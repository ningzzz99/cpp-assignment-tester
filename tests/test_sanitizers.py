import json
import shutil
import stat
from pathlib import Path

import pytest

from cppgrader import cli
from cppgrader.cli import main
from cppgrader.compiler import build_command, sanitizer_flags
from cppgrader.models import CaseSpec, ComparisonMode, FailureCategory, SuiteSpec
from cppgrader.runner import grade_submission, run_case
from cppgrader.sanitizers import check_sanitizer_support, find_sanitizer_report, runtime_unusable

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "examples" / "average_calculator"
FIXTURES = REPO / "tests" / "fixtures"
STRICT = ComparisonMode.STRICT
needs_clang = pytest.mark.skipif(shutil.which("clang++") is None, reason="clang++ not installed")


def fake_binary(tmp_path, body):
    path = tmp_path / "fake"
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


# --- argument construction -------------------------------------------------

def test_no_sanitizers_leaves_command_unchanged():
    plain = build_command("clang++", Path("/s.cpp"), Path("/b"))
    assert plain == build_command("clang++", Path("/s.cpp"), Path("/b"), ())
    assert not any("sanitize" in a for a in plain)


def test_sanitizer_flags():
    flags = sanitizer_flags(["address", "undefined", "address"])
    assert "-fsanitize=address,undefined" in flags
    assert "-fno-sanitize-recover=all" in flags
    cmd = build_command("clang++", Path("/s.cpp"), Path("/b"), ["undefined"])
    assert cmd.index("-fsanitize=undefined") < cmd.index("/s.cpp")  # flags precede the source


def test_unknown_sanitizer_rejected():
    with pytest.raises(ValueError, match="Unsupported sanitizer"):
        sanitizer_flags(["thread"])


# --- diagnostics recognition -----------------------------------------------

def test_find_sanitizer_report():
    ubsan = "a.cpp:5:7: runtime error: signed integer overflow\nSUMMARY: UndefinedBehaviorSanitizer: x\n"
    assert "runtime error" in find_sanitizer_report(ubsan)
    assert "AddressSanitizer" in find_sanitizer_report("==1==ERROR: AddressSanitizer: heap-use-after-free")
    assert find_sanitizer_report("just some stderr\n") is None


def test_runtime_unusable():
    assert runtime_unusable("==1==ERROR: Interceptors are not working.")
    assert not runtime_unusable("ordinary stderr")


def case(expected="ok\n"):
    return CaseSpec("t", "", expected, 5.0)


def test_sanitizer_diagnostic_with_abnormal_exit_is_a_sanitizer_failure(tmp_path):
    binary = fake_binary(tmp_path, "echo 'a.cpp:1:1: runtime error: bad' >&2\necho ok\nexit 1\n")
    result = run_case(binary, case(), STRICT, sanitized=True)
    assert not result.passed and result.category is FailureCategory.SANITIZER
    assert "runtime error" in result.message and result.exit_code == 1


def test_lookalike_stderr_with_clean_exit_is_not_a_finding(tmp_path):
    binary = fake_binary(tmp_path, "echo 'a.cpp:1:1: runtime error: bad' >&2\necho ok\n")
    assert run_case(binary, case(), STRICT, sanitized=True).passed


def test_unanchored_runtime_error_text_is_not_a_finding(tmp_path):
    assert find_sanitizer_report("Parse failed: runtime error: bad token\n") is None
    binary = fake_binary(tmp_path, "echo 'Parse failed: runtime error: x' >&2\necho ok\nexit 3\n")
    result = run_case(binary, case(), STRICT, sanitized=True)
    assert result.category is FailureCategory.NON_ZERO_EXIT


def test_unusable_runtime_text_with_clean_exit_is_ignored(tmp_path):
    binary = fake_binary(tmp_path, "echo '==1==ERROR: Interceptors are not working.' >&2\necho ok\n")
    assert run_case(binary, case(), STRICT, sanitized=True).passed


def test_crash_without_sanitizer_text_stays_a_crash(tmp_path):
    binary = fake_binary(tmp_path, "echo ok\nkill -SEGV $$\n")
    assert run_case(binary, case(), STRICT, sanitized=True).category is FailureCategory.CRASH


def test_same_stderr_is_ignored_for_ordinary_builds(tmp_path):
    binary = fake_binary(tmp_path, "echo 'runtime error: from the student program' >&2\necho ok\n")
    assert run_case(binary, case(), STRICT).passed


def test_sanitizer_abort_is_reported_as_sanitizer_not_crash(tmp_path):
    binary = fake_binary(tmp_path, "echo '==1==ERROR: AddressSanitizer: heap-use-after-free' >&2\n"
                                   "kill -ABRT $$\n")
    result = run_case(binary, case(), STRICT, sanitized=True)
    assert result.category is FailureCategory.SANITIZER and result.signal is not None


def test_unusable_runtime_is_runner_error_not_student_fault(tmp_path):
    binary = fake_binary(tmp_path, "echo '==1==ERROR: Interceptors are not working.' >&2\nexit 134\n")
    result = run_case(binary, case(), STRICT, sanitized=True)
    assert result.category is FailureCategory.RUNNER_ERROR and "sanitizer runtime" in result.message


def test_timeout_still_outranks_sanitizer(tmp_path):
    binary = fake_binary(tmp_path, "echo 'runtime error: x' >&2\nsleep 30\n")
    result = run_case(binary, CaseSpec("t", "", "", 0.3), STRICT, sanitized=True)
    assert result.category is FailureCategory.TIMEOUT


# --- toolchain probing -----------------------------------------------------

def test_probe_reports_missing_compiler():
    support = check_sanitizer_support(["undefined"], compiler="definitely-not-a-compiler")
    assert not support.ok and "compiler_unavailable" in support.message


@pytest.mark.skipif(shutil.which("false") is None, reason="no `false` binary")
def test_probe_reports_compiler_that_rejects_flags():
    support = check_sanitizer_support(["undefined"], compiler="false")
    assert not support.ok and "Could not build" in support.message


# --- real toolchain (skipped when the sanitizer is unusable here) ----------

def ubsan_usable():
    return shutil.which("clang++") is not None and check_sanitizer_support(("undefined",)).ok


@pytest.mark.skipif(not ubsan_usable(), reason="UBSan not usable on this toolchain")
def test_ubsan_detects_overflow_end_to_end():
    suite = SuiteSpec("A", STRICT, (case(),))
    plain = grade_submission(FIXTURES / "ubsan_overflow.cpp", suite)
    assert plain.compile.sanitizers == () and plain.passed  # ordinary build: UB goes unnoticed
    san = grade_submission(FIXTURES / "ubsan_overflow.cpp", suite, sanitizers=["undefined"])
    assert san.compile.sanitizers == ("undefined",)
    assert not san.passed and san.cases[0].category is FailureCategory.SANITIZER


@pytest.mark.skipif(not ubsan_usable(), reason="UBSan not usable on this toolchain")
def test_clean_program_passes_under_ubsan():
    suite = SuiteSpec("A", STRICT, (CaseSpec("t", "4\n2 4 6 8\n", "5\n", 5.0),))
    assert grade_submission(EXAMPLE / "solution.cpp", suite, sanitizers=["undefined"]).passed


# --- CLI ---------------------------------------------------------------------

SOLUTION, TESTS = str(EXAMPLE / "solution.cpp"), str(EXAMPLE / "tests.json")


@needs_clang
def test_cli_pass_exit_0_and_report(tmp_path, capsys):
    report = tmp_path / "out" / "r.json"
    assert main(["grade", SOLUTION, TESTS, "--report", str(report)]) == 0
    out = capsys.readouterr().out
    assert "RESULT: PASSED (3/3" in out and "Report written" in out
    data = json.loads(report.read_text())
    assert data["outcome"] == "passed" and data["compile"]["sanitizers"] == []


@needs_clang
def test_cli_grading_failure_exit_1(capsys):
    assert main(["grade", str(FIXTURES / "wrong_output.cpp"), TESTS]) == 1
    out = capsys.readouterr().out
    assert "FAIL  normal_values [wrong_output]" in out and "RESULT: FAILED (0/3" in out
    assert "PASSED" not in out


@needs_clang
def test_cli_compile_error_exit_1_and_not_graded(tmp_path, capsys):
    bad = tmp_path / "bad.cpp"
    bad.write_text("int main() { int x = ; }\n")
    assert main(["grade", str(bad), TESTS]) == 1
    out = capsys.readouterr().out
    assert "COMPILATION FAILED" in out and "NOT GRADED" in out and "PASSED" not in out


def test_cli_missing_source_exit_2(tmp_path, capsys):
    assert main(["grade", str(tmp_path / "nope.cpp"), TESTS]) == 2
    assert "Source file not found" in capsys.readouterr().err


def test_cli_bad_test_file_exit_2(tmp_path, capsys):
    bad = tmp_path / "t.json"
    bad.write_text("{not json")
    assert main(["grade", SOLUTION, str(bad)]) == 2
    assert "Invalid JSON" in capsys.readouterr().err


@needs_clang
def test_cli_report_write_failure_exit_3_but_result_still_shown(tmp_path, capsys):
    assert main(["grade", SOLUTION, TESTS, "--report", str(tmp_path)]) == 3  # a directory
    captured = capsys.readouterr()
    assert "RESULT: PASSED" in captured.out and "report was not saved" in captured.err


def test_cli_unsupported_sanitizer_stops_before_grading(monkeypatch, capsys):
    monkeypatch.setattr(cli, "check_sanitizer_support",
                        lambda names: type("S", (), {"ok": False, "message": "ASan broken"})())
    monkeypatch.setattr(cli, "grade_submission",
                        lambda *a, **k: pytest.fail("must not grade without usable sanitizers"))
    assert main(["grade", SOLUTION, TESTS, "--sanitize", "address"]) == 2
    err = capsys.readouterr().err
    assert "ASan broken" in err and "Nothing was graded" in err


def test_cli_rejects_unknown_sanitizer_and_bad_timeout(capsys):
    with pytest.raises(SystemExit) as info:
        main(["grade", SOLUTION, TESTS, "--sanitize", "thread"])
    assert info.value.code == 2
    assert main(["grade", SOLUTION, TESTS, "--compile-timeout", "0"]) == 2


def test_cli_check_and_help_still_work(capsys):
    assert main([]) == 0
    assert "grade" in capsys.readouterr().out
    assert main(["--check"]) in (0, 1)


def test_cli_nonfinite_compile_timeout_is_a_clean_error(capsys):
    for bad in ("inf", "nan", "-1"):
        assert main(["grade", SOLUTION, TESTS, "--compile-timeout", bad]) == 2
        assert "finite number greater than 0" in capsys.readouterr().err


def test_cli_report_cannot_overwrite_source_or_tests(tmp_path, capsys):
    src = tmp_path / "s.cpp"
    src.write_text("int main() {}\n")
    assert main(["grade", str(src), TESTS, "--report", str(src)]) == 2
    assert src.read_text() == "int main() {}\n"
    assert "overwrite the source file" in capsys.readouterr().err
    tests = tmp_path / "t.json"
    tests.write_text(Path(TESTS).read_text())
    assert main(["grade", SOLUTION, str(tests), "--report", str(tests)]) == 2
    assert tests.read_text() == Path(TESTS).read_text()
    link = tmp_path / "link.json"  # a symlink to the source is the same file too
    link.symlink_to(src)
    assert main(["grade", str(src), TESTS, "--report", str(link)]) == 2
    assert src.read_text() == "int main() {}\n"


def test_cli_combined_sanitizers_are_probed_and_passed_through_together(monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr(cli, "check_sanitizer_support",
                        lambda names: seen.setdefault("probe", tuple(names)) and
                        type("S", (), {"ok": True, "message": ""})())
    real = cli.grade_submission

    def spy(*a, **k):
        seen["grade"] = tuple(k["sanitizers"])
        return real(*a, **{**k, "sanitizers": ()})  # avoid needing a working ASan here
    monkeypatch.setattr(cli, "grade_submission", spy)
    assert main(["grade", SOLUTION, TESTS, "--sanitize", "undefined", "--sanitize", "address",
                 "--sanitize", "undefined"]) == 0
    assert seen == {"probe": ("undefined", "address"), "grade": ("undefined", "address")}


def asan_usable():
    return shutil.which("clang++") is not None and check_sanitizer_support(("address",)).ok


@pytest.mark.skipif(asan_usable(), reason="ASan works here; the broken-toolchain path is not reachable")
@needs_clang
def test_asan_unusable_toolchain_gives_clean_exit_2_for_asan_and_combined(capsys):
    for flags in (["--sanitize", "address"], ["--sanitize", "undefined", "--sanitize", "address"]):
        assert main(["grade", SOLUTION, TESTS, *flags]) == 2
        err = capsys.readouterr().err
        assert "Nothing was graded" in err and "do not run correctly" in err or "Could not build" in err


@pytest.mark.skipif(not asan_usable(), reason="AddressSanitizer is not usable on this toolchain")
def test_asan_and_ubsan_combined_end_to_end():
    suite = SuiteSpec("A", STRICT, (CaseSpec("t", "4\n2 4 6 8\n", "5\n", 5.0),))
    grade = grade_submission(EXAMPLE / "solution.cpp", suite, sanitizers=["address", "undefined"])
    assert grade.passed and grade.compile.sanitizers == ("address", "undefined")
