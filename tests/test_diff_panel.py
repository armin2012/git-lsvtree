"""Tests for DiffPanel's pure alignment logic (_align_sides)."""
from __future__ import annotations

import pytest

# _align_sides is a module-level function; import it directly
from git_lsvtree_ui.ui.diff_panel import _align_sides

_WHITE = "#ffffff"
_RED = "#fee2e2"
_BLUE = "#dbeafe"


# ── helpers ────────────────────────────────────────────────────────────────

def _colors(side):
    return [color for _, color in side]


def _texts(side):
    return [text for text, _ in side]


# ── identical content ──────────────────────────────────────────────────────

def test_identical_all_white():
    lines = ["line1", "line2", "line3"]
    left, right, ranges = _align_sides(lines, lines)
    assert all(c == _WHITE for c in _colors(left))
    assert all(c == _WHITE for c in _colors(right))
    assert ranges == []


def test_identical_same_text_both_sides():
    lines = ["a", "b", "c"]
    left, right, _ = _align_sides(lines, lines)
    assert _texts(left) == lines
    assert _texts(right) == lines


# ── single delete ──────────────────────────────────────────────────────────

def test_delete_line_left_red_right_padding():
    old = ["a", "b", "c"]
    new = ["a", "c"]
    left, right, ranges = _align_sides(old, new)
    assert left and right
    assert len(left) == len(right)  # always equal length
    assert ranges != []
    # Some left line must be red
    assert _RED in _colors(left)


def test_delete_right_side_has_empty_padding():
    old = ["a", "b"]
    new = ["a"]
    left, right, _ = _align_sides(old, new)
    # Right side padding for deleted line has None color
    right_colors = _colors(right)
    assert None in right_colors


# ── single insert ──────────────────────────────────────────────────────────

def test_insert_line_right_blue_left_padding():
    old = ["a", "c"]
    new = ["a", "b", "c"]
    left, right, ranges = _align_sides(old, new)
    assert len(left) == len(right)
    assert ranges != []
    assert _BLUE in _colors(right)


def test_insert_left_side_has_empty_padding():
    old = ["a"]
    new = ["a", "b"]
    left, right, _ = _align_sides(old, new)
    left_colors = _colors(left)
    assert None in left_colors


# ── replace ────────────────────────────────────────────────────────────────

def test_replace_left_red_right_blue():
    old = ["a", "old_line", "c"]
    new = ["a", "new_line", "c"]
    left, right, ranges = _align_sides(old, new)
    assert _RED in _colors(left)
    assert _BLUE in _colors(right)
    assert ranges != []


def test_replace_equal_lines_still_white():
    old = ["same1", "old", "same2"]
    new = ["same1", "new", "same2"]
    left, right, _ = _align_sides(old, new)
    left_pairs = list(zip(_texts(left), _colors(left)))
    right_pairs = list(zip(_texts(right), _colors(right)))
    assert ("same1", _WHITE) in left_pairs
    assert ("same2", _WHITE) in left_pairs
    assert ("same1", _WHITE) in right_pairs
    assert ("same2", _WHITE) in right_pairs


# ── length invariant ───────────────────────────────────────────────────────

def test_left_right_always_same_length():
    cases = [
        (["a"], ["a", "b", "c"]),
        (["a", "b", "c"], ["a"]),
        (["a", "b"], ["c", "d"]),
        ([], ["a"]),
        (["a"], []),
    ]
    for old, new in cases:
        left, right, _ = _align_sides(old, new)
        assert len(left) == len(right), f"length mismatch for {old!r} vs {new!r}"


def test_empty_both_sides():
    left, right, ranges = _align_sides([], [])
    assert left == []
    assert right == []
    assert ranges == []


# ── diff_ranges ────────────────────────────────────────────────────────────

def test_diff_ranges_non_empty_on_any_change():
    _, _, ranges = _align_sides(["a"], ["b"])
    assert len(ranges) > 0


def test_diff_ranges_multiple_blocks():
    old = ["same", "old1", "same", "old2", "same"]
    new = ["same", "new1", "same", "new2", "same"]
    _, _, ranges = _align_sides(old, new)
    assert len(ranges) == 2


def test_diff_ranges_bounds_within_line_count():
    old = ["a", "b", "c", "d", "e"]
    new = ["a", "X", "c", "Y", "e"]
    left, _, ranges = _align_sides(old, new)
    total = len(left)
    for start, end in ranges:
        assert 0 <= start < total
        assert start < end <= total
