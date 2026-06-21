from __future__ import annotations

from pathlib import Path

import pytest

from git_lsvtree_ui.core.project_tree import ProjectTreeBuilder


def _child_names(node):
    return [child.name for child in node.children]


def test_project_tree_builds_flat_files():
    tree = ProjectTreeBuilder().build(
        repo_root=Path("/repo"),
        tracked_paths=["README.md", "pyproject.toml"],
    )

    assert tree.repo_root == Path("/repo")
    assert tree.tracked_file_count == 2
    assert tree.root.name == "repo"
    assert tree.root.rel_path == ""
    assert tree.root.kind == "directory"
    assert _child_names(tree.root) == ["pyproject.toml", "README.md"]
    assert all(child.kind == "file" for child in tree.root.children)
    assert all(child.tracked for child in tree.root.children)


def test_project_tree_builds_nested_directories():
    tree = ProjectTreeBuilder().build(
        repo_root=Path("/repo"),
        tracked_paths=[
            "src/app/main_window.py",
            "src/core/project_tree.py",
            "tests/test_project_tree.py",
        ],
    )

    root_names = _child_names(tree.root)
    assert root_names == ["src", "tests"]
    src = tree.root.children[0]
    assert src.kind == "directory"
    assert src.rel_path == "src"
    assert _child_names(src) == ["app", "core"]
    app = src.children[0]
    assert app.kind == "directory"
    assert app.rel_path == "src/app"
    assert _child_names(app) == ["main_window.py"]
    assert app.children[0].kind == "file"
    assert app.children[0].rel_path == "src/app/main_window.py"


def test_project_tree_sorts_directories_before_files_case_insensitive():
    tree = ProjectTreeBuilder().build(
        repo_root=Path("/repo"),
        tracked_paths=[
            "zeta.txt",
            "Src/main.py",
            "alpha.txt",
            "docs/readme.md",
            "Beta.txt",
        ],
    )

    assert _child_names(tree.root) == ["docs", "Src", "alpha.txt", "Beta.txt", "zeta.txt"]


def test_project_tree_rejects_empty_tracked_paths():
    with pytest.raises(ValueError, match="no tracked files"):
        ProjectTreeBuilder().build(repo_root=Path("/repo"), tracked_paths=[])


def test_project_tree_normalizes_posix_paths_and_deduplicates():
    tree = ProjectTreeBuilder().build(
        repo_root=Path("/repo"),
        tracked_paths=[
            "src//main.py",
            "./src/main.py",
            "src/lib/../lib/util.py",
            "",
            ".",
        ],
    )

    assert tree.tracked_file_count == 2
    src = tree.root.children[0]
    assert src.name == "src"
    assert _child_names(src) == ["lib", "main.py"]
    assert src.children[0].children[0].rel_path == "src/lib/util.py"
