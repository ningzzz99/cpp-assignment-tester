import os
import shutil
import stat
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

from cppgrader.compiler import build_command, compile_cpp
from cppgrader.models import CompileStatus

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "average_calculator" / "solution.cpp"
needs_clang = pytest.mark.skipif(shutil.which("clang++") is None, reason="clang++ not installed")


def write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text)
    return path


def test_build_command_is_an_argument_list_with_required_flags(tmp_path):
    cmd = build_command("clang++", tmp_path / "a.cpp", tmp_path / "out")
    assert isinstance(cmd, list)
    for flag in ("-std=c++17", "-Wall", "-Wextra", "-Wpedantic"):
        assert flag in cmd


@needs_clang
def test_successful_compilation(tmp_path):
    result = compile_cpp(EXAMPLE, tmp_path / "build")
    assert result.status is CompileStatus.SUCCESS and result.ok
    assert result.returncode == 0
    assert result.binary_path.is_file()
    assert result.binary_path.parent == tmp_path / "build"
    assert result.elapsed_seconds >= 0
    assert not result.has_warnings
    assert subprocess.run([str(result.binary_path)], input="2\n1 2\n",
                          capture_output=True, text=True).stdout == "1.5\n"


@needs_clang
def test_source_directory_is_left_untouched(tmp_path):
    src = write(tmp_path, "ok.cpp", "int main() { return 0; }\n")
    before = sorted(p.name for p in tmp_path.iterdir())
    result = compile_cpp(src)
    try:
        assert result.ok
        assert sorted(p.name for p in tmp_path.iterdir()) == before
    finally:
        result.cleanup()


@needs_clang
def test_compile_error_preserves_diagnostics(tmp_path):
    src = write(tmp_path, "bad.cpp", "int main() { int x = ; return 0; }\n")
    result = compile_cpp(src, tmp_path / "build")
    assert result.status is CompileStatus.COMPILE_ERROR and not result.ok
    assert result.returncode != 0
    assert "bad.cpp" in result.stderr and "error" in result.stderr
    assert result.binary_path is None


@needs_clang
def test_warnings_are_surfaced_not_ignored(tmp_path):
    src = write(tmp_path, "warn.cpp", "int main() { int unused = 0; return 0; }\n")
    result = compile_cpp(src, tmp_path / "build")
    assert result.ok and result.has_warnings
    assert "unused" in result.stderr


@needs_clang
def test_filename_starting_with_dash_is_not_parsed_as_option(tmp_path):
    src = write(tmp_path, "-weird.cpp", "int main() { return 0; }\n")
    assert compile_cpp(src, tmp_path / "build").ok


def test_missing_source_file(tmp_path):
    result = compile_cpp(tmp_path / "nope.cpp", tmp_path / "build")
    assert result.status is CompileStatus.SOURCE_NOT_FOUND
    assert "not found" in result.stderr


def test_missing_compiler(tmp_path):
    src = write(tmp_path, "ok.cpp", "int main() { return 0; }\n")
    result = compile_cpp(src, tmp_path / "build", compiler="no-such-compiler-xyz")
    assert result.status is CompileStatus.COMPILER_UNAVAILABLE
    assert "xcode-select --install" in result.stderr


def test_non_executable_compiler_is_reported(tmp_path):
    src = write(tmp_path, "ok.cpp", "int main() { return 0; }\n")
    fake = write(tmp_path, "fake-cc", "not a program\n")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)  # executable bit, but invalid format
    result = compile_cpp(src, tmp_path / "build", compiler=str(fake))
    assert result.status is CompileStatus.COMPILER_UNAVAILABLE


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_timeout_kills_compiler_and_its_children(tmp_path):
    """A fake 'compiler' that spawns a long sleep stands in for a hung clang/ld."""
    pidfile = tmp_path / "child.pid"
    fake = write(tmp_path, "slow-cc", f"#!/bin/sh\nsleep 60 &\necho $! > '{pidfile}'\nwait\n")
    fake.chmod(0o755)
    src = write(tmp_path, "ok.cpp", "int main() { return 0; }\n")

    start = time.monotonic()
    result = compile_cpp(src, tmp_path / "build", compiler=str(fake), timeout_seconds=1.0)

    assert result.status is CompileStatus.TIMEOUT
    assert "timed out" in result.stderr
    assert time.monotonic() - start < 30  # generous: proves we did not wait for the sleep
    child = int(pidfile.read_text())
    deadline = time.monotonic() + 5
    while _alive(child) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not _alive(child), "child process survived the timeout"


@needs_clang
def test_cleanup_only_removes_owned_build_dir(tmp_path):
    src = write(tmp_path, "ok.cpp", "int main() { return 0; }\n")
    mine = tmp_path / "mine"
    result = compile_cpp(src, mine)
    result.cleanup()
    assert mine.exists()  # caller-supplied dir is never deleted

    owned = compile_cpp(src)
    assert owned.build_dir.exists()
    owned.cleanup()
    assert not owned.build_dir.exists()


def test_unusable_build_dir_is_reported_not_raised(tmp_path):
    src = write(tmp_path, "ok.cpp", "int main() { return 0; }\n")
    blocker = write(tmp_path, "a_file", "")
    result = compile_cpp(src, blocker / "sub")  # parent is a file, so mkdir must fail
    assert result.status is CompileStatus.BUILD_DIR_ERROR
    assert "build directory" in result.stderr


@needs_clang
def test_interrupt_removes_owned_build_dir(tmp_path, monkeypatch):
    src = write(tmp_path, "ok.cpp", "int main() { return 0; }\n")
    created = []
    real_mkdtemp = tempfile.mkdtemp
    monkeypatch.setattr("cppgrader.compiler.tempfile.mkdtemp",
                        lambda **kw: created.append(real_mkdtemp(**kw)) or created[-1])

    def interrupted(self, *a, **kw):
        raise KeyboardInterrupt

    monkeypatch.setattr(subprocess.Popen, "communicate", interrupted)
    with pytest.raises(KeyboardInterrupt):
        compile_cpp(src)
    assert len(created) == 1 and not Path(created[0]).exists()


def test_auto_build_dir_is_returned_for_cleanup_when_compiler_missing(tmp_path):
    src = write(tmp_path, "ok.cpp", "int main() { return 0; }\n")
    result = compile_cpp(src, compiler="no-such-compiler-xyz")
    assert result.build_dir is None  # nothing was created, so nothing to leak
