"""Run a compiled program against test cases.

WARNING: this is NOT a sandbox. Programs run with your user's privileges and can
read files, use the network and spawn processes. Run only code you trust. The
measures here (temp working directory, minimal environment, output-size limit,
process-group kill) limit accidents, not malicious code.
"""

from __future__ import annotations

import os
import resource
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Sequence

from .comparator import compare_output
from .compiler import DEFAULT_COMPILER, DEFAULT_TIMEOUT_SECONDS, compile_cpp
from .sanitizers import find_sanitizer_report, runtime_unusable
from .models import (
    CaseResult, CaseSpec, ComparisonMode, CompileResult, FailureCategory, GradeResult, SuiteSpec,
)

DEFAULT_MAX_OUTPUT_BYTES = 10 * 1024 * 1024
KILL_GRACE_SECONDS = 5.0
_CHILD_ENV = {"PATH": "/usr/bin:/bin", "LANG": "en_US.UTF-8"}  # nothing else is inherited


def _limit_child(max_output_bytes: int):
    def apply() -> None:
        # One byte of slack lets us tell "exactly at the limit" from "over it".
        resource.setrlimit(resource.RLIMIT_FSIZE, (max_output_bytes + 1, max_output_bytes + 1))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    return apply


def _kill_group(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def _read_capped(path: Path, cap: int) -> tuple[str, bool]:
    with open(path, "rb") as handle:
        data = handle.read(cap + 1)
    return data[:cap].decode("utf-8", errors="replace"), len(data) > cap


def _signal_name(number: int) -> str:
    try:
        return signal.Signals(number).name
    except ValueError:
        return f"signal {number}"


def run_case(
    binary: Path,
    case: CaseSpec,
    mode: ComparisonMode,
    *,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    sanitized: bool = False,
) -> CaseResult:
    """Run `binary` once on `case`. Never raises for expected failures.

    Set `sanitized` when the binary was built with sanitizers so that their
    diagnostics on stderr are recognised and fail the test.
    """
    def result(passed: bool, category: FailureCategory | None, message: str, elapsed: float,
               **kw) -> CaseResult:
        defaults = dict(exit_code=None, signal=None, stdout="", stderr="", output_truncated=False,
                        output_matches=None, diff="")
        defaults.update(kw)
        return CaseResult(case.name, passed, category, elapsed_seconds=elapsed, message=message,
                          **defaults)

    with tempfile.TemporaryDirectory(prefix="cppgrader-run-") as work_name:
        work = Path(work_name)
        out_path, err_path = work / "stdout.txt", work / "stderr.txt"
        start = time.perf_counter()
        timed_out = False
        with open(out_path, "wb") as out_file, open(err_path, "wb") as err_file:
            try:
                proc = subprocess.Popen(
                    [str(binary)], stdin=subprocess.PIPE, stdout=out_file, stderr=err_file,
                    cwd=work, env=_CHILD_ENV, start_new_session=True,
                    preexec_fn=_limit_child(max_output_bytes),
                )
            except OSError as exc:
                return result(False, FailureCategory.RUNNER_ERROR,
                              f"Could not start program: {exc}", time.perf_counter() - start)
            try:
                proc.communicate(input=case.input.encode("utf-8"), timeout=case.timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                _kill_group(proc.pid)
                proc.communicate()  # closes stdin and reaps the child
            except BaseException:
                _kill_group(proc.pid)
                proc.wait()
                raise
            elapsed = time.perf_counter() - start
            _kill_group(proc.pid)  # reap any grandchildren the program left behind

        stdout, out_truncated = _read_capped(out_path, max_output_bytes)
        stderr, err_truncated = _read_capped(err_path, max_output_bytes)

    truncated = out_truncated or err_truncated
    returncode = proc.returncode
    sig = -returncode if returncode < 0 else None
    exit_code = returncode if returncode >= 0 else None
    comparison = compare_output(case.expected_output, stdout, mode)
    common = dict(exit_code=exit_code, signal=sig, stdout=stdout, stderr=stderr,
                  output_truncated=truncated, output_matches=comparison.matches, diff=comparison.diff)

    # Precedence: a timeout, crash or bad exit fails the test even if the output matches.
    if timed_out:
        return result(False, FailureCategory.TIMEOUT,
                      f"Timed out after {case.timeout_seconds:g}s and was killed", elapsed, **common)
    if truncated or sig == signal.SIGXFSZ:
        common.update(output_matches=None, diff="")
        return result(False, FailureCategory.OUTPUT_LIMIT,
                      f"Produced more than {max_output_bytes} bytes of output", elapsed, **common)
    # Builds use -fno-sanitize-recover=all, so a real finding always ends the program
    # abnormally. Requiring that keeps a clean exit with look-alike stderr a plain pass.
    if sanitized and (sig is not None or exit_code != 0):
        if runtime_unusable(stderr):
            return result(False, FailureCategory.RUNNER_ERROR,
                          "The sanitizer runtime could not start on this system (not a defect in "
                          "the program); try a different --sanitize setting", elapsed, **common)
        report_line = find_sanitizer_report(stderr)
        if report_line is not None:
            return result(False, FailureCategory.SANITIZER,
                          f"Sanitizer reported: {report_line}", elapsed, **common)
    if sig is not None:
        return result(False, FailureCategory.CRASH,
                      f"Terminated by {_signal_name(sig)}", elapsed, **common)
    if exit_code != 0:
        return result(False, FailureCategory.NON_ZERO_EXIT,
                      f"Exited with code {exit_code}", elapsed, **common)
    if not comparison.matches:
        return result(False, FailureCategory.WRONG_OUTPUT, "Output differs from expected",
                      elapsed, **common)
    return result(True, None, "Passed", elapsed, **common)


def run_suite(
    compiled: CompileResult,
    suite: SuiteSpec,
    *,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
) -> list[CaseResult]:
    """Run every case against a *successful* compilation.

    Taking the CompileResult (not a path) means a failed compile cannot lead to
    running a stale binary: there is no binary_path to run.
    """
    if not compiled.ok or compiled.binary_path is None:
        raise ValueError(f"Cannot run tests: compilation did not succeed ({compiled.status.value})")
    return [run_case(compiled.binary_path, case, suite.comparison_mode,
                     max_output_bytes=max_output_bytes, sanitized=bool(compiled.sanitizers))
            for case in suite.cases]


def grade_submission(
    source: Path | str,
    suite: SuiteSpec,
    *,
    build_dir: Path | None = None,
    compiler: str = DEFAULT_COMPILER,
    compile_timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    sanitizers: Sequence[str] = (),
) -> GradeResult:
    """Compile `source` and run all cases, but only if *this* compilation succeeded.

    With no `build_dir` a temp directory is used and removed afterwards. A
    caller-provided `build_dir` is never deleted (CompileResult.cleanup only
    removes directories the compiler created), and any binary left there by an
    earlier build is removed before compiling, so it cannot be run.
    """
    start = time.perf_counter()
    compiled = compile_cpp(source, build_dir, compiler=compiler,
                           timeout_seconds=compile_timeout_seconds, sanitizers=sanitizers)
    try:
        cases = run_suite(compiled, suite, max_output_bytes=max_output_bytes) if compiled.ok else []
    finally:
        compiled.cleanup()
    return GradeResult(suite.assignment, compiled, cases, time.perf_counter() - start)
