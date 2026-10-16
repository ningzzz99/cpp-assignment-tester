"""Load and validate JSON test suites. See README for the format."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from .models import CaseSpec, ComparisonMode, SuiteSpec

DEFAULT_TIMEOUT_SECONDS = 5.0
MAX_TIMEOUT_SECONDS = 300.0
_TOP_KEYS = {"assignment", "comparison", "tests"}
_CASE_KEYS = {"name", "input", "expected_output", "timeout_seconds"}


class SuiteFormatError(ValueError):
    """The test file is missing, unreadable or malformed. The message is user-facing."""


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _unknown_keys(obj: dict, allowed: set[str], where: str) -> None:
    extra = sorted(set(obj) - allowed)
    if extra:
        raise SuiteFormatError(
            f"{where}: unknown key(s) {', '.join(map(repr, extra))}; allowed keys are {sorted(allowed)}"
        )


def _parse_case(raw: Any, index: int) -> CaseSpec:
    where = f"tests[{index}]"
    if not isinstance(raw, dict):
        raise SuiteFormatError(f"{where}: expected an object, got {type(raw).__name__}")
    name = raw.get("name")
    if isinstance(name, str) and name.strip():
        where = f"tests[{index}] ({name!r})"
    _unknown_keys(raw, _CASE_KEYS, where)

    if not isinstance(name, str) or not name.strip():
        raise SuiteFormatError(f"{where}: 'name' is required and must be a non-empty string")
    for key in ("input", "expected_output"):
        if key == "expected_output" and key not in raw:
            raise SuiteFormatError(f"{where}: 'expected_output' is required (use \"\" for no output)")
        if key in raw and not isinstance(raw[key], str):
            raise SuiteFormatError(f"{where}: '{key}' must be a string, got {type(raw[key]).__name__}")
    timeout = raw.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
    if not _is_number(timeout) or not math.isfinite(timeout) or not 0 < timeout <= MAX_TIMEOUT_SECONDS:
        raise SuiteFormatError(
            f"{where}: 'timeout_seconds' must be a number greater than 0 and at most "
            f"{MAX_TIMEOUT_SECONDS:g}, got {timeout!r}"
        )
    return CaseSpec(name, raw.get("input", ""), raw["expected_output"], float(timeout))


def parse_suite(data: Any) -> SuiteSpec:
    if not isinstance(data, dict):
        raise SuiteFormatError(f"Top level must be a JSON object, got {type(data).__name__}")
    _unknown_keys(data, _TOP_KEYS, "Test file")

    assignment = data.get("assignment")
    if not isinstance(assignment, str) or not assignment.strip():
        raise SuiteFormatError("'assignment' is required and must be a non-empty string")

    mode = ComparisonMode.STRICT
    if "comparison" in data:
        comparison = data["comparison"]
        if not isinstance(comparison, dict):
            raise SuiteFormatError("'comparison' must be an object like {\"mode\": \"strict\"}")
        _unknown_keys(comparison, {"mode"}, "'comparison'")
        raw_mode = comparison.get("mode", ComparisonMode.STRICT.value)
        try:
            mode = ComparisonMode(raw_mode)
        except ValueError:
            valid = [m.value for m in ComparisonMode]
            raise SuiteFormatError(f"'comparison.mode' must be one of {valid}, got {raw_mode!r}") from None

    raw_tests = data.get("tests")
    if not isinstance(raw_tests, list) or not raw_tests:
        raise SuiteFormatError("'tests' is required and must be a non-empty list")
    cases = tuple(_parse_case(raw, i) for i, raw in enumerate(raw_tests))

    seen: set[str] = set()
    for case in cases:
        if case.name in seen:
            raise SuiteFormatError(f"Duplicate test name {case.name!r}; names must be unique")
        seen.add(case.name)
    return SuiteSpec(assignment, mode, cases)


def load_suite(path: Path | str) -> SuiteSpec:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise SuiteFormatError(f"Test file not found: {path}") from None
    except (OSError, UnicodeDecodeError) as exc:
        raise SuiteFormatError(f"Could not read test file {path}: {exc}") from None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SuiteFormatError(
            f"Invalid JSON in {path}: {exc.msg} (line {exc.lineno}, column {exc.colno})"
        ) from None
    try:
        return parse_suite(data)
    except SuiteFormatError as exc:
        raise SuiteFormatError(f"{path}: {exc}") from None
