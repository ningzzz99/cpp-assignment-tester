"""Turn a GradeResult into a JSON report and write it to disk.

Pure serialization: nothing here compiles or runs code. Report format is
documented in docs/report-format.md.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from .models import CaseResult, CaseSpec, CompileResult, GradeResult, SuiteSpec

REPORT_SCHEMA_VERSION = 1


class ReportWriteError(OSError):
    """The report could not be serialized or written.

    This says nothing about the grading outcome; the GradeResult is unaffected.
    """


def _number(value: float | int | None) -> float | int | None:
    """JSON has no NaN/Infinity, so non-finite numbers become null."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _compile_section(compiled: CompileResult) -> dict[str, Any]:
    return {
        "status": compiled.status.value,
        "ok": compiled.ok,
        "has_warnings": compiled.has_warnings,
        "sanitizers": list(compiled.sanitizers),
        "command": list(compiled.command),
        "return_code": _number(compiled.returncode),
        "stdout": compiled.stdout,
        "diagnostics": compiled.stderr,  # compiler stderr, warnings included
        "elapsed_seconds": _number(compiled.elapsed_seconds),
    }


def _case_section(result: CaseResult, spec: CaseSpec | None) -> dict[str, Any]:
    return {
        "name": result.name,
        "passed": result.passed,
        "failure_category": result.category.value if result.category else None,
        "message": result.message,
        "input": spec.input if spec else None,
        "expected_output": spec.expected_output if spec else None,
        "actual_output": result.stdout,
        "stderr": result.stderr,
        "output_truncated": result.output_truncated,
        "output_matches": result.output_matches,
        "diff": result.diff,
        "exit_code": _number(result.exit_code),
        "signal": _number(result.signal),
        "timeout_seconds": _number(spec.timeout_seconds) if spec else None,
        "elapsed_seconds": _number(result.elapsed_seconds),
    }


def _outcome(grade: GradeResult) -> str:
    if not grade.compile.ok:
        return "compile_failed"
    if not grade.cases:
        return "no_tests"
    return "passed" if grade.passed else "failed"


def build_report(grade: GradeResult, suite: SuiteSpec | None = None) -> dict[str, Any]:
    """Return a JSON-serializable dict describing `grade`.

    Pass the `suite` that was graded to include each test's input, expected
    output and timeout; without it those fields are null. The report holds no
    timestamps or temp paths, so equal results give byte-identical reports.
    """
    specs = {case.name: case for case in suite.cases} if suite else {}
    categories = Counter(c.category.value for c in grade.cases if c.category)
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "assignment": grade.assignment,
        "outcome": _outcome(grade),
        "passed": grade.passed,
        "comparison_mode": suite.comparison_mode.value if suite else None,
        "total_elapsed_seconds": _number(grade.total_seconds),
        "compile": _compile_section(grade.compile),
        "summary": {
            "total": len(grade.cases),
            "passed": sum(c.passed for c in grade.cases),
            "failed": sum(not c.passed for c in grade.cases),
            "failures_by_category": dict(sorted(categories.items())),
        },
        "tests": [_case_section(c, specs.get(c.name)) for c in grade.cases],
    }


def report_to_json(report: dict[str, Any]) -> str:
    """Deterministic JSON text: sorted keys, 2-space indent, trailing newline."""
    try:
        return json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False,
                          allow_nan=False) + "\n"
    except (TypeError, ValueError) as exc:
        raise ReportWriteError(f"Report cannot be serialized to JSON: {exc}") from None


def write_report(report: dict[str, Any], path: Path | str) -> Path:
    """Write `report` to `path` atomically; raises ReportWriteError on failure.

    The text goes to a temp file in the same directory, is flushed to disk, and
    then renamed over `path`, so an interruption leaves either the previous
    report or none, never a partial one. Missing parent directories are created.
    """
    target = Path(path)
    text = report_to_json(report)  # serialize first: a bad report never touches disk
    tmp_name: str | None = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
        tmp_name = None
    except (OSError, UnicodeEncodeError) as exc:
        raise ReportWriteError(f"Could not write report to {target}: {exc}") from exc
    finally:
        if tmp_name is not None:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
    return target
