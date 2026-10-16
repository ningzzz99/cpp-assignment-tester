"""Compare expected and actual program output."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from .models import ComparisonMode

MAX_DIFF_LINES = 40
MAX_LINE_CHARS = 200
_ASCII_WS = re.compile(r"[ \t\n\r\f\v]+")


@dataclass(frozen=True)
class Comparison:
    matches: bool
    diff: str  # empty when the outputs match


def normalize_whitespace(text: str) -> str:
    """Collapse runs of ASCII whitespace (including newlines) to one space and trim.

    Only ASCII whitespace is collapsed, so e.g. a no-break space is still a difference.
    Line structure is lost, so this mode is inappropriate when layout matters.
    """
    return " ".join(token for token in _ASCII_WS.split(text) if token)


def _visible_lines(text: str) -> list[str]:
    """Lines with whitespace escapes made visible (\\n, \\t, \\r) and long lines cut."""
    lines = []
    for line in text.splitlines(keepends=True):
        shown = repr(line)[1:-1]
        lines.append(shown if len(shown) <= MAX_LINE_CHARS else shown[:MAX_LINE_CHARS] + "...")
    return lines


def make_diff(expected: str, actual: str) -> str:
    diff = list(difflib.unified_diff(
        _visible_lines(expected), _visible_lines(actual),
        fromfile="expected", tofile="actual", lineterm="", n=1,
    ))
    if len(diff) > MAX_DIFF_LINES:
        extra = len(diff) - MAX_DIFF_LINES
        diff = diff[:MAX_DIFF_LINES] + [f"... ({extra} more diff lines)"]
    return "\n".join(diff)


def compare_output(expected: str, actual: str, mode: ComparisonMode) -> Comparison:
    if mode is ComparisonMode.STRICT:
        matches = expected == actual
    elif mode is ComparisonMode.NORMALIZED_WHITESPACE:
        matches = normalize_whitespace(expected) == normalize_whitespace(actual)
    else:  # pragma: no cover - guards against a new enum member being forgotten
        raise ValueError(f"Unknown comparison mode: {mode}")
    return Comparison(matches, "" if matches else make_diff(expected, actual))
