import json

import pytest

from cppgrader.models import ComparisonMode
from cppgrader.test_loader import SuiteFormatError, load_suite, parse_suite

REPO = __import__("pathlib").Path(__file__).resolve().parents[1]


def case(**over):
    base = {"name": "t1", "input": "1\n", "expected_output": "1\n", "timeout_seconds": 2}
    base.update(over)
    return base


def suite(**over):
    base = {"assignment": "A", "tests": [case()]}
    base.update(over)
    return base


def test_example_suite_loads():
    s = load_suite(REPO / "examples" / "average_calculator" / "tests.json")
    assert s.assignment == "Average Calculator"
    assert s.comparison_mode is ComparisonMode.STRICT
    assert [c.name for c in s.cases] == ["normal_values", "single_value", "negative_values"]


def test_defaults_are_strict_mode_empty_input_and_5s_timeout():
    s = parse_suite({"assignment": "A", "tests": [{"name": "t", "expected_output": ""}]})
    assert s.comparison_mode is ComparisonMode.STRICT
    assert s.cases[0].input == "" and s.cases[0].timeout_seconds == 5.0


@pytest.mark.parametrize("data, fragment", [
    ([], "Top level must be a JSON object"),
    ({"tests": [case()]}, "'assignment' is required"),
    (suite(assignment=""), "'assignment' is required"),
    (suite(extra=1), "unknown key"),
    (suite(tests=[]), "non-empty list"),
    (suite(tests="x"), "non-empty list"),
    (suite(tests=["x"]), "tests[0]: expected an object"),
    (suite(comparison="strict"), "'comparison' must be an object"),
    (suite(comparison={"mode": "fuzzy"}), "must be one of"),
    (suite(comparison={"mod": "strict"}), "unknown key"),
    (suite(tests=[case(name="")]), "'name' is required"),
    (suite(tests=[{"name": "t", "input": ""}]), "'expected_output' is required"),
    (suite(tests=[case(input=5)]), "'input' must be a string"),
    (suite(tests=[case(expected_output=None)]), "'expected_output' must be a string"),
    (suite(tests=[case(timeout_seconds=0)]), "'timeout_seconds'"),
    (suite(tests=[case(timeout_seconds=-1)]), "'timeout_seconds'"),
    (suite(tests=[case(timeout_seconds="2")]), "'timeout_seconds'"),
    (suite(tests=[case(timeout_seconds=True)]), "'timeout_seconds'"),
    (suite(tests=[case(timeout_seconds=10**6)]), "'timeout_seconds'"),
    (suite(tests=[case(timeout_seconds=float("inf"))]), "'timeout_seconds'"),
    (suite(tests=[case(timeout_seconds=None)]), "'timeout_seconds'"),
    (suite(tests=[case(timeout_second=2)]), "unknown key"),
    (suite(tests=[case(), case()]), "Duplicate test name"),
])
def test_invalid_suites_give_understandable_errors(data, fragment):
    with pytest.raises(SuiteFormatError) as info:
        parse_suite(data)
    assert fragment in str(info.value)


def test_error_names_the_offending_test():
    with pytest.raises(SuiteFormatError, match="tests\\[1\\] \\('second'\\)"):
        parse_suite(suite(tests=[case(), case(name="second", timeout_seconds=0)]))


def test_nan_timeout_rejected(tmp_path):
    path = tmp_path / "t.json"
    path.write_text('{"assignment":"A","tests":[{"name":"t","expected_output":"","timeout_seconds":NaN}]}')
    with pytest.raises(SuiteFormatError, match="timeout_seconds"):
        load_suite(path)


def test_malformed_json_reports_location(tmp_path):
    path = tmp_path / "t.json"
    path.write_text('{\n  "assignment": "A",\n  "tests": [\n')
    with pytest.raises(SuiteFormatError, match=r"Invalid JSON.*line \d+, column \d+"):
        load_suite(path)


def test_missing_file(tmp_path):
    with pytest.raises(SuiteFormatError, match="not found"):
        load_suite(tmp_path / "nope.json")


def test_non_utf8_file(tmp_path):
    path = tmp_path / "t.json"
    path.write_bytes(b"\xff\xfe\x00bad")
    with pytest.raises(SuiteFormatError, match="Could not read"):
        load_suite(path)


def test_errors_from_a_file_include_the_path(tmp_path):
    path = tmp_path / "t.json"
    path.write_text(json.dumps(suite(tests=[])))
    with pytest.raises(SuiteFormatError, match="t.json"):
        load_suite(path)


def test_multiple_cases_and_whitespace_preserved_exactly(tmp_path):
    path = tmp_path / "t.json"
    path.write_text(json.dumps({"assignment": "A", "tests": [
        {"name": "a", "input": "  1\t2 \n\n", "expected_output": " 3 \n\n"},
        {"name": "b", "expected_output": ""},
    ]}), encoding="utf-8")
    s = load_suite(path)
    assert [c.name for c in s.cases] == ["a", "b"]
    assert s.cases[0].input == "  1\t2 \n\n" and s.cases[0].expected_output == " 3 \n\n"
    assert s.cases[1].input == "" and s.cases[1].expected_output == ""


def test_bare_infinity_in_json_file_is_rejected(tmp_path):
    path = tmp_path / "t.json"
    path.write_text('{"assignment": "A", "tests": [{"name": "t", "expected_output": "", '
                    '"timeout_seconds": Infinity}]}')
    with pytest.raises(SuiteFormatError, match="timeout_seconds"):
        load_suite(path)


def test_directory_instead_of_file_is_a_clean_error(tmp_path):
    with pytest.raises(SuiteFormatError, match="Could not read"):
        load_suite(tmp_path)
