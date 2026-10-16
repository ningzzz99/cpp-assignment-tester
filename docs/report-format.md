# Report format (schema_version 1)

Produced by `cppgrader.report.build_report(grade, suite)`; written by `write_report`.
JSON is UTF-8, keys sorted, 2-space indent, trailing newline. No timestamps or temp
paths are included, so equal results give identical text. `NaN`/`Infinity` never
appear: non-finite numbers are written as `null`. `null` also means "not available".

| Field | Type | Notes |
|---|---|---|
| `schema_version` | int | Bumped on incompatible changes. |
| `assignment` | string | From the test suite. |
| `outcome` | string | `passed`, `failed`, `compile_failed`, or `no_tests`. |
| `passed` | bool | Compiled, at least one test, all tests passed. |
| `comparison_mode` | string/null | Null if no suite was given. |
| `total_elapsed_seconds` | number/null | Compile + all tests. |
| `compile.status` | string | A `CompileStatus` value, e.g. `success`, `compile_error`. |
| `compile.ok`, `compile.has_warnings` | bool | |
| `compile.sanitizers` | string[] | Sanitizers the build used (empty for an ordinary build). |
| `compile.command` | string[] | Argument list used. |
| `compile.return_code` | int/null | |
| `compile.stdout`, `compile.diagnostics` | string | Compiler stdout / stderr (warnings included). |
| `compile.elapsed_seconds` | number/null | |
| `summary.total/passed/failed` | int | |
| `summary.failures_by_category` | object | Count per failure category. |
| `tests[]` | array | One entry per executed test; empty if compilation failed. |

Each `tests[]` entry:

| Field | Type | Notes |
|---|---|---|
| `name`, `message` | string | |
| `passed` | bool | |
| `failure_category` | string/null | `wrong_output`, `non_zero_exit`, `crash`, `timeout`, `output_limit_exceeded`, `sanitizer_error`, `runner_error`; null when passed. |
| `input`, `expected_output` | string/null | Null if no suite was given. |
| `actual_output`, `stderr` | string | Possibly truncated (see `output_truncated`). |
| `output_matches` | bool/null | Null when output was not compared. |
| `diff` | string | Empty unless output differs. |
| `exit_code` | int/null | Null if killed by a signal or never started. |
| `signal` | int/null | Signal number if killed by one. |
| `timeout_seconds`, `elapsed_seconds` | number/null | |

Report-writing failures raise `ReportWriteError`; they do not change a grading result.
Reports contain full program output and compiler diagnostics, so treat them as sensitive.

Field additions are backward compatible and do not change `schema_version`.
