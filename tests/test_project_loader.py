from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from git_lsvtree_ui.app.graph_loader import ProjectLoaderWorker, ProjectLoadRequest
from git_lsvtree_ui.core import git_repo as git_repo_module


def _completed(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


def test_project_loader_resolves_repo_root_and_builds_tree(monkeypatch, tmp_path: Path):
    project_path = tmp_path / "repo" / "subdir"
    repo_root = tmp_path / "repo"
    calls: list[tuple[Path, tuple]] = []

    def fake_run_git_at(path: Path, *args: str):
        calls.append((path, args))
        if args == ("rev-parse", "--show-toplevel"):
            return _completed(stdout=str(repo_root) + "\n")
        if args == ("ls-files", "-z"):
            return _completed(stdout="README.md\x00src/main.py\x00")
        raise AssertionError(f"unexpected command: {args} cwd={path}")

    monkeypatch.setattr(git_repo_module.GitRepo, "run_git_at", staticmethod(fake_run_git_at))
    worker = ProjectLoaderWorker(ProjectLoadRequest(project_path=project_path))
    loaded = []
    errors = []
    worker.signals.loaded.connect(lambda result: loaded.append(result))
    worker.signals.failed.connect(lambda message: errors.append(message))

    worker.run()

    assert errors == []
    assert len(loaded) == 1
    assert loaded[0].repo_root == repo_root
    assert loaded[0].tree.repo_root == repo_root
    assert loaded[0].tree.tracked_file_count == 2
    assert [child.name for child in loaded[0].tree.root.children] == ["src", "README.md"]
    assert len(calls) == 2


def test_project_loader_fails_for_non_git_directory(monkeypatch, tmp_path: Path):
    project_path = tmp_path / "not-repo"

    def fake_run_git_at(path: Path, *args: str):
        return _completed(returncode=128, stderr="not a git repository")

    monkeypatch.setattr(git_repo_module.GitRepo, "run_git_at", staticmethod(fake_run_git_at))
    worker = ProjectLoaderWorker(ProjectLoadRequest(project_path=project_path))
    loaded = []
    errors = []
    worker.signals.loaded.connect(lambda result: loaded.append(result))
    worker.signals.failed.connect(lambda message: errors.append(message))

    worker.run()

    assert loaded == []
    assert errors
    assert "not a git repository" in errors[0]


def test_project_loader_fails_for_empty_tracked_file_list(monkeypatch, tmp_path: Path):
    repo_root = tmp_path / "repo"

    def fake_run_git_at(path: Path, *args: str):
        if args == ("rev-parse", "--show-toplevel"):
            return _completed(stdout=str(repo_root) + "\n")
        if args == ("ls-files", "-z"):
            return _completed(stdout="")
        raise AssertionError(f"unexpected command: {args}")

    monkeypatch.setattr(git_repo_module.GitRepo, "run_git_at", staticmethod(fake_run_git_at))
    worker = ProjectLoaderWorker(ProjectLoadRequest(project_path=repo_root))
    loaded = []
    errors = []
    worker.signals.loaded.connect(lambda result: loaded.append(result))
    worker.signals.failed.connect(lambda message: errors.append(message))

    worker.run()

    assert loaded == []
    assert errors
    assert "no tracked files" in errors[0]


def test_project_loader_fails_when_ls_files_fails(monkeypatch, tmp_path: Path):
    repo_root = tmp_path / "repo"

    def fake_run_git_at(path: Path, *args: str):
        if args == ("rev-parse", "--show-toplevel"):
            return _completed(stdout=str(repo_root) + "\n")
        if args == ("ls-files", "-z"):
            return _completed(returncode=1, stderr="ls-files failed")
        raise AssertionError(f"unexpected command: {args}")

    monkeypatch.setattr(git_repo_module.GitRepo, "run_git_at", staticmethod(fake_run_git_at))
    worker = ProjectLoaderWorker(ProjectLoadRequest(project_path=repo_root))
    loaded = []
    errors = []
    worker.signals.loaded.connect(lambda result: loaded.append(result))
    worker.signals.failed.connect(lambda message: errors.append(message))

    worker.run()

    assert loaded == []
    assert errors
    assert "ls-files failed" in errors[0]
