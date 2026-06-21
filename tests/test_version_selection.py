"""Tests for FIFO-queue version node selection behaviour (§8.1)."""
from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from git_lsvtree_ui.app.graph_loader import GraphLoadResult
from git_lsvtree_ui.app.main_window import MainWindow
from git_lsvtree_ui.core.graph_model import DisplayEdge, DisplayGraph, DisplayNode, GraphModel
from git_lsvtree_ui.layout.tree_layout import TreeLayout


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


# ── helpers ────────────────────────────────────────────────────────────────

_NO_MOD = Qt.KeyboardModifier.NoModifier
_CTRL   = Qt.KeyboardModifier.ControlModifier


def _make_window_with_nodes(qapp, *node_ids: str) -> MainWindow:
    """Return a MainWindow with a loaded layout containing the given version nodes."""
    nodes = {
        nid: DisplayNode(nid, "version", "main", i, i, str(i + 1), (nid,))
        for i, nid in enumerate(node_ids)
    }
    edges = tuple(
        DisplayEdge(node_ids[i], node_ids[i + 1], "main")
        for i in range(len(node_ids) - 1)
    )
    display = DisplayGraph(nodes=nodes, edges=edges)
    layout = TreeLayout().layout(display, branch_order=("main",))
    window = MainWindow()
    window.set_loaded_layout(GraphLoadResult(
        file_path=Path("file.txt"),
        layout=layout,
        mode="key",
        graph=GraphModel({}, (), (), (), {}),
    ))
    return window


def _click(window: MainWindow, node_id: str, mod=_NO_MOD) -> None:
    window._on_node_clicked_with_modifiers(node_id, mod)


# ── single-click selects ───────────────────────────────────────────────────

def test_first_click_selects_node(qapp):
    a, b = "a" * 40, "b" * 40
    w = _make_window_with_nodes(qapp, a, b)
    _click(w, a)
    assert w.selected_versions == [a]


def test_first_click_enables_detail_not_diff(qapp):
    a, b = "a" * 40, "b" * 40
    w = _make_window_with_nodes(qapp, a, b)
    _click(w, a)
    assert w.diff_action.isEnabled() is False


# ── second click appends ───────────────────────────────────────────────────

def test_second_click_different_node_adds_to_selection(qapp):
    a, b = "a" * 40, "b" * 40
    w = _make_window_with_nodes(qapp, a, b)
    _click(w, a)
    _click(w, b)
    assert w.selected_versions == [a, b]


def test_two_selected_enables_diff(qapp):
    a, b = "a" * 40, "b" * 40
    w = _make_window_with_nodes(qapp, a, b)
    _click(w, a)
    _click(w, b)
    assert w.diff_action.isEnabled() is True


# ── third click evicts oldest ──────────────────────────────────────────────

def test_third_click_evicts_oldest(qapp):
    a, b, c = "a" * 40, "b" * 40, "c" * 40
    w = _make_window_with_nodes(qapp, a, b, c)
    _click(w, a)
    _click(w, b)
    _click(w, c)
    assert w.selected_versions == [b, c]


def test_third_click_still_enables_diff(qapp):
    a, b, c = "a" * 40, "b" * 40, "c" * 40
    w = _make_window_with_nodes(qapp, a, b, c)
    _click(w, a)
    _click(w, b)
    _click(w, c)
    assert w.diff_action.isEnabled() is True


# ── toggle off (click already-selected node) ───────────────────────────────

def test_click_selected_node_deselects_it(qapp):
    a, b = "a" * 40, "b" * 40
    w = _make_window_with_nodes(qapp, a, b)
    _click(w, a)
    _click(w, a)  # toggle off
    assert w.selected_versions == []


def test_click_selected_node_disables_diff(qapp):
    a, b = "a" * 40, "b" * 40
    w = _make_window_with_nodes(qapp, a, b)
    _click(w, a)
    _click(w, a)
    assert w.diff_action.isEnabled() is False


def test_toggle_off_oldest_of_two(qapp):
    a, b = "a" * 40, "b" * 40
    w = _make_window_with_nodes(qapp, a, b)
    _click(w, a)
    _click(w, b)
    _click(w, a)  # remove oldest
    assert w.selected_versions == [b]
    assert w.diff_action.isEnabled() is False


def test_toggle_off_newest_of_two(qapp):
    a, b = "a" * 40, "b" * 40
    w = _make_window_with_nodes(qapp, a, b)
    _click(w, a)
    _click(w, b)
    _click(w, b)  # remove newest
    assert w.selected_versions == [a]
    assert w.diff_action.isEnabled() is False


# ── ctrl modifier no longer required ──────────────────────────────────────

def test_ctrl_click_still_adds_node(qapp):
    """Ctrl+click should behave identically to plain click."""
    a, b = "a" * 40, "b" * 40
    w = _make_window_with_nodes(qapp, a, b)
    _click(w, a)
    _click(w, b, mod=_CTRL)
    assert w.selected_versions == [a, b]
