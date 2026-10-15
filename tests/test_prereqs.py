import shutil
from pathlib import Path

import pytest

from cppgrader.cli import main
from cppgrader.prereqs import check_clang, check_prerequisites, smoke_test

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "average_calculator" / "solution.cpp"
needs_clang = pytest.mark.skipif(shutil.which("clang++") is None, reason="clang++ not installed")


def test_check_prerequisites_reports_python():
    statuses = {s.name: s for s in check_prerequisites()}
    assert statuses["python"].found


def test_missing_source_is_reported_not_raised(tmp_path):
    passed, message = smoke_test(tmp_path / "nope.cpp", "", "")
    assert not passed
    assert "not found" in message or "xcode-select" in message


@needs_clang
def test_smoke_test_passes_on_example():
    passed, message = smoke_test(EXAMPLE, "4\n2 4 6 8\n", "5\n")
    assert passed, message


@needs_clang
def test_smoke_test_detects_wrong_expectation():
    passed, _ = smoke_test(EXAMPLE, "4\n2 4 6 8\n", "6\n")
    assert not passed


@needs_clang
def test_cli_smoke_exit_code_zero():
    assert main(["--check", "--smoke"]) == 0


def test_clang_that_fails_to_run_is_reported_missing(tmp_path, monkeypatch):
    fake = tmp_path / "clang++"
    fake.write_text("#!/bin/sh\necho 'no developer tools' >&2\nexit 1\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    status = check_clang()
    assert not status.found and "xcode-select --install" in status.detail
