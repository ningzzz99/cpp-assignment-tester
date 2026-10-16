from cppgrader.comparator import compare_output, normalize_whitespace
from cppgrader.models import ComparisonMode

STRICT, NORM = ComparisonMode.STRICT, ComparisonMode.NORMALIZED_WHITESPACE


def test_strict_requires_exact_match():
    assert compare_output("5\n", "5\n", STRICT).matches
    assert not compare_output("5\n", "5", STRICT).matches
    assert not compare_output("5\n", "5 \n", STRICT).matches


def test_normalized_ignores_spacing_and_blank_lines():
    assert compare_output("1 2 3\n", "  1\n\n2\t3  \n\n", NORM).matches
    assert compare_output("", "  \n", NORM).matches


def test_normalized_still_detects_real_differences():
    assert not compare_output("1 2 3", "1 2 4", NORM).matches
    assert not compare_output("1 2", "12", NORM).matches  # whitespace between tokens matters


def test_non_ascii_whitespace_is_not_collapsed():
    assert normalize_whitespace("a b") == "a b"
    assert not compare_output("a b", "a b", NORM).matches


def test_diff_makes_whitespace_visible():
    result = compare_output("5\n", "5", STRICT)
    assert not result.matches
    assert "-5\\n" in result.diff and "+5" in result.diff


def test_diff_empty_on_match():
    assert compare_output("x", "x", STRICT).diff == ""


def test_diff_is_truncated():
    result = compare_output("\n".join(map(str, range(500))), "\n".join(map(str, range(500, 1000))), STRICT)
    assert "more diff lines" in result.diff
    assert len(result.diff.splitlines()) <= 41


def test_very_long_line_is_cut():
    result = compare_output("a" * 5000, "b", STRICT)
    assert len(result.diff) < 1000


def test_unicode_is_compared_and_shown():
    assert compare_output("héllo ✓\n", "héllo ✓\n", STRICT).matches
    assert "✓" in compare_output("✓\n", "x\n", STRICT).diff
