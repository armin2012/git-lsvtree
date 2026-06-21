from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from git_lsvtree_ui.app import main_window as main_window_module
from git_lsvtree_ui.app.graph_loader import GraphLoadResult, ProjectLoadResult
from git_lsvtree_ui.app.main_window import MainWindow
from git_lsvtree_ui.core.graph_model import DisplayGraph, GraphModel
from git_lsvtree_ui.core.project_tree import ProjectTreeBuilder
from git_lsvtree_ui.layout.tree_layout import TreeLayout


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def _make_tree(repo_root: Path):
    return ProjectTreeBuilder().build(
        repo_root=repo_root,
        tracked_paths=["README.md", "src/app.py"],
    )


def _empty_layout():
    return TreeLayout().layout(DisplayGraph(nodes={}, edges=()), branch_order=())


class _FakeSignal:
    def connect(self, _slot):
        pass


class _FakeWorkerSignals:
    loaded = _FakeSignal()
    failed = _FakeSignal()


def test_main_window_open_project_starts_project_loader(qapp, monkeypatch, tmp_path):
    captured = []

    class _Worker:
        def __init__(self, request):
            captured.append(request)
            self.signals = _FakeWorkerSignals()

    window = MainWindow()
    window.thread_pool.start = lambda _: None
    monkeypatch.setattr(main_window_module, "ProjectLoaderWorker", _Worker)

    window._load_project(tmp_path)

    assert len(captured) == 1
    assert captured[0].project_path == tmp_path


def test_main_window_project_loaded_shows_navigator(qapp, tmp_path):
    window = MainWindow()
    assert window.navigator_dock.isHidden()

    tree = _make_tree(tmp_path)
    window._on_project_loaded(ProjectLoadResult(repo_root=tmp_path, tree=tree))

    assert not window.navigator_dock.isHidden()
    assert window.current_project_root == tmp_path
    assert window.project_navigator.project_tree is tree


def test_main_window_project_file_selection_starts_graph_loader(qapp, monkeypatch, tmp_path):
    captured = []

    class _Worker:
        def __init__(self, request):
            captured.append(request)
            self.signals = _FakeWorkerSignals()

    window = MainWindow()
    window.thread_pool.start = lambda _: None
    monkeypatch.setattr(main_window_module, "GraphLoaderWorker", _Worker)

    file_path = tmp_path / "README.md"
    file_path.write_text("hello", encoding="utf-8")
    window.load_file(file_path)

    assert len(captured) == 1
    assert captured[0].file_path == file_path


def test_main_window_project_load_failure_keeps_current_graph(qapp, tmp_path):
    window = MainWindow()
    result = GraphLoadResult(
        file_path=tmp_path / "file.txt",
        layout=_empty_layout(),
        mode="key",
        graph=GraphModel({}, (), (), (), {}),
    )
    window.set_loaded_layout(result)
    prev_layout = window.current_layout

    window._on_project_failed("not a git repository")

    assert window.current_layout is prev_layout


def test_main_window_toggle_project_navigator_visibility_preserves_tree(qapp, tmp_path):
    window = MainWindow()
    tree = _make_tree(tmp_path)
    window._on_project_loaded(ProjectLoadResult(repo_root=tmp_path, tree=tree))
    assert not window.navigator_dock.isHidden()

    window.navigator_dock.hide()
    assert window.navigator_dock.isHidden()
    assert window.project_navigator.project_tree is tree

    window.navigator_dock.show()
    assert not window.navigator_dock.isHidden()
    assert window.project_navigator.project_tree is tree
    assert window.project_navigator.tree_widget.topLevelItemCount() > 0
