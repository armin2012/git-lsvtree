"""Tests for CollapseModel: collapsing logic and tag propagation."""
from __future__ import annotations

import pytest

from git_lsvtree_ui.core.collapse_model import CollapseModel

from .conftest import h, linear_graph, two_branch_graph


# ── without collapse ───────────────────────────────────────────────────────

def test_without_collapse_preserves_all_nodes():
    graph = linear_graph(5)
    display = CollapseModel(enabled=False).build(graph)
    assert len(display.nodes) == 5
    assert all(n.kind == "version" for n in display.nodes.values())


def test_without_collapse_preserves_all_edges():
    graph = linear_graph(4)
    display = CollapseModel(enabled=False).build(graph)
    assert len(display.edges) == 3


def test_without_collapse_tags_propagated():
    from git_lsvtree_ui.core.graph_model import replace
    graph = linear_graph(3)
    # Tag node h(1)
    tagged_id = h(1)
    tagged = graph.nodes[tagged_id]
    new_nodes = dict(graph.nodes)
    new_nodes[tagged_id] = tagged.__class__(
        **{**tagged.__dict__, "tags": ("v1.0",)}
    )
    from types import MappingProxyType
    from git_lsvtree_ui.core.graph_model import GraphModel
    graph2 = GraphModel(
        nodes=new_nodes,
        edges=graph.edges,
        order_newest_first=graph.order_newest_first,
        order_oldest_first=graph.order_oldest_first,
        branches=graph.branches,
    )
    display = CollapseModel(enabled=False).build(graph2)
    assert display.nodes[tagged_id].tags == ("v1.0",)


# ── with collapse: collapsibility rules ───────────────────────────────────

def test_single_collapsible_not_collapsed():
    # 3 nodes: c0 (indeg=0) → c1 (indeg=1, outdeg=1) → c2 (outdeg=0)
    # c1 alone doesn't form a run (need ≥ 2 consecutive)
    graph = linear_graph(3)
    display = CollapseModel(enabled=True).build(graph)
    runs = [n for n in display.nodes.values() if n.kind == "run"]
    assert len(runs) == 0


def test_two_collapsible_nodes_form_run():
    # 4 nodes: c0 → c1 → c2 → c3; c1 and c2 are collapsible
    graph = linear_graph(4)
    display = CollapseModel(enabled=True).build(graph)
    runs = [n for n in display.nodes.values() if n.kind == "run"]
    assert len(runs) == 1
    assert len(runs[0].source_hashes) == 2


def test_three_collapsible_nodes_form_run():
    # 5 nodes: c0 → c1 → c2 → c3 → c4; c1,c2,c3 collapsible
    graph = linear_graph(5)
    display = CollapseModel(enabled=True).build(graph)
    runs = [n for n in display.nodes.values() if n.kind == "run"]
    assert len(runs) == 1
    assert len(runs[0].source_hashes) == 3
    # c0 and c4 remain as version nodes
    versions = [n for n in display.nodes.values() if n.kind == "version"]
    assert len(versions) == 2


def test_tagged_node_not_collapsed():
    from git_lsvtree_ui.core.graph_model import GraphModel
    graph = linear_graph(5)
    # Tag c2 (middle, would otherwise be collapsible)
    tagged_id = h(2)
    tagged = graph.nodes[tagged_id]
    new_nodes = dict(graph.nodes)
    import dataclasses
    new_nodes[tagged_id] = dataclasses.replace(tagged, tags=("v1.0",))
    graph2 = GraphModel(
        nodes=new_nodes, edges=graph.edges,
        order_newest_first=graph.order_newest_first,
        order_oldest_first=graph.order_oldest_first,
        branches=graph.branches,
    )
    display = CollapseModel(enabled=True).build(graph2)
    # h(2) must appear as a version node, not inside a run
    assert tagged_id in display.nodes
    assert display.nodes[tagged_id].kind == "version"


def test_tags_propagated_to_display_node():
    """VersionNode.tags must flow into DisplayNode.tags."""
    from git_lsvtree_ui.core.graph_model import GraphModel
    import dataclasses
    graph = linear_graph(3)
    tagged_id = h(0)  # oldest node (not collapsible: indeg=0)
    new_nodes = dict(graph.nodes)
    new_nodes[tagged_id] = dataclasses.replace(graph.nodes[tagged_id], tags=("release-1",))
    graph2 = GraphModel(
        nodes=new_nodes, edges=graph.edges,
        order_newest_first=graph.order_newest_first,
        order_oldest_first=graph.order_oldest_first,
        branches=graph.branches,
    )
    display = CollapseModel(enabled=True).build(graph2)
    assert display.nodes[tagged_id].tags == ("release-1",)


def test_branch_fork_node_not_collapsed():
    """Node with outdeg > 1 (branch point) must not be collapsed."""
    graph = two_branch_graph(main_n=5, fork_at=2, feat_n=3)
    display = CollapseModel(enabled=True).build(graph)
    # h(2) is the fork point on main — must remain a version node
    fork_id = h(2)
    assert fork_id in display.nodes
    assert display.nodes[fork_id].kind == "version"


def test_run_source_hashes_ordered():
    """Run source_hashes should be in oldest-first branch order."""
    graph = linear_graph(5)
    display = CollapseModel(enabled=True).build(graph)
    runs = [n for n in display.nodes.values() if n.kind == "run"]
    assert len(runs) == 1
    # c1, c2, c3 in that order (oldest first as per branch info)
    assert runs[0].source_hashes == (h(1), h(2), h(3))


def test_expanded_run_shows_individual_nodes():
    graph = linear_graph(5)
    # First build to discover the run ID
    collapsed = CollapseModel(enabled=True).build(graph)
    runs = [n for n in collapsed.nodes.values() if n.kind == "run"]
    assert len(runs) == 1
    run_id = runs[0].id

    # Expand
    expanded = CollapseModel(enabled=True).build(graph, expanded_runs=frozenset([run_id]))
    runs_after = [n for n in expanded.nodes.values() if n.kind == "run"]
    assert len(runs_after) == 0
    assert len(expanded.nodes) == 5


def test_display_edges_remapped_through_run():
    """Edges should use run ID for src/dst where commits are collapsed."""
    graph = linear_graph(5)
    display = CollapseModel(enabled=True).build(graph)
    node_ids = set(display.nodes.keys())
    for edge in display.edges:
        assert edge.src in node_ids, f"edge.src {edge.src} not in display nodes"
        assert edge.dst in node_ids, f"edge.dst {edge.dst} not in display nodes"


def test_two_branch_graph_edges_preserved():
    graph = two_branch_graph(main_n=5, fork_at=2, feat_n=3)
    display = CollapseModel(enabled=False).build(graph)
    kinds = {e.kind for e in display.edges}
    assert "branch" in kinds
    assert "main" in kinds
