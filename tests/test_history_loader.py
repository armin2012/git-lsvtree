"""Tests for HistoryLoader and its pure parsing helpers."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from git_lsvtree_ui.core.history_loader import (
    HistoryLoader,
    parse_merge_source,
    parse_tags,
)

RS = "\x00"   # must match history_loader.RS
GS = "\x02"


def _log_entry(
    hash_: str,
    parents: tuple[str, ...] = (),
    decorations: str = "",
    author: str = "Author",
    email: str = "a@b.com",
    atime: int = 1000,
    ctime: int = 1000,
    subject: str = "msg",
    committer: str = "Committer",
    committer_email: str = "c@b.com",
    description: str = "",
) -> str:
    parent_str = " ".join(parents)
    return (
        f"{RS}{hash_} {parent_str}"
        f"{GS}{decorations}{GS}{author}{GS}{email}"
        f"{GS}{atime}{GS}{ctime}{GS}{subject}"
        f"{GS}{committer}{GS}{committer_email}{GS}{description}"
    )


def _mock_repo(log_output: str, head_commit: str = "", tags: list[str] | None = None) -> MagicMock:
    repo = MagicMock()
    repo.rel_path = "src/foo.py"
    repo.git_checked.return_value = log_output
    _tags = tags or []

    def _git(*args, **kwargs):
        m = MagicMock()
        m.returncode = 0
        if args and args[0] == "tag":
            # Return configured tag list (empty by default in tests)
            m.stdout = "\n".join(_tags) + "\n" if _tags else ""
        elif args and args[0] == "rev-list" and len(args) >= 2 and args[1] == "-1":
            # rev-list -1 <ref> [--] [path]: return head_commit as the anchor
            m.stdout = head_commit + "\n" if head_commit else ""
            m.returncode = 0 if head_commit else 1
        else:
            m.returncode = 0 if head_commit else 1
            m.stdout = head_commit + "\n" if head_commit else ""
        return m

    repo.git.side_effect = _git
    return repo


# ── parse_tags ─────────────────────────────────────────────────────────────

def test_parse_tags_empty():
    assert parse_tags("") == ()


def test_parse_tags_no_tags():
    assert parse_tags("HEAD -> main, origin/main") == ()


def test_parse_tags_single():
    assert parse_tags("tag: v1.0.0") == ("v1.0.0",)


def test_parse_tags_multiple():
    assert parse_tags("tag: v1.0.0, tag: v1.0.1, HEAD -> main") == ("v1.0.0", "v1.0.1")


# ── parse_merge_source ─────────────────────────────────────────────────────

def test_parse_merge_source_branch():
    assert parse_merge_source("Merge branch 'feature-x'") == "feature-x"


def test_parse_merge_source_remote():
    assert parse_merge_source("Merge remote-tracking branch 'origin/dev'") == "origin/dev"


def test_parse_merge_source_pr():
    assert parse_merge_source("Merge pull request #42 from user/feat") == "user/feat"


def test_parse_merge_source_unknown():
    assert parse_merge_source("regular commit message") == ""


# ── HistoryLoader.load ─────────────────────────────────────────────────────

def test_load_empty():
    repo = _mock_repo("")
    graph = HistoryLoader(repo).load()
    assert len(graph.nodes) == 0
    assert len(graph.edges) == 0


def test_load_single_commit():
    h = "a" * 40
    repo = _mock_repo(_log_entry(h, subject="Initial"), head_commit=h)
    graph = HistoryLoader(repo).load()

    assert len(graph.nodes) == 1
    assert len(graph.edges) == 0
    node = graph.nodes[h]
    assert node.hash == h
    assert node.parents == ()
    assert node.main_parent is None
    assert node.subject == "Initial"
    assert node.is_head_file_version is True


def test_load_commit_description_and_committer():
    h = "a" * 40
    repo = _mock_repo(
        _log_entry(
            h,
            subject="Fix routed edge detail",
            committer="Release Bot",
            committer_email="release@example.com",
            description="Why:\nshow full metadata in Details",
        ),
        head_commit=h,
    )

    graph = HistoryLoader(repo).load()
    node = graph.nodes[h]

    assert node.subject == "Fix routed edge detail"
    assert node.committer_name == "Release Bot"
    assert node.committer_email == "release@example.com"
    assert node.description == "Why:\nshow full metadata in Details"


def test_load_linear_two_commits():
    c0 = "0" * 40
    c1 = "1" * 40
    log = _log_entry(c1, parents=(c0,)) + _log_entry(c0)
    repo = _mock_repo(log, head_commit=c1)
    graph = HistoryLoader(repo).load()

    assert len(graph.nodes) == 2
    assert len(graph.edges) == 1
    edge = graph.edges[0]
    assert edge.src == c0
    assert edge.dst == c1
    assert edge.kind == "main"
    assert graph.nodes[c1].main_parent == c0
    assert graph.nodes[c0].main_parent is None


def test_load_merge_commit():
    c0 = "0" * 40
    c1 = "1" * 40
    cm = "2" * 40  # merge commit with parents c1 and c0
    log = (
        _log_entry(cm, parents=(c1, c0), subject="Merge branch 'feat'")
        + _log_entry(c1)
        + _log_entry(c0)
    )
    repo = _mock_repo(log, head_commit=cm)
    graph = HistoryLoader(repo).load()

    assert len(graph.nodes) == 3
    assert graph.nodes[cm].main_parent == c1
    assert len(graph.nodes[cm].merge_parents) == 1
    assert graph.nodes[cm].merge_parents[0].hash == c0
    merge_edges = [e for e in graph.edges if e.kind == "merge"]
    assert len(merge_edges) == 1
    assert merge_edges[0].src == c0
    assert merge_edges[0].dst == cm


def test_load_tags_parsed():
    c0 = "a" * 40
    repo = _mock_repo(_log_entry(c0, decorations="tag: v2.0, HEAD -> main"), head_commit=c0)
    graph = HistoryLoader(repo).load()
    assert graph.nodes[c0].tags == ("v2.0",)


def test_repo_wide_tag_scan_is_opt_in():
    c0 = "a" * 40
    repo = _mock_repo(_log_entry(c0), head_commit=c0, tags=["v1.0"])

    graph = HistoryLoader(repo).load()

    assert graph.nodes[c0].tags == ()
    assert not any(call.args and call.args[0] == "tag" for call in repo.git.call_args_list)


def test_repo_wide_tag_scan_can_be_enabled():
    c0 = "a" * 40
    repo = _mock_repo(_log_entry(c0), head_commit=c0, tags=["v1.0"])

    graph = HistoryLoader(repo, include_repo_tags=True).load()

    assert graph.nodes[c0].tags == ("v1.0",)


def test_load_topo_rank_oldest_is_zero():
    c0, c1, c2 = "0" * 40, "1" * 40, "2" * 40
    log = _log_entry(c2, (c1,)) + _log_entry(c1, (c0,)) + _log_entry(c0)
    repo = _mock_repo(log, head_commit=c2)
    graph = HistoryLoader(repo).load()

    # order_oldest_first: c0, c1, c2 → topo_rank = 0, 1, 2
    assert graph.nodes[c0].topo_rank == 0
    assert graph.nodes[c1].topo_rank == 1
    assert graph.nodes[c2].topo_rank == 2


def test_load_order_newest_first():
    c0, c1 = "0" * 40, "1" * 40
    repo = _mock_repo(_log_entry(c1, (c0,)) + _log_entry(c0))
    graph = HistoryLoader(repo).load()
    assert graph.order_newest_first[0] == c1
    assert graph.order_oldest_first[0] == c0
