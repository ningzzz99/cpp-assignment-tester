"""Prerequisite detection and a minimal compile-and-run smoke test (Phase 1).

Compilation uses the compiler module; execution here is still ad hoc and will
be replaced by the runner module in a later phase.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .compiler import compile_cpp
from .models import CompileStatus

INSTALL_HINTS = {
    "clang++": "Install Apple's command line tools with: xcode-select --install",
    "python": "Python 3.9+ is required. Install from https://www.python.org or: brew install python",
}


@dataclass(frozen=True)
class ToolStatus:
    name: str
    found: bool
    detail: str  # version string when found, installation hint when not


def check_python() -> ToolStatus:
    ok = sys.version_info >= (3, 9)
    version = sys.version.split()[0]
    return ToolStatus("python", ok, version if ok else f"{version}. {INSTALL_HINTS['python']}")


def check_clang() -> ToolStatus:
    path = shutil.which("clang++")
    if path is None:
        return ToolStatus("clang++", False, INSTALL_HINTS["clang++"])
    try:
        result = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ToolStatus("clang++", False, f"{path} could not run ({exc}). {INSTALL_HINTS['clang++']}")
    if result.returncode != 0:
        # e.g. the /usr/bin/clang++ shim exists but the command line tools are not installed
        return ToolStatus("clang++", False, f"{path} failed to run. {INSTALL_HINTS['clang++']}")
    lines = result.stdout.strip().splitlines()
    return ToolStatus("clang++", True, lines[0] if lines else "(no version output)")


def check_prerequisites() -> list[ToolStatus]:
    return [check_python(), check_clang()]


def smoke_test(source: Path, stdin_text: str, expected_stdout: str) -> tuple[bool, str]:
    """Compile `source` as C++17 into a temp dir, run it once, compare output.

    Returns (passed, message). Never raises for expected failures.
    """
    result = compile_cpp(source, timeout_seconds=60)
    try:
        if not result.ok:
            if result.status is CompileStatus.SOURCE_NOT_FOUND:
                return False, f"Source file not found: {source}"
            if result.status is CompileStatus.COMPILER_UNAVAILABLE:
                return False, INSTALL_HINTS["clang++"]
            return False, f"Compilation failed:\n{result.stderr}"
        try:
            run = subprocess.run(
                [str(result.binary_path)], input=stdin_text, capture_output=True, text=True, timeout=10
            )
        except subprocess.TimeoutExpired:
            return False, "Program timed out after 10s"
    finally:
        result.cleanup()

    if run.returncode != 0:
        return False, f"Program exited with code {run.returncode}"
    if run.stdout != expected_stdout:
        return False, f"Output mismatch: expected {expected_stdout!r}, got {run.stdout!r}"
    return True, f"Compiled and ran {source.name}; output {run.stdout!r} as expected"
