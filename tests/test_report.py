import json
import math
import os
import shutil
from pathlib import Path

import pytest

from cppgrader import report as report_module
from cppgrader.models import (
    CaseResult, CaseSpec, CompileResult, CompileStatus, ComparisonMode, FailureCategory,
    GradeResult, SuiteSpec,
)
from cppgrader.report import (
    REPORT_SCHEMA_VERSION, ReportWriteError, build_report, report_to_json, write_report,
)
from cppgrader.runner import grade_submission
from cppgrader.test_loader import load_suite

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "examples" / "average_calculator"
STRICT = ComparisonMode.STRICT


def compiled(status=CompileStatus.SUCCESS, stderr="", rc=0):
    return CompileResult(status, ["clang++", "x.cpp"], rc, "", stderr, 0.5,
                         binary_path=Path("/tmp/p") if status is CompileStatus.SUCCESS else None)


def case_result(name="t", passed=True, category=None, **kw):
    base = dict(name=name, passed=passed, category=category, exit_code=0, signal=None,
                elapsed_seconds=0.01, stdout="out\n", stderr="", output_truncated=False,
                output_matches=passed, diff="", message="Passed" if passed else "Failed")
    base.update(kw)
    return CaseResult(**base)


def spec(name="t"):
    return CaseSpec(name, "in\n", "out\n", 2.0)


def make_grade(cases, comp=None):
    return GradeResult("Demo", comp or compiled(), cases, 1.25)


def test_successful_report_fields():
    suite = SuiteSpec("Demo", STRICT, (spec(),))
    rep = build_report(make_grade([case_result()]), suite)
    assert rep["schema_version"] == REPORT_SCHEMA_VERSION
    assert rep["assignment"] == "Demo" and rep["outcome"] == "passed" and rep["passed"] is True
    assert rep["comparison_mode"] == "strict"
    assert rep["summary"] == {"total": 1, "passed": 1, "failed": 0, "failures_by_category": {}}
    t = rep["tests"][0]
    assert t["expected_output"] == "out\n" and t["actual_output"] == "out\n"
    assert t["input"] == "in\n" and t["timeout_seconds"] == 2.0
    assert t["failure_category"] is None and t["exit_code"] == 0


def test_compile_failure_report_keeps_diagnostics_and_has_no_tests():
    comp = compiled(CompileStatus.COMPILE_ERROR, "x.cpp:1: error: expected expression\n", rc=1)
    rep = build_report(make_grade([], comp))
    assert rep["outcome"] == "compile_failed" and rep["passed"] is False
    assert rep["compile"]["status"] == "compile_error"
    assert "expected expression" in rep["compile"]["diagnostics"]
    assert rep["compile"]["return_code"] == 1 and rep["tests"] == []


def test_test_failures_and_summary_counts():
    cases = [
        case_result("a"),
        case_result("b", False, FailureCategory.WRONG_OUTPUT, stdout="bad\n", diff="-out\n+bad"),
        case_result("c", False, FailureCategory.NON_ZERO_EXIT, exit_code=3, stderr="boom\n"),
        case_result("d", False, FailureCategory.WRONG_OUTPUT),
    ]
    suite = SuiteSpec("Demo", STRICT, tuple(spec(n) for n in "abcd"))
    rep = build_report(make_grade(cases), suite)
    assert rep["outcome"] == "failed" and rep["passed"] is False
    assert rep["summary"] == {"total": 4, "passed": 1, "failed": 3,
                              "failures_by_category": {"non_zero_exit": 1, "wrong_output": 2}}
    c = rep["tests"][2]
    assert c["exit_code"] == 3 and c["stderr"] == "boom\n"
    assert c["failure_category"] == "non_zero_exit"


def test_timeout_and_crash_entries():
    cases = [
        case_result("t", False, FailureCategory.TIMEOUT, exit_code=None, signal=9,
                    message="Timed out after 2s and was killed"),
        case_result("c", False, FailureCategory.CRASH, exit_code=None, signal=6),
    ]
    rep = build_report(make_grade(cases))
    assert rep["tests"][0]["failure_category"] == "timeout"
    assert rep["tests"][0]["exit_code"] is None and rep["tests"][0]["signal"] == 9
    assert rep["tests"][1]["failure_category"] == "crash"


def test_without_suite_expected_output_is_null():
    rep = build_report(make_grade([case_result()]))
    assert rep["comparison_mode"] is None
    assert rep["tests"][0]["expected_output"] is None and rep["tests"][0]["input"] is None


def test_no_tests_outcome():
    assert build_report(make_grade([]))["outcome"] == "no_tests"


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_non_finite_numbers_become_null_and_json_is_strict(bad):
    grade = make_grade([case_result(elapsed_seconds=bad)])
    grade.total_seconds = bad
    text = report_to_json(build_report(grade))
    data = json.loads(text, parse_constant=lambda c: pytest.fail(f"non-standard constant {c}"))
    assert data["total_elapsed_seconds"] is None and data["tests"][0]["elapsed_seconds"] is None


def test_output_text_round_trips_exactly():
    odd = "tab\t quote\" nul\x00 unicode é 日本 \r\n trailing  \n\n"
    rep = build_report(make_grade([case_result(stdout=odd)]))
    assert json.loads(report_to_json(rep))["tests"][0]["actual_output"] == odd


def test_json_is_deterministic_sorted_and_newline_terminated():
    rep = build_report(make_grade([case_result()]))
    text = report_to_json(rep)
    assert text == report_to_json(build_report(make_grade([case_result()])))
    assert text.endswith("}\n")
    assert list(json.loads(text)) == sorted(json.loads(text))


def test_unserializable_report_raises_report_write_error(tmp_path):
    target = tmp_path / "r.json"
    with pytest.raises(ReportWriteError, match="serialized"):
        write_report({"bad": object()}, target)
    assert not target.exists()


def test_write_report_creates_parents_and_leaves_no_temp_files(tmp_path):
    target = tmp_path / "nested" / "dir" / "r.json"
    rep = build_report(make_grade([case_result()]))
    assert write_report(rep, target) == target
    assert json.loads(target.read_text(encoding="utf-8")) == json.loads(report_to_json(rep))
    assert [p.name for p in target.parent.iterdir()] == ["r.json"]


def test_write_report_replaces_existing_report(tmp_path):
    target = tmp_path / "r.json"
    target.write_text("old")
    write_report(build_report(make_grade([])), target)
    assert json.loads(target.read_text())["schema_version"] == REPORT_SCHEMA_VERSION


def test_failed_write_keeps_previous_report_and_cleans_temp(tmp_path, monkeypatch):
    target = tmp_path / "r.json"
    target.write_text("previous report")

    def boom(src, dst):
        raise OSError("disk exploded")
    monkeypatch.setattr(report_module.os, "replace", boom)
    with pytest.raises(ReportWriteError, match="disk exploded"):
        write_report(build_report(make_grade([])), target)
    assert target.read_text() == "previous report"
    assert [p.name for p in tmp_path.iterdir()] == ["r.json"]


def test_target_is_a_directory(tmp_path):
    with pytest.raises(ReportWriteError, match="Could not write report"):
        write_report(build_report(make_grade([])), tmp_path)


def test_parent_path_is_a_file(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    with pytest.raises(ReportWriteError):
        write_report(build_report(make_grade([])), blocker / "r.json")


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permissions")
def test_read_only_directory(tmp_path):
    ro = tmp_path / "ro"
    ro.mkdir()
    ro.chmod(0o555)
    try:
        with pytest.raises(ReportWriteError, match="Could not write report"):
            write_report(build_report(make_grade([])), ro / "r.json")
    finally:
        ro.chmod(0o755)


def test_report_write_error_is_not_a_grading_result(tmp_path):
    grade = make_grade([case_result()])
    with pytest.raises(ReportWriteError):
        write_report(build_report(grade), tmp_path)  # a directory
    assert grade.passed  # grading outcome is untouched


@pytest.mark.skipif(shutil.which("clang++") is None, reason="clang++ not installed")
def test_end_to_end_example_report(tmp_path):
    suite = load_suite(EXAMPLE / "tests.json")
    grade = grade_submission(EXAMPLE / "solution.cpp", suite)
    path = write_report(build_report(grade, suite), tmp_path / "report.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["outcome"] == "passed" and data["summary"]["total"] == 3
    assert [t["name"] for t in data["tests"]] == ["normal_values", "single_value", "negative_values"]
    assert all(t["expected_output"] == t["actual_output"] for t in data["tests"])
