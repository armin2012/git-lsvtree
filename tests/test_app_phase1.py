from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from PySide6.QtCore import QRectF
from PySide6.QtWidgets import QApplication

from git_lsvtree_ui.app.graph_loader import GraphLoadRequest, GraphLoadResult, GraphLoaderWorker
from git_lsvtree_ui.app import main_window as main_window_module
from git_lsvtree_ui.app.main_window import MainWindow
from git_lsvtree_ui.core.graph_model import DisplayEdge, DisplayGraph, DisplayNode, GraphModel
from git_lsvtree_ui.layout.tree_layout import TreeLayout


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def _run(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()


def test_graph_loader_reports_empty_history_as_failure(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(repo, "init")
    _run(repo, "config", "user.email", "tester@example.com")
    _run(repo, "config", "user.name", "Tester")
    tracked = repo / "tracked.txt"
    tracked.write_text("tracked\n", encoding="utf-8")
    _run(repo, "add", "tracked.txt")
    _run(repo, "commit", "-m", "tracked")
    untracked = repo / "untracked.txt"
    untracked.write_text("untracked\n", encoding="utf-8")

    worker = GraphLoaderWorker(GraphLoadRequest(file_path=untracked))
    loaded = []
    errors = []
    worker.signals.loaded.connect(lambda result: loaded.append(result))
    worker.signals.failed.connect(lambda message: errors.append(message))

    worker.run()

    assert loaded == []
    assert errors
    assert "no Git history" in errors[0]


def test_search_matches_partial_label(qapp):
    window = MainWindow()
    display = DisplayGraph(
        nodes={
            "a" * 40: DisplayNode(
                id="a" * 40,
                kind="version",
                branch="main",
                per_branch_index=0,
                topo_rank=0,
                label="release-2026",
                source_hashes=("a" * 40,),
            )
        },
        edges=(),
    )
    layout = TreeLayout().layout(display, branch_order=("main",))
    result = GraphLoadResult(
        file_path=Path("file.txt"),
        layout=layout,
        mode="key",
        graph=GraphModel({}, (), (), (), {}),
    )
    window.set_loaded_layout(result)
    hits = []
    window.graph_view.scene().highlight_node = lambda node_id: hits.append(node_id)

    window._search_node("2026")

    assert hits[-1] == "a" * 40


def test_export_png_scales_large_scene(tmp_path: Path, qapp, monkeypatch):
    window = MainWindow()
    out = tmp_path / "graph.png"
    scene = window.graph_view.scene()
    scene.setSceneRect(QRectF(0, 0, 1000, 1000))
    monkeypatch.setattr(main_window_module, "MAX_EXPORT_PIXELS", 100)
    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(out), "PNG (*.png)"),
    )

    window.export_png()

    assert out.exists()


def test_main_window_load_file_enables_repo_tags(qapp, monkeypatch, tmp_path: Path):
    captured = []

    class _Signal:
        def connect(self, _slot):
            pass

    class _Signals:
        loaded = _Signal()
        failed = _Signal()

    class _Worker:
        def __init__(self, request: GraphLoadRequest):
            captured.append(request)
            self.signals = _Signals()

    window = MainWindow()
    window.thread_pool.start = lambda _worker: None
    monkeypatch.setattr(main_window_module, "GraphLoaderWorker", _Worker)

    window.load_file(tmp_path / "tracked.txt")

    assert captured
    assert captured[0].include_repo_tags is True


def test_graph_scene_edge_selection_replaces_previous_overlay(qapp):
    a, b, c = "a" * 40, "b" * 40, "c" * 40
    display = DisplayGraph(
        nodes={
            a: DisplayNode(a, "version", "main", 0, 0, "1", (a,), ("v1.0",)),
            b: DisplayNode(b, "version", "main", 1, 1, "2", (b,), ()),
            c: DisplayNode(c, "version", "main", 2, 2, "3", (c,), ()),
        },
        edges=(DisplayEdge(a, b, "main"), DisplayEdge(b, c, "main")),
    )
    layout = TreeLayout().layout(display, branch_order=("main",))
    window = MainWindow()
    scene = window.graph_view.scene()
    scene.set_layout_graph(layout)

    scene.set_edge_selection(a, b)
    first_info = scene._edge_info_item
    assert scene._selected_edge_id == f"{a}->{b}"
    assert scene.edge_by_id[f"{a}->{b}"]._selected_state is True
    assert first_info is not None
    assert any("v1.0" in child.text() for child in first_info.childItems())

    scene.set_edge_selection(b, c)

    assert scene._selected_edge_id == f"{b}->{c}"
    assert scene.edge_by_id[f"{a}->{b}"]._selected_state is False
    assert scene.edge_by_id[f"{b}->{c}"]._selected_state is True
    assert first_info not in scene.items()
    assert scene._edge_info_item is not None


def test_main_window_edge_click_clears_version_selection(qapp):
    a, b = "a" * 40, "b" * 40
    display = DisplayGraph(
        nodes={
            a: DisplayNode(a, "version", "main", 0, 0, "1", (a,)),
            b: DisplayNode(b, "version", "main", 1, 1, "2", (b,)),
        },
        edges=(DisplayEdge(a, b, "main"),),
    )
    layout = TreeLayout().layout(display, branch_order=("main",))
    window = MainWindow()
    result = GraphLoadResult(
        file_path=Path("file.txt"),
        layout=layout,
        mode="key",
        graph=GraphModel({}, (), (), (), {}),
    )
    window.set_loaded_layout(result)
    window.selected_versions = [a, b]
    window.graph_view.scene().set_selection([a, b])

    window._on_edge_clicked(a, b)

    assert window.selected_versions == []
    assert window.diff_action.isEnabled() is False
