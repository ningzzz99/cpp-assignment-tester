"""Command-line entry point: environment checks and the `grade` command.

WARNING: `grade` compiles and runs the submission with your user's privileges.
Timeouts are not a sandbox. Only grade code you trust.

Exit codes: 0 all tests passed (or checks ok); 1 grading failure (compile error,
failed test, or no tests); 2 usage/configuration/tool error (bad arguments or
test file, source or compiler missing, sanitizers unusable); 3 the report could
not be written (grading itself completed; its result is still printed).
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

from . import __version__
from .compiler import SUPPORTED_SANITIZERS
from .models import CompileStatus, GradeResult
from .prereqs import check_prerequisites, smoke_test
from .report import ReportWriteError, build_report, write_report
from .runner import grade_submission
from .sanitizers import check_sanitizer_support
from .test_loader import SuiteFormatError, load_suite

EXIT_OK, EXIT_GRADING_FAILED, EXIT_ERROR, EXIT_REPORT_FAILED = 0, 1, 2, 3
# Compile outcomes that are the tool's or caller's problem, not the submission's.
_TOOL_ERRORS = {CompileStatus.SOURCE_NOT_FOUND, CompileStatus.COMPILER_UNAVAILABLE,
                CompileStatus.BUILD_DIR_ERROR}
MAX_SHOWN_CHARS = 1500

REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE_SOURCE = REPO_ROOT / "examples" / "average_calculator" / "solution.cpp"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cppgrader",
        description="C++17 assignment grader (development prototype; not a sandbox).",
    )
    parser.add_argument("--version", action="version", version=f"cppgrader {__version__}")
    parser.add_argument("--check", action="store_true", help="verify Python and clang++ are available")
    parser.add_argument("--smoke", action="store_true", help="compile and run the bundled example once")
    commands = parser.add_subparsers(dest="command", metavar="COMMAND")
    grade = commands.add_parser(
        "grade", help="compile a C++ source file and grade it against a JSON test suite",
        description="Compile SOURCE (C++17) and run it against the tests in TESTS_JSON. "
                    "Runs the program with your privileges: timeouts are NOT a sandbox, "
                    "so only grade code you trust.",
    )
    grade.add_argument("source", type=Path, help="C++ source file to grade")
    grade.add_argument("tests", type=Path, metavar="TESTS_JSON", help="JSON test suite (see README)")
    grade.add_argument("--report", type=Path, metavar="PATH",
                       help="also write a JSON report here (atomic; replaces an existing file)")
    grade.add_argument("--sanitize", action="append", choices=SUPPORTED_SANITIZERS, default=[],
                       metavar="NAME", help="build with a sanitizer (repeatable): "
                       f"{', '.join(SUPPORTED_SANITIZERS)}. Checked for toolchain support first")
    grade.add_argument("--compile-timeout", type=float, default=60.0, metavar="SECONDS",
                       help="compiler time limit (default: 60)")
    return parser


def _same_file(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve() or (a.exists() and b.exists() and a.samefile(b))
    except OSError:
        return False


def _clip(text: str) -> str:
    text = text.rstrip("\n")
    return text if len(text) <= MAX_SHOWN_CHARS else text[:MAX_SHOWN_CHARS] + "\n... (truncated)"


def _indent(text: str) -> str:
    return "\n".join("      " + line for line in _clip(text).splitlines())


def _print_grade(grade: GradeResult) -> None:
    compiled = grade.compile
    if not compiled.ok:
        print(f"COMPILATION FAILED ({compiled.status.value})")
        if compiled.stderr.strip():
            print(_clip(compiled.stderr))
        print("RESULT: NOT GRADED - no tests were run")
        return
    mode = f" with sanitizers: {', '.join(compiled.sanitizers)}" if compiled.sanitizers else ""
    print(f"Compiled successfully{mode}.")
    if compiled.has_warnings:
        print("Compiler warnings:\n" + _clip(compiled.stderr))
    for case in grade.cases:
        if case.passed:
            print(f"  PASS  {case.name} ({case.elapsed_seconds:.2f}s)")
            continue
        print(f"  FAIL  {case.name} [{case.category.value}]: {case.message}")
        if case.diff:
            print(_indent(case.diff))
        if case.stderr.strip():
            print("    stderr:\n" + _indent(case.stderr))
    passed = sum(c.passed for c in grade.cases)
    verdict = "PASSED" if grade.passed else "FAILED"
    print(f"RESULT: {verdict} ({passed}/{len(grade.cases)} tests passed)")


def run_grade(args: argparse.Namespace) -> int:
    if not (math.isfinite(args.compile_timeout) and args.compile_timeout > 0):
        print("error: --compile-timeout must be a finite number greater than 0", file=sys.stderr)
        return EXIT_ERROR
    if args.report is not None:
        # The report is written by atomic replace; never let that clobber an input file.
        for role, path in (("source file", args.source), ("test file", args.tests)):
            if _same_file(args.report, path):
                print(f"error: --report would overwrite the {role} ({path}); choose another path",
                      file=sys.stderr)
                return EXIT_ERROR
    try:
        suite = load_suite(args.tests)
    except SuiteFormatError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    sanitizers = tuple(dict.fromkeys(args.sanitize))
    if sanitizers:
        support = check_sanitizer_support(sanitizers)
        if not support.ok:
            print(f"error: {support.message}\nNothing was graded. Retry without --sanitize "
                  "or with a sanitizer that works here (e.g. --sanitize undefined).", file=sys.stderr)
            return EXIT_ERROR
    print("Note: the program runs with your privileges; timeouts are not a sandbox. "
          "Only grade code you trust.", file=sys.stderr)

    grade = grade_submission(args.source, suite, compile_timeout_seconds=args.compile_timeout,
                             sanitizers=sanitizers)
    if grade.compile.status in _TOOL_ERRORS:
        print(f"error: {grade.compile.stderr.strip()}", file=sys.stderr)
        return EXIT_ERROR
    _print_grade(grade)

    if args.report is not None:
        try:
            write_report(build_report(grade, suite), args.report)
            print(f"Report written to {args.report}")
        except ReportWriteError as exc:
            print(f"error: grading completed but the report was not saved: {exc}", file=sys.stderr)
            return EXIT_REPORT_FAILED
    return EXIT_OK if grade.passed else EXIT_GRADING_FAILED


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "grade":
        if args.check or args.smoke:
            parser.error("--check/--smoke cannot be combined with a command")
        return run_grade(args)
    if not (args.check or args.smoke):
        parser.print_help()
        return 0

    exit_code = 0
    if args.check:
        for status in check_prerequisites():
            print(f"[{'ok' if status.found else 'MISSING'}] {status.name}: {status.detail}")
            if not status.found:
                exit_code = 1
    if args.smoke and exit_code == 0:
        passed, message = smoke_test(SMOKE_SOURCE, "4\n2 4 6 8\n", "5\n")
        print(f"[{'ok' if passed else 'FAIL'}] smoke: {message}")
        exit_code = 0 if passed else 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
