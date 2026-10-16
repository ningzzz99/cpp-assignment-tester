"""Sanitizer support: detect usable toolchains and recognise sanitizer diagnostics.

WARNING: like the rest of the tool this is NOT a sandbox. A sanitizer finds
defects in well-meaning code; it does not contain malicious code.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path
from typing import NamedTuple, Sequence

from .compiler import DEFAULT_COMPILER, compile_cpp

PROBE_TIMEOUT_SECONDS = 30.0
_PROBE_SOURCE = (
    "#include <cstdlib>\n"
    "int main() { void* p = std::malloc(8); std::free(p); return 0; }\n"
)
_PROBE_ENV = {"PATH": "/usr/bin:/bin", "LANG": "en_US.UTF-8"}

# Patterns are anchored to the formats the sanitizer runtimes emit, so ordinary
# program messages that merely contain "runtime error:" are not matched.
# A program can still print forged text, which is why the runner also requires
# abnormal termination (builds use -fno-sanitize-recover=all, so real findings abort).
_RUNTIME_UNUSABLE = re.compile(r"^==\d+==ERROR: Interceptors are not working", re.M)
_FIRST_REPORT = re.compile(
    r"^(?:==\d+==ERROR: (?:Address|Leak|Undefined)Sanitizer"
    r"|\S.*:\d+:\d+: runtime error: "
    r"|SUMMARY: (?:Address|Leak|Undefined)\w*Sanitizer).*$",
    re.M,
)


class SanitizerSupport(NamedTuple):
    ok: bool
    message: str


def runtime_unusable(stderr: str) -> bool:
    """True if stderr shows the sanitizer runtime itself failed to start."""
    return bool(_RUNTIME_UNUSABLE.search(stderr))


def find_sanitizer_report(stderr: str) -> str | None:
    """First line of a sanitizer diagnostic in `stderr`, or None.

    Only meaningful for output of an instrumented build, and only together with
    abnormal termination (see runner.run_case).
    """
    match = _FIRST_REPORT.search(stderr)
    return match.group(0).strip() if match else None


def check_sanitizer_support(
    sanitizers: Sequence[str], compiler: str = DEFAULT_COMPILER
) -> SanitizerSupport:
    """Build and run a tiny trusted program with `sanitizers` to see if they work here.

    Returns (ok, message). Never raises for toolchain problems.
    """
    names = ", ".join(sanitizers)
    with tempfile.TemporaryDirectory(prefix="cppgrader-probe-") as tmp:
        source = Path(tmp) / "probe.cpp"
        source.write_text(_PROBE_SOURCE, encoding="utf-8")
        result = compile_cpp(source, compiler=compiler, sanitizers=sanitizers,
                             timeout_seconds=PROBE_TIMEOUT_SECONDS)
        try:
            if not result.ok:
                detail = result.stderr.strip().splitlines()[:5]
                return SanitizerSupport(False, (
                    f"Could not build a test program with sanitizer(s) {names} "
                    f"({result.status.value}):\n  " + "\n  ".join(detail)))
            try:
                run = subprocess.run([str(result.binary_path)], stdin=subprocess.DEVNULL,
                                     capture_output=True, text=True, errors="replace",
                                     env=_PROBE_ENV, cwd=tmp, timeout=PROBE_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                return SanitizerSupport(False, f"The sanitizer probe program ({names}) timed out.")
            except OSError as exc:
                return SanitizerSupport(False, f"Could not run the sanitizer probe program: {exc}")
        finally:
            result.cleanup()
    if run.returncode != 0 or runtime_unusable(run.stderr) or find_sanitizer_report(run.stderr):
        detail = (run.stderr.strip().splitlines() or ["(no output)"])[0]
        return SanitizerSupport(False, (
            f"Sanitizer(s) {names} build but do not run correctly with this toolchain "
            f"(exit status {run.returncode}): {detail}"))
    return SanitizerSupport(True, f"Sanitizer(s) {names} are usable.")
