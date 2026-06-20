"""Tests for KeySelector."""
from __future__ import annotations

import pytest

from git_lsvtree_ui.core.key_selector import KeySelector

from .conftest import h, linear_graph, two_branch_graph


def test_full_mode_returns_all_nodes():
    graph = linear_graph(10)
    result = KeySelector().select(graph, mode="full")
    assert len(result.graph.nodes) == 10
    assert not result.partial


def test_small_graph_below_threshold_returned_unchanged():
    graph = linear_graph(5)
    result = KeySelector().select(graph, mode="key", threshold=10)
    assert len(result.graph.nodes) == 5
    assert not result.partial


def test_threshold_zero_raises():
    graph = linear_graph(3)
    with pytest.raises(ValueError):
        KeySelector().select(graph, mode="key", threshold=0)


def test_skeleton_includes_branch_tips():
    # Branch tips = first and last node of each branch
    graph = linear_graph(10)
    result = KeySelector().select(graph, mode="key", threshold=5)
    node_ids = set(result.graph.nodes.keys())
    main_nodes = list(graph.branches["main"].nodes)
    assert main_nodes[0] in node_ids   # oldest tip
    assert main_nodes[-1] in node_ids  # newest tip (HEAD)


def test_skeleton_includes_branch_points():
    # Fork point has outdeg > 1 → must be in skeleton
    graph = two_branch_graph(main_n=8, fork_at=3, feat_n=4)
    result = KeySelector().select(graph, mode="key", threshold=4)
    # Fork point is h(3)
    assert h(3) in result.graph.nodes


def test_skeleton_includes_merge_src_and_dst():
    # Test _skeleton() directly: merge src and dst must be in skeleton regardless of threshold
    from git_lsvtree_ui.core.graph_model import GraphModel, Edge
    graph = linear_graph(6)
    merge_edge = Edge(h(1), h(4), "merge", "merge from feat")
    graph2 = GraphModel(
        nodes=graph.nodes, edges=graph.edges + (merge_edge,),
        order_newest_first=graph.order_newest_first,
        order_oldest_first=graph.order_oldest_first,
        branches=graph.branches,
    )
    skeleton = KeySelector()._skeleton(graph2)
    assert h(1) in skeleton
    assert h(4) in skeleton


def test_tag_nodes_fill_budget_after_skeleton():
    import dataclasses
    from git_lsvtree_ui.core.graph_model import GraphModel
    graph = linear_graph(20)
    # Tag node h(10) — should be added after skeleton (tips) within budget
    tagged_id = h(10)
    new_nodes = dict(graph.nodes)
    new_nodes[tagged_id] = dataclasses.replace(graph.nodes[tagged_id], tags=("v1.5",))
    graph2 = GraphModel(
        nodes=new_nodes, edges=graph.edges,
        order_newest_first=graph.order_newest_first,
        order_oldest_first=graph.order_oldest_first,
        branches=graph.branches,
    )
    result = KeySelector().select(graph2, mode="key", threshold=5)
    assert tagged_id in result.graph.nodes


def test_partial_flag_set_when_skeleton_exceeds_threshold():
    # Force a skeleton that exceeds threshold by using many merge edges
    from git_lsvtree_ui.core.graph_model import GraphModel, Edge
    graph = linear_graph(20)
    # Add many merge edges to bloat the skeleton
    extra_edges = tuple(
        Edge(h(i), h(i + 5), "merge") for i in range(10)
    )
    graph2 = GraphModel(
        nodes=graph.nodes, edges=graph.edges + extra_edges,
        order_newest_first=graph.order_newest_first,
        order_oldest_first=graph.order_oldest_first,
        branches=graph.branches,
    )
    result = KeySelector().select(graph2, mode="key", threshold=2)
    assert result.partial
    assert result.warning != ""


def test_selected_graph_edges_only_between_visible_nodes():
    graph = linear_graph(20)
    result = KeySelector().select(graph, mode="key", threshold=5)
    node_ids = set(result.graph.nodes.keys())
    for edge in result.graph.edges:
        assert edge.src in node_ids
        assert edge.dst in node_ids
