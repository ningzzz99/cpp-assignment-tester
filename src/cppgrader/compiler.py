"""Compile a C++17 source file with clang++ (no shell, with timeout)."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path

from .models import CompileResult, CompileStatus

DEFAULT_COMPILER = "clang++"
DEFAULT_TIMEOUT_SECONDS = 60.0
WARNING_FLAGS = ["-Wall", "-Wextra", "-Wpedantic"]
KILL_GRACE_SECONDS = 5.0  # how long to wait for output pipes to close after a kill


def build_command(compiler: str, source: Path, binary: Path) -> list[str]:
    """Return the argument list (never a shell string) for a C++17 compile.

    `-x c++` makes clang treat the file as C++ regardless of extension, and the
    absolute `source` path cannot be mistaken for an option.
    """
    return [compiler, "-std=c++17", *WARNING_FLAGS, "-x", "c++", str(source), "-o", str(binary)]


def _kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        proc.kill()


def compile_cpp(
    source: Path | str,
    build_dir: Path | None = None,
    *,
    compiler: str = DEFAULT_COMPILER,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> CompileResult:
    """Compile `source` into `build_dir` (a fresh temp directory when omitted).

    Never raises for expected failures; inspect `CompileResult.status`.
    Callers should call `result.cleanup()` when finished, whatever the status:
    an auto-created build directory is returned for every outcome that got far
    enough to create it. It is removed here only when an exception escapes.
    """
    start = time.monotonic()

    def failure(status: CompileStatus, command: list[str], message: str, **kw) -> CompileResult:
        return CompileResult(status, command, kw.pop("returncode", None), kw.pop("stdout", ""),
                             message, time.monotonic() - start, **kw)

    source_path = Path(source).expanduser().resolve()
    if not source_path.is_file():
        return failure(CompileStatus.SOURCE_NOT_FOUND, [], f"Source file not found: {source}")

    compiler_path = shutil.which(compiler)
    if compiler_path is None:
        return failure(CompileStatus.COMPILER_UNAVAILABLE, [compiler],
                       f"Compiler '{compiler}' not found. On macOS run: xcode-select --install")

    owns_dir = build_dir is None
    out_dir = Path(tempfile.mkdtemp(prefix="cppgrader-build-")) if owns_dir else Path(build_dir)
    dir_info = {"build_dir": out_dir, "_owns_build_dir": owns_dir}
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        result = failure(CompileStatus.BUILD_DIR_ERROR, [],
                         f"Could not create build directory '{out_dir}': {exc}", **dir_info)
        result.cleanup()
        return result
    binary = out_dir / "program"
    # Remove any binary left by an earlier build so a failed compile can never
    # leave something runnable behind. This is the exact path `-o` would overwrite.
    try:
        if binary.is_file() or binary.is_symlink():
            binary.unlink()
    except OSError as exc:
        result = failure(CompileStatus.BUILD_DIR_ERROR, [],
                         f"Could not remove stale binary '{binary}': {exc}", **dir_info)
        result.cleanup()
        return result
    command = build_command(compiler_path, source_path, binary)

    try:
        proc = subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            encoding="utf-8", errors="replace",
            start_new_session=True,  # own process group so a timeout kills clang's children too
        )
    except OSError as exc:
        return failure(CompileStatus.COMPILER_UNAVAILABLE, command,
                       f"Could not execute compiler '{compiler_path}': {exc}", **dir_info)

    try:
        stdout, stderr = proc.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        _kill_group(proc)
        try:
            stdout, stderr = proc.communicate(timeout=KILL_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            # A descendant outside the process group still holds the pipes open.
            stdout, stderr = "", "(partial compiler output unavailable)\n"
        note = f"Compilation timed out after {timeout_seconds:g}s and was killed.\n"
        return failure(CompileStatus.TIMEOUT, command, note + (stderr or ""),
                       stdout=stdout or "", **dir_info)
    except BaseException:  # e.g. KeyboardInterrupt: don't leave a compiler or temp dir behind
        _kill_group(proc)
        proc.wait()
        if owns_dir:
            shutil.rmtree(out_dir, ignore_errors=True)
        raise

    elapsed = time.monotonic() - start
    ok = proc.returncode == 0
    return CompileResult(
        CompileStatus.SUCCESS if ok else CompileStatus.COMPILE_ERROR,
        command, proc.returncode, stdout, stderr, elapsed,
        binary_path=binary if ok else None, **dir_info,
    )
