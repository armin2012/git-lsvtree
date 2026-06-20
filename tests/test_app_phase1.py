from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from PySide6.QtCore import QRectF
from PySide6.QtWidgets import QApplication

from git_lsvtree_ui.app.graph_loader import GraphLoadRequest, GraphLoadResult, GraphLoaderWorker
from git_lsvtree_ui.app import main_window as main_window_module
from git_lsvtree_ui.app.main_window import MainWindow
from git_lsvtree_ui.core.graph_model import DisplayGraph, DisplayNode, GraphModel
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
