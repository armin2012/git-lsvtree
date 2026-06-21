from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from PySide6.QtCore import QRectF, Qt
from PySide6.QtWidgets import QApplication

from git_lsvtree_ui.app.graph_loader import GraphLoadRequest, GraphLoadResult, GraphLoaderWorker
from git_lsvtree_ui.app import main_window as main_window_module
from git_lsvtree_ui.app.main_window import MainWindow
from git_lsvtree_ui.core.graph_model import DisplayEdge, DisplayGraph, DisplayNode, GraphModel, VersionNode
from git_lsvtree_ui.layout.geometry import Point
from git_lsvtree_ui.layout.tree_layout import LayoutEdge, LayoutNode
from git_lsvtree_ui.layout.tree_layout import TreeLayout
from git_lsvtree_ui.ui.detail_panel import DetailPanel
from git_lsvtree_ui.ui.items import EdgeItem


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
    first_text_items = [child for child in first_info.childItems() if hasattr(child, "text")]
    assert first_text_items
    first_text = first_text_items[0].text()
    assert "from: 1" in first_text
    assert "to:   2" in first_text
    assert f"1         ｜ {a[:12]} ｜ main" in first_text
    assert f"2         ｜ {b[:12]} ｜ main" in first_text
    assert first_text_items[0].font().fixedPitch() is True

    scene.set_edge_selection(b, c)

    assert scene._selected_edge_id == f"{b}->{c}"
    assert scene.edge_by_id[f"{a}->{b}"]._selected_state is False
    assert scene.edge_by_id[f"{b}->{c}"]._selected_state is True
    assert scene._edge_info_item is first_info
    assert scene._edge_info_item.isVisible() is True
    second_text = first_text_items[0].text()
    assert f"2         ｜ {b[:12]} ｜ main" in second_text
    assert f"3         ｜ {c[:12]} ｜ main" in second_text
    assert f"1         ｜ {a[:12]} ｜ main" not in second_text


def test_graph_scene_edge_selection_refreshes_overlay_regions(qapp, monkeypatch):
    a, b, c = "a" * 40, "b" * 40, "c" * 40
    display = DisplayGraph(
        nodes={
            a: DisplayNode(a, "version", "main", 0, 0, "1", (a,)),
            b: DisplayNode(b, "version", "main", 1, 1, "2", (b,)),
            c: DisplayNode(c, "version", "main", 2, 2, "3", (c,)),
        },
        edges=(DisplayEdge(a, b, "main"), DisplayEdge(b, c, "main")),
    )
    layout = TreeLayout().layout(display, branch_order=("main",))
    window = MainWindow()
    scene = window.graph_view.scene()
    scene.set_layout_graph(layout)
    invalidated = []
    updated = []
    monkeypatch.setattr(scene, "invalidate", lambda rect, layers=None: invalidated.append((rect, layers)))
    monkeypatch.setattr(scene, "update", lambda rect=None: updated.append(rect))

    scene.set_edge_selection(a, b)
    scene.set_edge_selection(b, c)

    assert len(invalidated) >= 2
    assert len(updated) >= 2
    assert all(not rect.isNull() for rect, _layers in invalidated)
    assert all(rect is None or not rect.isNull() for rect in updated)


def test_graph_scene_format_node_summary_uses_aligned_separator(qapp):
    a = "a" * 40
    display_node = DisplayNode(a, "version", "feature-x", 0, 0, "12", (a,))

    summary = MainWindow().graph_view.scene()._format_node_summary(display_node)

    assert summary == f"12        ｜ {a[:12]} ｜ feature-x"


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


def test_edge_item_uses_quadratic_path_for_routed_edge(qapp):
    edge = LayoutEdge(
        src="a",
        dst="b",
        kind="merge",
        label="",
        start=Point(0, 0),
        end=Point(100, 0),
        route_kind="quadratic",
        control_points=(Point(50, 40),),
        stroke_width=1.2,
    )

    item = EdgeItem(edge)

    assert not item.path().isEmpty()
    assert item.path().elementCount() > 2
    assert abs(item.pen().widthF() - 1.2) < 0.001
    assert item.brush().style() == Qt.BrushStyle.NoBrush
    assert item.arrow_item.brush().color().name() == "#dc2626"


def test_edge_item_selection_preserves_routed_path(qapp):
    edge = LayoutEdge(
        src="a",
        dst="b",
        kind="merge",
        label="",
        start=Point(0, 0),
        end=Point(100, 0),
        route_kind="quadratic",
        control_points=(Point(50, 40),),
    )
    item = EdgeItem(edge)
    before = item.path()

    item.set_selected_state(True)
    assert item.brush().style() == Qt.BrushStyle.NoBrush
    assert item.arrow_item.brush().color().name() == "#f59e0b"
    item.set_selected_state(False)

    assert item.path() == before
    assert item.arrow_item.brush().color().name() == "#dc2626"


def test_detail_panel_shows_commit_description_and_committer(qapp):
    commit = "a" * 40
    graph = GraphModel(
        nodes={
            commit: VersionNode(
                hash=commit,
                parents=(),
                main_parent=None,
                merge_parents=(),
                tags=("v1.0",),
                author_name="Alice",
                author_email="alice@example.com",
                author_time=1000,
                commit_time=1100,
                subject="Improve Details",
                topo_rank=0,
                reconstructed_branch="main",
                committer_name="Bob",
                committer_email="bob@example.com",
                description="Why:\nshow commit body in the Details dock",
            )
        },
        edges=(),
        order_newest_first=(commit,),
        order_oldest_first=(commit,),
        branches={},
    )
    layout_node = LayoutNode(
        id=commit,
        kind="version",
        branch="main",
        topo_rank=0,
        center=Point(0, 0),
        radius=10,
        label="1",
        source_hashes=(commit,),
        tags=("v1.0",),
    )
    panel = DetailPanel()

    panel.show_version(layout_node, graph)

    text = panel.toPlainText()
    assert "Improve Details" in text
    assert "Bob <bob@example.com>" in text
    assert "Why:" in text
    assert "show commit body in the Details dock" in text
