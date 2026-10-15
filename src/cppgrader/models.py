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
