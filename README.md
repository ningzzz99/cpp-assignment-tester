# cppgrader — C++ Assignment Tester and AI Debugging Assistant

A small, dependency-free Python tool that compiles a C++17 submission with Clang, runs it
against JSON-defined test cases, and reports a deterministic verdict per test. It can
optionally build with sanitizers, write a structured JSON report, and ask a **local**
Ollama model for debugging *suggestions* (never part of the grade).

> **⚠️ Security: this is NOT a sandbox.** It compiles and executes native code with your
> user's privileges (files, network, processes). Timeouts, a temporary working directory, a
> minimal environment and an output-size limit reduce accidents; they do not contain malicious
> code. **Only run code you wrote or trust. Never run untrusted student submissions with this tool.**

## Highlights
- **Deterministic grading** — compiler status, exit code / signal, timeout and exact output
  comparison decide pass/fail. A crash, non-zero exit or timeout fails a test even if its output matches.
- **Safe-by-construction process handling** — argument lists only (no `shell=True`), process-group
  kills on timeout, output caps, scrubbed environment, no stale-binary execution after a failed compile.
- **Sanitizer mode** — opt-in UBSan/ASan builds with a toolchain probe and clear failure categories.
- **JSON reports** — documented schema, deterministic output, atomic writes.
- **Optional local AI** — Ollama (`qwen2.5-coder:1.5b`) over loopback only; off by default, advisory only,
  and its failures can never change a grade or exit code.
- Standard library only at runtime; 200+ pytest tests that need neither Ollama nor network.

## Architecture
```
 tests.json ──► test_loader ─┐
                             ├─► runner.grade_submission ──► GradeResult ──► report (JSON)
 solution.cpp ─► compiler ───┘        │  (comparator, sanitizers)               │
                                      └──────────────► cli ◄───────────────────┘
                                                        └─(optional, after grading)─► ai ─► local Ollama
```
| Module (`src/cppgrader/`) | Responsibility |
|---|---|
| `cli.py` | Entry point: `--check`, `--smoke`, `--version`, `grade …`; exit codes |
| `compiler.py` | `compile_cpp`: C++17 build in a temp/caller build dir, diagnostics, timeout, stale-binary removal |
| `test_loader.py` | Parse and validate the JSON test-suite format |
| `runner.py` | Run a binary per test (stdin, timeout, output cap), classify failures, `grade_submission` |
| `comparator.py` | `strict` / `normalized_whitespace` comparison and readable diffs |
| `sanitizers.py` | Probe ASan/UBSan support; recognise sanitizer diagnostics |
| `report.py` | Build and atomically write the JSON report |
| `ai.py` | Optional Ollama client and bounded prompt construction (advisory only) |
| `models.py`, `prereqs.py` | Shared result types; prerequisite check and smoke test |

## Requirements
- **macOS with Apple Clang** (`xcode-select --install`). Developed and verified on macOS with
  Apple clang 14.0.3. The runner uses POSIX APIs, so Windows is not supported; other Unix systems
  with `clang++` are untested.
- **Python 3.9+** declared in `pyproject.toml`. Verified on 3.13 (development) and 3.10 (fresh virtualenv:
  install, console script, smoke check and full suite). 3.9 itself was not tested.
- Optional, only for `--ai`: [Ollama](https://ollama.com) and the `qwen2.5-coder:1.5b` model.

## Quick start
```bash
git clone <this repository> && cd cpp-assignment-tester
python3 -m venv .venv
source .venv/bin/activate                 # or call .venv/bin/python directly
python -m pip install --upgrade pip       # old pip (< 21.3) cannot do editable installs
python -m pip install -e ".[dev]"         # installs cppgrader + pytest

cppgrader --version
cppgrader --check --smoke                 # verify Python/clang++, compile + run the example
python -m pytest -v                       # run the test suite

# grade the included example and write a JSON report (reports/ is git-ignored)
cppgrader grade examples/average_calculator/solution.cpp \
                examples/average_calculator/tests.json --report reports/average_calculator.json
```
Without installing, every command also works as
`PYTHONPATH=src python3 -m cppgrader.cli …` from the repository root.

### Try the failure demos
```bash
cppgrader grade examples/faulty_programs/wrong_answer.cpp   examples/average_calculator/tests.json   # exit 1: 2 pass, 1 fails with a diff
cppgrader grade examples/faulty_programs/compile_error.cpp  examples/average_calculator/tests.json   # exit 1: NOT GRADED, compiler errors shown
cppgrader grade examples/faulty_programs/ubsan_overflow.cpp examples/faulty_programs/ubsan_tests.json                      # exit 0: UB goes unnoticed
cppgrader grade examples/faulty_programs/ubsan_overflow.cpp examples/faulty_programs/ubsan_tests.json --sanitize undefined # exit 1: sanitizer_error
```

## The `grade` command
```
cppgrader grade SOURCE.cpp TESTS.json [--report PATH] [--sanitize address|undefined]...
                [--compile-timeout SECONDS] [--ai [--ai-model NAME] [--ai-endpoint URL]
                 [--ai-timeout SECONDS] [--ai-include-source]]
```
Output is one `PASS`/`FAIL` line per test (with a diff and stderr for failures) and a final
`RESULT:` line, which says `PASSED` only if the program compiled and every test passed.
`--report` writes the JSON report atomically, replacing an existing file, and refuses to
overwrite the source or test file. `cppgrader grade --help` lists every option.

| Exit code | Meaning |
|---|---|
| 0 | Compiled and every test passed |
| 1 | Grading failure: compile error (or compile timeout), failed test(s), or a suite with no executed tests |
| 2 | Usage or tool/configuration error: bad arguments or test file, missing source or compiler, unusable sanitizer, invalid or non-local `--ai-endpoint` |
| 3 | Grading finished but the report could not be written (the result is still printed) |

`--check` exits 1 if a prerequisite is missing. AI suggestions never change the exit code.

### Test-case JSON format
```json
{
  "assignment": "Average Calculator",
  "comparison": { "mode": "strict" },
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

Unknown keys are rejected so typos are not silently ignored; malformed files give an error naming
the field. **Comparison modes:** `strict` is byte-for-byte; `normalized_whitespace` collapses runs of
ASCII whitespace (including newlines) and trims the ends, so it is **inappropriate** where layout
matters (tables, one-item-per-line output, ASCII art).

**Verdict rules.** A test passes only if the program exits with code 0, is not killed by a signal,
finishes within its timeout, stays under the output limit (10 MiB), and its stdout matches.
Failure categories: `wrong_output`, `non_zero_exit`, `crash`, `timeout`, `output_limit_exceeded`,
`sanitizer_error`, `runner_error`.

### Sanitizer mode
`--sanitize undefined` and/or `--sanitize address` build with Clang's UBSan / ASan plus
`-fno-sanitize-recover=all`, so a detected defect aborts instead of being printed and ignored.
Without `--sanitize`, compilation is unchanged.
- Before grading, a tiny trusted probe program is built and run with the requested sanitizers; if it
  fails the CLI exits 2 with the reason and grades nothing.
- A test fails as `sanitizer_error` when a sanitizer-format diagnostic appears on stderr **and** the
  program terminated abnormally. Look-alike text from a program that exits 0 is not a finding. A
  program can forge such text and then fail on purpose; that only makes it fail. Precedence: timeout,
  output limit, sanitizer, crash, non-zero exit, wrong output.
- If the sanitizer runtime itself cannot start, the test is a `runner_error`, not blamed on the program.
- **Verified here (Apple clang 14.0.3):** UBSan works end to end. AddressSanitizer builds but aborts at
  startup ("Interceptors are not working"), so the probe rejects it on this machine and ASan has **not**
  been exercised against real memory errors; the real-ASan test is skipped automatically. Sanitizers add
  overhead and find defects in cooperative code; they are not a security measure.

### JSON reports
`--report PATH` (or `cppgrader.report.build_report` / `write_report` in Python) produces a deterministic
document (sorted keys, no timestamps, `null` for unavailable values) with compile status and diagnostics,
per-test input / expected / actual output, stderr, exit code, signal, failure category and timings. The
field reference is [docs/report-format.md](docs/report-format.md). Reports contain full program output, so
treat them as sensitive. A write failure raises `ReportWriteError` / exits 3 and never alters the grade.

## Optional local AI debugging suggestions
Grading is always local and deterministic. `--ai` additionally asks a **local** model for
*suggestions* about a compile error or failed tests. The text is advice from a small language
model: it can be wrong, is never part of the grade, and **never changes results, the report, exit
codes, or your files**. It is off by default; the tool never downloads a model or starts Ollama.

**One-time setup:**
```bash
# install Ollama from https://ollama.com, then:
ollama serve                    # leave running (if not already started by the Ollama app)
ollama pull qwen2.5-coder:1.5b  # ~1 GB download
```
**Use:**
```bash
cppgrader grade examples/faulty_programs/compile_error.cpp examples/average_calculator/tests.json --ai
cppgrader grade examples/faulty_programs/wrong_answer.cpp  examples/average_calculator/tests.json --ai
```
| Option | Meaning |
|---|---|
| `--ai` | Request suggestions after grading (a compile error, or up to 3 failed tests) |
| `--ai-model NAME` | Model (default `qwen2.5-coder:1.5b`, or env `CPPGRADER_OLLAMA_MODEL`) |
| `--ai-endpoint URL` | Ollama URL (default `http://localhost:11434`, or env `CPPGRADER_OLLAMA_URL`) |
| `--ai-timeout SECONDS` | Per-request limit, enforced as an overall deadline on the response (default 120) |
| `--ai-include-source` | Also send the first 60 lines of the source when explaining failed tests |

**Privacy.** Only loopback endpoints (`localhost`, `127.0.0.1`, `::1`, plain `http`) are accepted;
anything else is a usage error (exit 2) and nothing is graded. A hostname such as `localhost` must
resolve only to loopback addresses (checked once when the client is created; a resolver that changes
its answer later is out of scope). Redirects are not followed and proxy environment variables are
ignored. What is sent: compiler diagnostics (capped at 4000 characters) plus source lines around the
reported errors; for failed tests the test input, expected and actual output, diff and stderr (1000
characters each); the source itself only with `--ai-include-source`. Prompts label all of it as
untrusted data, but a small model can still be steered by hostile text in a submission, so treat
output as advice only. Model output is stripped of control and formatting characters before printing,
and the response size is capped while it is read. Ctrl-C during suggestions skips them and keeps the
grading exit code.

**Behavior.** Suggestions print after the `RESULT:` line (and after the report is written). If Ollama is
unreachable, times out, lacks the model or returns garbage, a one-line "AI suggestion unavailable"
message goes to stderr and the exit code is unchanged. If the server is down only one request is made.

**Quality and speed.** On the development machine, requests took roughly 45–85 s (the first loads the
model), and the 1.5B model's advice was often generic and sometimes wrong (for example, suggesting a
header that was already included). The compiler diagnostics printed above the suggestions are authoritative.

**Troubleshooting.** *Could not reach Ollama*: run `ollama serve`. *Model not available*:
`ollama pull qwen2.5-coder:1.5b`. *Timed out*: raise `--ai-timeout`. *Refusing non-local endpoint*: use a
loopback URL.

## Python API
```python
from cppgrader.test_loader import load_suite
from cppgrader.runner import grade_submission
from cppgrader.report import build_report, write_report

suite = load_suite("examples/average_calculator/tests.json")   # raises SuiteFormatError
grade = grade_submission("examples/average_calculator/solution.cpp", suite)
if not grade.compile.ok:
    print(grade.compile.status.value, grade.compile.stderr)    # no tests were run
for case in grade.cases:
    print(case.name, "PASS" if case.passed else case.category.value, case.message)
write_report(build_report(grade, suite), "reports/example.json")
```
`grade_submission` runs tests only if *that* compilation succeeded. Pass `build_dir=` to keep the build
directory (it is never deleted; a temp one is removed afterwards); any older `program` in it is removed
before compiling, so a failed compile cannot run a stale binary. `sanitizers=[...]` enables sanitizer builds.

## Testing
```bash
python -m pytest -v        # from the activated .venv; or .venv/bin/python -m pytest -v
```
The suite needs only Python and `clang++`: Ollama is exercised against a fake loopback server, with one
optional real-Ollama round trip that skips cleanly when the model is unavailable. Expected skips: the real
AddressSanitizer test when ASan cannot run (as on the development Mac).

## Known limitations
- Not safe for untrusted submissions; subprocess timeouts are not a sandbox. Grades only the stdout,
  exit status and timing of single-file C++17 programs.
- ASan is unverified on the development machine (see Sanitizer mode); UBSan is verified.
- AI suggestions come from a small local model and are unverified; each request can take a minute or more.
- `--ai` timeouts are an overall response deadline, but a single blocking read can overrun it by up to one socket timeout.
- No CI configuration is included; tests were run locally (macOS, Python 3.13 and 3.10).

## Possible future work
Multi-file projects, a stdin/argument-driven batch mode for many submissions (inside a real sandbox),
AI text in reports, Linux/CI support.

## License
No license has been chosen yet, so by default all rights are reserved by the author. Add a `LICENSE`
file before inviting reuse or contributions.
