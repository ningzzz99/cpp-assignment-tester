"""Command-line entry point (Phase 1: environment check and smoke test only).

Grading commands arrive in later phases.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .prereqs import check_prerequisites, smoke_test

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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

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
