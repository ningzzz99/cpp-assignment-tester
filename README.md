# cppgrader — C++ Assignment Tester and AI Debugging Assistant

> **Status: early development (Phase 5).** Compilation, test loading, execution, JSON
> reports, a `grade` CLI and opt-in sanitizer mode exist; AI features do not yet.
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

## Grading from the command line
```bash
PYTHONPATH=src .venv/bin/python -m cppgrader.cli grade SOURCE.cpp TESTS.json [--report PATH] \
    [--sanitize address|undefined]... [--compile-timeout SECONDS]

# example
PYTHONPATH=src .venv/bin/python -m cppgrader.cli grade \
    examples/average_calculator/solution.cpp examples/average_calculator/tests.json \
    --report reports/average_calculator.json
```
`--help` lists the options. Output is one `PASS`/`FAIL` line per test (with a diff, and
stderr for failures) and a final `RESULT:` line; it only says `PASSED` if the program
compiled and every test passed. `--report` writes the JSON report atomically (replacing any
existing file); see [docs/report-format.md](docs/report-format.md).

| Exit code | Meaning |
|---|---|
| 0 | Compiled and every test passed |
| 1 | Grading failure: compile error, failed test(s), or a suite with no executed tests |
| 2 | Usage or tool/configuration error: bad arguments or test file, missing source or compiler, unusable sanitizer |
| 3 | Grading finished but the report could not be written (the result is still printed) |

### Sanitizer mode
`--sanitize undefined` and/or `--sanitize address` build with Clang's UndefinedBehavior and
AddressSanitizer plus `-fno-sanitize-recover=all` (so a detected defect aborts rather than
being printed and ignored). Without `--sanitize`, compilation is unchanged.
- Before grading, a tiny trusted probe program is built and run with the requested sanitizers.
  If that fails, the CLI exits 2 with the reason and grades nothing.
- A test fails as `sanitizer_error` when a sanitizer-format diagnostic appears on stderr **and**
  the program terminated abnormally (non-zero exit or signal; sanitized builds abort on a finding).
  Look-alike text from a program that exits 0 is not treated as a finding, so a program cannot
  fail (or be mistaken for failing) merely by printing "runtime error:". A program could still
  forge such text and then fail on purpose; that only makes it fail. Precedence:
  timeout, output limit, sanitizer, crash, non-zero exit, wrong output.
- If the sanitizer runtime itself cannot start (and the program exited abnormally), the test is a
  `runner_error`, not blamed on the program.
- `--report` refuses to overwrite the source or test file (exit 2).
- **Verified on the development machine (Apple clang 14.0.3):** UBSan works; AddressSanitizer
  builds but aborts at startup ("Interceptors are not working"), so the probe rejects it there.
  ASan has therefore not been exercised against real memory errors. Sanitizers add run-time
  and memory overhead and find defects in cooperative code; they are not a security measure.

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
