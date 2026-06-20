"""Tests for BranchRebuilder."""
from __future__ import annotations

import pytest

from git_lsvtree_ui.core.branch_rebuilder import BranchRebuilder
from git_lsvtree_ui.core.graph_model import BranchInfo, Edge, GraphModel, MergeParent, VersionNode

from .conftest import h, vnode


def _raw_graph(
    specs: list[tuple[str, tuple[str, ...], dict]],
) -> GraphModel:
    """Build raw GraphModel (as HistoryLoader would produce).
    specs: [(commit_id, parent_ids, kwargs)] newest-first.
    """
    order_newest = [s[0] for s in specs]
    order_oldest = list(reversed(order_newest))
    topo = {c: i for i, c in enumerate(order_oldest)}
    node_set = set(order_newest)

    nodes: dict[str, VersionNode] = {}
    edges: list[Edge] = []
    for commit, parents, kwargs in specs:
        parents_in = tuple(p for p in parents if p in node_set)
        main_parent = parents_in[0] if parents_in else None
        merge_parents = tuple(
            MergeParent(p, kwargs.pop("merge_label", ""))
            for p in parents_in[1:]
        )
        nodes[commit] = VersionNode(
            hash=commit,
            parents=parents_in,
            main_parent=main_parent,
            merge_parents=merge_parents,
            tags=kwargs.get("tags", ()),
            author_name="A",
            author_email="a@b.com",
            author_time=topo[commit],
            commit_time=topo[commit],
            subject=kwargs.get("subject", "msg"),
            topo_rank=topo[commit],
            is_head_file_version=kwargs.get("is_head", False),
        )
        if main_parent:
            edges.append(Edge(main_parent, commit, "main"))
        for mp in merge_parents:
            edges.append(Edge(mp.hash, commit, "merge", mp.label))

    return GraphModel(
        nodes=nodes,
        edges=tuple(edges),
        order_newest_first=tuple(order_newest),
        order_oldest_first=tuple(order_oldest),
        branches={},
    )


# ── tests ──────────────────────────────────────────────────────────────────

def test_empty_graph():
    empty = GraphModel({}, (), (), (), {})
    result = BranchRebuilder().rebuild(empty)
    assert len(result.nodes) == 0
    assert len(result.branches) == 0


def test_single_commit_on_main():
    c0 = h(0)
    graph = _raw_graph([(c0, (), {"is_head": True})])
    result = BranchRebuilder().rebuild(graph, main_branch="main")

    assert result.nodes[c0].reconstructed_branch == "main"
    assert result.nodes[c0].per_branch_index == 0
    assert "main" in result.branches


def test_linear_chain_all_on_main():
    commits = [h(i) for i in range(5)]
    specs = [(commits[i], (commits[i - 1],) if i else (), {}) for i in range(4, -1, -1)]
    specs[0] = (commits[4], (commits[3],), {"is_head": True})
    graph = _raw_graph(specs)
    result = BranchRebuilder().rebuild(graph, main_branch="main")

    for c in commits:
        assert result.nodes[c].reconstructed_branch == "main"
    assert len(result.branches) == 1
    assert "main" in result.branches


def test_feature_branch_gets_separate_name():
    # main: c0 → c1 → c2;  feature: f0 forked from c1
    c0, c1, c2 = h(0), h(1), h(2)
    f0 = h(10)
    # merge: c2 merges f0 with message "Merge branch 'feature'"
    cm = h(20)
    specs = [
        (cm, (c2, f0), {"subject": "Merge branch 'feature'", "is_head": True}),
        (c2, (c1,), {}),
        (f0, (c1,), {}),
        (c1, (c0,), {}),
        (c0, (), {}),
    ]
    graph = _raw_graph(specs)
    result = BranchRebuilder().rebuild(graph, main_branch="main")

    branches = set(n.reconstructed_branch for n in result.nodes.values())
    assert "main" in branches
    assert len(branches) >= 2  # at least main + one feature branch


def test_branch_edges_assigned():
    # Two nodes on different branches should produce a "branch" edge
    c0, c1 = h(0), h(1)
    f0 = h(10)
    specs = [
        (f0, (c0,), {}),
        (c1, (c0,), {"is_head": True}),
        (c0, (), {}),
    ]
    graph = _raw_graph(specs)
    result = BranchRebuilder().rebuild(graph, main_branch="main")

    src_branches = {e.src: result.nodes[e.src].reconstructed_branch for e in result.edges}
    dst_branches = {e.dst: result.nodes[e.dst].reconstructed_branch for e in result.edges}
    branch_edges = [e for e in result.edges if e.kind == "branch"]
    # At least one edge should cross branch boundaries
    cross = [
        e for e in result.edges
        if result.nodes[e.src].reconstructed_branch != result.nodes[e.dst].reconstructed_branch
    ]
    assert len(cross) > 0
    assert all(e.kind == "branch" for e in cross)


def test_merge_edges_preserved():
    c0, c1, cm = h(0), h(1), h(2)
    specs = [
        (cm, (c1, c0), {"subject": "Merge branch 'feat'", "is_head": True}),
        (c1, (c0,), {}),
        (c0, (), {}),
    ]
    graph = _raw_graph(specs)
    result = BranchRebuilder().rebuild(graph, main_branch="main")
    merge_edges = [e for e in result.edges if e.kind == "merge"]
    assert len(merge_edges) == 1
    assert merge_edges[0].dst == cm


def test_per_branch_index_sequential():
    commits = [h(i) for i in range(4)]
    specs = [(commits[i], (commits[i - 1],) if i else (), {}) for i in range(3, -1, -1)]
    specs[0] = (commits[3], (commits[2],), {"is_head": True})
    graph = _raw_graph(specs)
    result = BranchRebuilder().rebuild(graph, main_branch="main")

    indices = sorted(result.nodes[c].per_branch_index for c in commits)
    assert indices == [0, 1, 2, 3]


def test_main_branch_gets_column_hint_zero():
    c0 = h(0)
    graph = _raw_graph([(c0, (), {"is_head": True})])
    result = BranchRebuilder().rebuild(graph, main_branch="main")
    assert result.branches["main"].column_hint == 0
