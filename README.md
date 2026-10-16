# cppgrader — C++ Assignment Tester and AI Debugging Assistant

> **Status: early development (Phase 3).** Compilation, test loading and execution
> exist as library modules; the grading CLI, reports, sanitizers and AI features do not yet.
>
> **⚠️ Security: this is a development prototype and NOT a sandbox.** It compiles and
> executes native code with your user's privileges (files, network, processes).
> Timeouts, a temp working directory, a minimal environment and an output-size
> limit reduce accidents; they do not contain malicious code. **Only run code you
> wrote or trust. Never run untrusted student submissions with this tool.**

## Problem statement and motivation
_TODO_

## Features and architecture
_TODO (planned: compiler, runner, comparator, reporter, sanitizer mode, optional Ollama explanations)_

## Prerequisites (macOS)
- Python 3.9+
- Apple Clang: `xcode-select --install`
- Optional: [Ollama](https://ollama.com) with `qwen2.5-coder:1.5b` (later phases)

## Setup and usage
From the repository root:

```bash
PYTHONPATH=src python3 -m cppgrader.cli --check          # verify prerequisites
PYTHONPATH=src python3 -m cppgrader.cli --check --smoke  # also compile + run the example
```

## Test-case JSON format
```json
{
  "assignment": "Average Calculator",
  "comparison": { "mode": "normalized_whitespace" },
  "tests": [
    { "name": "normal_values", "input": "4\n2 4 6 8\n", "expected_output": "5\n", "timeout_seconds": 2 }
  ]
}
```
| Field | Required | Notes |
|---|---|---|
| `assignment` | yes | Non-empty string. |
| `comparison.mode` | no | `strict` (default) or `normalized_whitespace`. |
| `tests[].name` | yes | Unique, non-empty. |
| `tests[].input` | no | Sent on stdin; defaults to `""`. |
| `tests[].expected_output` | yes | Use `""` to expect no output. |
| `tests[].timeout_seconds` | no | Number in (0, 300]; default 5. |

Unknown keys are rejected so typos are not silently ignored. Malformed files give an error naming the field.

**Comparison modes.** `strict` requires byte-for-byte equality. `normalized_whitespace`
collapses runs of ASCII whitespace (spaces, tabs, newlines) to one space and trims the
ends. It therefore ignores line structure, which is **inappropriate** for assignments
where layout matters (tables, one-item-per-line output, ASCII art).

**Verdict rules.** A test passes only if the program exits with code 0, is not killed by
a signal, finishes within its timeout, stays under the output-size limit (10 MiB), and
its stdout matches. A crash, non-zero exit or timeout fails the test even if the output matches.

## Compiling and running tests (Python API)
There is no grading CLI yet (the CLI only has `--check`/`--smoke`), so use the library:

```python
from cppgrader.test_loader import load_suite, SuiteFormatError
from cppgrader.runner import grade_submission

suite = load_suite("examples/average_calculator/tests.json")   # raises SuiteFormatError
grade = grade_submission("examples/average_calculator/solution.cpp", suite)
if not grade.compile.ok:
    print(grade.compile.status.value, grade.compile.stderr)    # no tests were run
for case in grade.cases:
    print(case.name, "PASS" if case.passed else case.category.value, case.message)
```
Run with `PYTHONPATH=src .venv/bin/python script.py`. Loading only parses JSON; nothing is executed.

`grade_submission` runs tests **only if that compilation succeeded**. Pass `build_dir=` to
keep the build directory; it is never deleted (a temp one is removed afterwards), and any
older `program` in it is deleted before compiling, so a failed compile cannot run a stale binary.

**How failures are represented** (`CaseResult.category`; `None` when passed):
`wrong_output` (stdout differs, `diff` shows how), `non_zero_exit`, `crash` (killed by a
signal, `signal` is set), `timeout` (killed after `timeout_seconds`),
`output_limit_exceeded`, `runner_error` (e.g. binary missing). `exit_code`, `stdout`,
`stderr` and `elapsed_seconds` are kept whenever available. Compile problems are in
`GradeResult.compile` (`CompileStatus`), kept separate from per-test results.

## JSON reports
```python
from cppgrader.report import build_report, write_report, ReportWriteError

report = build_report(grade, suite)            # plain dict; `suite` adds input/expected output
try:
    write_report(report, "reports/average_calculator.json")   # atomic; reports/ is git-ignored
except ReportWriteError as exc:
    print("grading finished, but the report was not saved:", exc)
```
Reports are deterministic (sorted keys, no timestamps), use `null` for unavailable values
and non-finite numbers, and contain full program output, so treat them as sensitive.
A write failure raises `ReportWriteError` and never alters the grading result. The field
reference is in [docs/report-format.md](docs/report-format.md). There is no CLI command for reports yet.

## Ollama integration
_TODO (Phase 8)_

## Running tests and benchmarks
```bash
python3 -m pip install -e ".[dev]"   # installs pytest (once)
.venv/bin/python -m pytest -v
```

## Known limitations and security considerations
- Not safe for untrusted submissions; subprocess timeouts are not a sandbox.

## Future improvements
_TODO_

## License
_To be chosen._
