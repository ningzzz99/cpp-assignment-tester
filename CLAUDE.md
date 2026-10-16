# CLAUDE.md

Guidance for Claude Code in this repository. Keep it current as the project evolves.

## 1. Project overview

`cppgrader` compiles, runs and grades C++17 assignment submissions against JSON test cases, with planned optional local-AI explanations of failures. It is a development prototype and **not a sandbox**. See `README.md` for user-facing docs; do not duplicate them here.

## 2. Technology and environment

- Python >= 3.9, standard library only at runtime (`dependencies = []`); `pytest` is the only dev dependency.
- Target language for graded programs: C++17, compiled with Apple Clang (`clang++`) on macOS.
- Local virtualenv at `.venv/` (use `.venv/bin/python`). It is git-ignored.
- **Planned, not implemented:** local Ollama integration (model `qwen2.5-coder:1.5b`, README says Phase 8). No Ollama/AI code exists yet.

## 3. Architecture

Package `src/cppgrader/` (update this list when modules change):

| Module | Responsibility | Status |
|---|---|---|
| `prereqs.py` | Check Python/clang++, run a smoke test | implemented |
| `cli.py` | Entry point: `--check`, `--smoke`, `--version`, and `grade SOURCE TESTS [--report] [--sanitize] [--compile-timeout]` (exit 0 pass / 1 grading failure / 2 tool-config error / 3 report write failure) | implemented |
| `sanitizers.py` | Probe whether ASan/UBSan work (`check_sanitizer_support`), recognise sanitizer diagnostics (counted only with abnormal termination) | implemented |
| `compiler.py` | `compile_cpp()`: build a C++17 binary in a temp build dir, capture diagnostics, timeout | implemented |
| `models.py` | Shared dataclasses/enums (`CompileResult`, `SuiteSpec`, `CaseSpec`, `CaseResult`, `GradeResult`, `FailureCategory`, `ComparisonMode`) | implemented |
| `test_loader.py` | Parse/validate test-case JSON (`load_suite`, `parse_suite`); rejects unknown keys | implemented |
| `comparator.py` | `strict` / `normalized_whitespace` output comparison and diffs | implemented |
| `report.py` | `build_report`, `report_to_json`, `write_report` (atomic), `ReportWriteError`; format in `docs/report-format.md` | implemented |
| `runner.py` | `run_case`, `run_suite`, `grade_submission` (optional caller-owned `build_dir`): run binary with stdin, timeout, output cap, minimal env, signal/exit classification | implemented |

Not yet present: Ollama client. Sanitizer builds use `compile_cpp(..., sanitizers=...)`; AddressSanitizer does not run on the dev machine (UBSan does). `examples/average_calculator/` holds a sample solution and `tests.json`; `tests/fixtures/*.cpp` are small C++ programs used by the tests.

## 4. Development commands

Run from the repo root.

```bash
.venv/bin/python -m pytest                      # full suite (pytest config in pyproject.toml sets pythonpath=src)
.venv/bin/python -m pytest tests/test_runner.py # one file
PYTHONPATH=src .venv/bin/python -m cppgrader.cli --check          # verify prerequisites
PYTHONPATH=src .venv/bin/python -m cppgrader.cli --check --smoke  # also compile + run the example
PYTHONPATH=src .venv/bin/python -m cppgrader.cli grade examples/average_calculator/solution.cpp examples/average_calculator/tests.json [--report reports/x.json] [--sanitize undefined]
```

Installing the package or dev extras (`pip install -e ".[dev]"`) changes the environment; only do it if the user asks.

## 5. Coding standards

- Type-annotate all function signatures and dataclass fields; use `from __future__ import annotations` as existing modules do.
- Keep modules small and single-purpose; share types via `models.py`.
- Raise or return errors that say what went wrong and which field/file/command was involved (see `SuiteFormatError`, `CompileStatus`).
- Minimal dependencies: do not add runtime dependencies without asking.
- Subprocesses: always pass an argument **list**; **never use `shell=True`**. Always set a timeout and clean up the process group.

## 6. Testing rules

- Preserve existing tests; do not delete or weaken them to make code pass.
- Every bug fix gets a regression test that fails before the fix.
- Run the relevant tests after each change and the full suite before reporting completion.
- Never claim tests passed unless you ran them in this session; quote the actual result. Report failures and skipped steps plainly.
- Last verified: full suite, 133 passed, 1 skipped (`.venv/bin/python -m pytest`) when this file was written (2026-10-16).

## 7. Security requirements

- Timeouts, temp dirs, env scrubbing and output caps are **not a sandbox**. Compiled C++ runs with the user's privileges.
- Do not compile or execute arbitrary untrusted C++ code, and do not run student submissions that the user has not said are trusted. Only run code in `examples/`, `tests/fixtures/`, or that the user wrote or vouches for.
- AI output must never decide pass/fail; grading is deterministic (exit status, signal, timeout, output comparison).
- AI output must never modify a student's source file automatically; any suggested change needs explicit user approval.

## 8. Git rules

- Run `git status` before making changes and note pre-existing uncommitted work; do not revert or overwrite it.
- Do not commit (or push) unless explicitly asked.
- Never commit `.venv/`, `__pycache__/`, `.pytest_cache/`, `*.egg-info/`, compiled binaries (`*.o`, `*.out`, `*.dSYM/`), or generated reports (`reports/*` except `.gitkeep`). `.gitignore` covers these; check before staging.

## 9. Project roadmap

Phase numbers beyond 5 and 8 are not defined in the repository; do not invent them. Statuses reflect the repo and the last verified test run.

| Phase | Scope | Status |
|---|---|---|
| 1 | Project foundation, prerequisite check, smoke test CLI | complete (committed) |
| 2 | C++ compiler module | complete (committed) |
| 3 | Test-case loading, runner, output comparison, compile-then-run (`grade_submission`) | implemented and verified (82 passed, smoke check ok on 2026-10-16); committed |
| 4 | Structured JSON reports (`report.py`) | complete (committed; 102 passed when verified, 2026-10-16) |
| 5 | Grading CLI and sanitizer mode | implemented and verified (133 passed, 1 skipped (real-ASan test; ASan unusable here), smoke check ok, 2026-10-16); committed |
| 8 | Optional Ollama explanations (advisory only) | not started |

Update this table only from verified evidence, and never mark a phase complete merely because it was requested.

## 10. Working procedure

1. Inspect first: read the relevant code, tests and `git status` before editing.
2. Work in small phases; do only what the current request asks and **stop at the requested phase**.
3. Preserve working behavior; avoid unrelated refactors.
4. Test every change (relevant tests, then full suite).
5. Report actual results and known limitations honestly, including anything not run or not verified.
6. Keep `CLAUDE.md` (architecture, roadmap) and `README.md` in sync when structure or status changes.
