import shutil
import signal
from pathlib import Path

import pytest

from cppgrader.compiler import compile_cpp
from cppgrader.models import (
    CaseSpec, CompileStatus, ComparisonMode, FailureCategory, SuiteSpec,
)
from cppgrader.runner import grade_submission, run_case, run_suite
from cppgrader.test_loader import load_suite

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures"
EXAMPLE = REPO / "examples" / "average_calculator"

pytestmark = pytest.mark.skipif(shutil.which("clang++") is None, reason="clang++ not installed")
STRICT, NORM = ComparisonMode.STRICT, ComparisonMode.NORMALIZED_WHITESPACE


@pytest.fixture(scope="module")
def build(tmp_path_factory):
    """Compile a fixture once per module and return its binary path."""
    cache: dict[Path, Path] = {}

    def _build(source: Path) -> Path:
        if source not in cache:
            result = compile_cpp(source, tmp_path_factory.mktemp(source.stem))
            assert result.ok, result.stderr
            cache[source] = result.binary_path
        return cache[source]

    return _build


def spec(expected="5\n", input="", timeout=10.0, name="case"):
    return CaseSpec(name, input, expected, timeout)


def test_correct_output_passes(build):
    r = run_case(build(EXAMPLE / "solution.cpp"), spec(input="4\n2 4 6 8\n"), STRICT)
    assert r.passed and r.category is None
    assert r.exit_code == 0 and r.signal is None
    assert r.stdout == "5\n" and r.output_matches is True and r.diff == ""
    assert r.elapsed_seconds >= 0


def test_wrong_output_fails_with_diff(build):
    r = run_case(build(FIXTURES / "wrong_output.cpp"), spec(), STRICT)
    assert not r.passed and r.category is FailureCategory.WRONG_OUTPUT
    assert r.exit_code == 0 and r.output_matches is False
    assert "-5" in r.diff and "+6" in r.diff


def test_non_zero_exit_fails_even_when_output_matches(build):
    r = run_case(build(FIXTURES / "exit_three.cpp"), spec(), STRICT)
    assert r.output_matches is True
    assert not r.passed and r.category is FailureCategory.NON_ZERO_EXIT
    assert r.exit_code == 3


def test_crash_fails_even_when_output_matches(build):
    r = run_case(build(FIXTURES / "abort_after_output.cpp"), spec(), STRICT)
    assert r.output_matches is True
    assert not r.passed and r.category is FailureCategory.CRASH
    assert r.signal == signal.SIGABRT and r.exit_code is None
    assert "SIGABRT" in r.message


def test_timeout_is_killed_and_reported(build):
    r = run_case(build(FIXTURES / "infinite_loop.cpp"), spec(timeout=0.5), STRICT)
    assert not r.passed and r.category is FailureCategory.TIMEOUT
    assert "Timed out" in r.message
    assert r.elapsed_seconds < 30  # generous bound: proves the loop did not run on


def test_runaway_output_is_capped(build):
    r = run_case(build(FIXTURES / "flood_output.cpp"), spec(timeout=20), STRICT, max_output_bytes=100_000)
    assert not r.passed and r.category is FailureCategory.OUTPUT_LIMIT
    assert r.output_truncated and len(r.stdout) <= 100_000


def test_stdout_and_stderr_captured_separately(build):
    r = run_case(build(FIXTURES / "split_streams.cpp"), spec(expected="to-stdout\n"), STRICT)
    assert r.passed
    assert r.stdout == "to-stdout\n" and r.stderr == "to-stderr\n"


def test_input_is_delivered_per_run(build):
    binary = build(FIXTURES / "echo_input.cpp")
    assert run_case(binary, spec(expected="a\nb\n", input="a\nb\n"), STRICT).passed
    assert run_case(binary, spec(expected="", input=""), STRICT).passed  # runs are independent


def test_whitespace_mode_changes_verdict(build):
    binary = build(FIXTURES / "whitespace_variant.cpp")
    assert not run_case(binary, spec(), STRICT).passed
    assert run_case(binary, spec(), NORM).passed


def test_program_does_not_inherit_environment(build, monkeypatch):
    monkeypatch.setenv("CPPGRADER_SECRET_PROBE", "1")
    r = run_case(build(FIXTURES / "env_dump.cpp"), spec(expected="clean\n"), STRICT)
    assert r.passed, r.stdout


def test_missing_binary_is_a_runner_error(tmp_path):
    r = run_case(tmp_path / "nope", spec(), STRICT)
    assert r.category is FailureCategory.RUNNER_ERROR and not r.passed


def test_each_case_in_a_suite_is_reported_separately(build, tmp_path):
    compiled = compile_cpp(EXAMPLE / "solution.cpp", tmp_path)
    suite = SuiteSpec("A", STRICT, (
        spec("5\n", "4\n2 4 6 8\n", name="ok"),
        spec("99\n", "1\n7\n", name="bad"),
    ))
    results = run_suite(compiled, suite)
    assert [(r.name, r.passed) for r in results] == [("ok", True), ("bad", False)]


def test_grade_example_assignment_passes_and_cleans_up():
    suite = load_suite(EXAMPLE / "tests.json")
    grade = grade_submission(EXAMPLE / "solution.cpp", suite)
    assert grade.passed, [c.message for c in grade.cases]
    assert len(grade.cases) == 3 and grade.compile.ok
    assert not grade.compile.build_dir.exists()


def test_grade_reports_failures_and_not_passed(tmp_path):
    suite = SuiteSpec("A", STRICT, (spec("5\n"),))
    grade = grade_submission(FIXTURES / "wrong_output.cpp", suite)
    assert not grade.passed and grade.cases[0].category is FailureCategory.WRONG_OUTPUT


def test_compile_error_runs_no_tests(tmp_path):
    bad = tmp_path / "bad.cpp"
    bad.write_text("int main() { int x = ; }\n")
    grade = grade_submission(bad, SuiteSpec("A", STRICT, (spec(),)))
    assert grade.compile.status is CompileStatus.COMPILE_ERROR
    assert grade.cases == [] and not grade.passed


def test_failed_recompile_into_same_dir_leaves_no_stale_binary(tmp_path):
    good = tmp_path / "good.cpp"
    good.write_text('#include <iostream>\nint main() { std::cout << "5\\n"; }\n')
    bad = tmp_path / "bad.cpp"
    bad.write_text("int main() { int x = ; }\n")
    build_dir = tmp_path / "build"

    first = compile_cpp(good, build_dir)
    assert first.ok and first.binary_path.is_file()

    second = compile_cpp(bad, build_dir)  # same directory, same output path
    assert second.status is CompileStatus.COMPILE_ERROR
    assert second.binary_path is None
    assert not (build_dir / "program").exists()  # the old binary is gone
    with pytest.raises(ValueError, match="compilation did not succeed"):
        run_suite(second, SuiteSpec("A", STRICT, (spec(),)))


def test_run_suite_refuses_unsuccessful_compilation(tmp_path):
    missing = compile_cpp(tmp_path / "nope.cpp")
    with pytest.raises(ValueError):
        run_suite(missing, SuiteSpec("A", STRICT, (spec(),)))


def test_grade_never_runs_stale_executable_after_failed_compile(tmp_path):
    build_dir = tmp_path / "build"
    build_dir.mkdir()
    marker = tmp_path / "ran.txt"
    stale = build_dir / "program"  # the path the compiler would produce
    stale.write_text(f"#!/bin/sh\necho ran > '{marker}'\necho 5\n")
    stale.chmod(0o755)
    bad = tmp_path / "bad.cpp"
    bad.write_text("int main() { int x = ; }\n")

    grade = grade_submission(bad, SuiteSpec("A", STRICT, (spec("5\n"),)), build_dir=build_dir)

    assert grade.compile.status is CompileStatus.COMPILE_ERROR
    assert "error" in grade.compile.stderr  # diagnostics preserved
    assert grade.cases == [] and not grade.passed
    assert not marker.exists()  # the dummy executable was never executed
    assert build_dir.exists()  # a caller-owned build dir is not deleted


def test_grade_with_caller_build_dir_succeeds_and_keeps_dir(tmp_path):
    grade = grade_submission(EXAMPLE / "solution.cpp", load_suite(EXAMPLE / "tests.json"),
                             build_dir=tmp_path / "build")
    assert grade.passed
    assert (tmp_path / "build").is_dir()
