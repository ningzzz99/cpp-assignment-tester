"""Shared result types."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class CompileStatus(str, Enum):
    SUCCESS = "success"
    COMPILE_ERROR = "compile_error"
    TIMEOUT = "timeout"
    COMPILER_UNAVAILABLE = "compiler_unavailable"
    SOURCE_NOT_FOUND = "source_not_found"
    BUILD_DIR_ERROR = "build_dir_error"


@dataclass
class CompileResult:
    status: CompileStatus
    command: list[str]
    returncode: int | None
    stdout: str
    stderr: str  # compiler diagnostics, including warnings; never discarded
    elapsed_seconds: float
    binary_path: Path | None = None
    build_dir: Path | None = None
    _owns_build_dir: bool = field(default=False, repr=False)
    sanitizers: tuple[str, ...] = ()  # sanitizers the binary was instrumented with

    @property
    def ok(self) -> bool:
        return self.status is CompileStatus.SUCCESS

    @property
    def has_warnings(self) -> bool:
        """True when compilation succeeded but the compiler emitted diagnostics."""
        return self.ok and bool(self.stderr.strip())

    def cleanup(self) -> None:
        """Remove the build directory, but only if this module created it."""
        if self._owns_build_dir and self.build_dir is not None:
            shutil.rmtree(self.build_dir, ignore_errors=True)


class ComparisonMode(str, Enum):
    STRICT = "strict"
    NORMALIZED_WHITESPACE = "normalized_whitespace"


@dataclass(frozen=True)
class CaseSpec:
    name: str
    input: str
    expected_output: str
    timeout_seconds: float


@dataclass(frozen=True)
class SuiteSpec:
    assignment: str
    comparison_mode: ComparisonMode
    cases: tuple[CaseSpec, ...]


class FailureCategory(str, Enum):
    WRONG_OUTPUT = "wrong_output"
    NON_ZERO_EXIT = "non_zero_exit"
    CRASH = "crash"  # terminated by a signal
    TIMEOUT = "timeout"
    OUTPUT_LIMIT = "output_limit_exceeded"
    SANITIZER = "sanitizer_error"  # a sanitizer reported a defect in the program
    RUNNER_ERROR = "runner_error"  # the grader could not start the program


@dataclass
class CaseResult:
    name: str
    passed: bool
    category: FailureCategory | None
    exit_code: int | None  # None when killed by a signal or never started
    signal: int | None
    elapsed_seconds: float
    stdout: str
    stderr: str
    output_truncated: bool
    output_matches: bool | None  # None when output was not compared
    diff: str  # empty unless output differs
    message: str


@dataclass
class GradeResult:
    assignment: str
    compile: CompileResult
    cases: list[CaseResult]
    total_seconds: float

    @property
    def passed(self) -> bool:
        return self.compile.ok and bool(self.cases) and all(c.passed for c in self.cases)
