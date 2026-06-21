from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from git_lsvtree_ui.core.project_tree import ProjectTreeBuilder
from git_lsvtree_ui.ui.project_navigator import ProjectNavigator


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def _tree():
    return ProjectTreeBuilder().build(
        repo_root=Path("/repo"),
        tracked_paths=[
            "README.md",
            "src/app.py",
            "src/lib/util.py",
            "tests/test_app.py",
        ],
    )


def _top_texts(navigator: ProjectNavigator) -> list[str]:
    return [
        navigator.tree_widget.topLevelItem(index).text(0)
        for index in range(navigator.tree_widget.topLevelItemCount())
    ]


def test_project_navigator_populates_first_level_items(qapp):
    navigator = ProjectNavigator()

    navigator.set_project_tree(_tree())

    assert _top_texts(navigator) == ["+ src", "+ tests", "  README.md"]


def test_project_navigator_expands_and_collapses_directory(qapp):
    navigator = ProjectNavigator()
    navigator.set_project_tree(_tree())
    src = navigator.tree_widget.topLevelItem(0)

    navigator.toggle_directory_item(src)

    assert src.isExpanded() is True
    assert src.text(0) == "- src"
    assert "src" in navigator.expanded_dirs()

    navigator.toggle_directory_item(src)

    assert src.isExpanded() is False
    assert src.text(0) == "+ src"
    assert "src" not in navigator.expanded_dirs()


def test_project_navigator_emits_file_selected(qapp):
    navigator = ProjectNavigator()
    navigator.set_project_tree(_tree())
    selected: list[Path] = []
    navigator.fileSelected.connect(lambda path: selected.append(path))
    readme = navigator.tree_widget.topLevelItem(2)

    navigator.activate_item(readme)

    assert selected == [Path("/repo/README.md")]


def test_project_navigator_preserves_expanded_dirs(qapp):
    navigator = ProjectNavigator()
    navigator.set_project_tree(_tree())

    navigator.restore_expanded_dirs({"src"})

    src = navigator.tree_widget.topLevelItem(0)
    tests = navigator.tree_widget.topLevelItem(1)
    assert src.isExpanded() is True
    assert src.text(0) == "- src"
    assert tests.isExpanded() is False
    assert navigator.expanded_dirs() == {"src"}


def test_project_navigator_marks_selected_file(qapp):
    navigator = ProjectNavigator()
    navigator.set_project_tree(_tree())

    navigator.set_selected_file("README.md")

    readme = navigator.tree_widget.topLevelItem(2)
    assert navigator.tree_widget.currentItem() is readme
    assert navigator.selected_project_file == "README.md"
