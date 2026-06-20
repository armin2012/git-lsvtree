"""Tests for TreeLayout: row assignment, interval packing, coordinates, edges."""
from __future__ import annotations

import math

import pytest

from git_lsvtree_ui.core.collapse_model import CollapseModel
from git_lsvtree_ui.layout.tree_layout import LayoutSettings, TreeLayout

from .conftest import h, linear_graph, make_display_graph, two_branch_graph


S = LayoutSettings()
TL = TreeLayout(S)


def _layout(dg, branch_order=None):
    return TreeLayout(S).layout(dg, branch_order=branch_order)


# ── _row_by_node ───────────────────────────────────────────────────────────

def test_row_by_node_sorted_by_topo_rank():
    dg = make_display_graph(
        [("c2", "main", 2, ()), ("c0", "main", 0, ()), ("c1", "main", 1, ())],
        [],
    )
    rows = TreeLayout(S)._row_by_node(dg)
    assert rows["c0"] < rows["c1"] < rows["c2"]


def test_row_by_node_zero_indexed():
    dg = make_display_graph([("c0", "main", 5, ()), ("c1", "main", 10, ())], [])
    rows = TreeLayout(S)._row_by_node(dg)
    assert sorted(rows.values()) == [0, 1]


# ── _row_ranges ────────────────────────────────────────────────────────────

def test_row_ranges_single_branch():
    dg = make_display_graph(
        [("c0", "main", 0, ()), ("c1", "main", 1, ()), ("c2", "main", 2, ())],
        [],
    )
    rows = TreeLayout(S)._row_by_node(dg)
    rng = TreeLayout(S)._row_ranges(dg, rows)
    assert rng["main"] == (0, 2)


def test_row_ranges_two_branches():
    dg = make_display_graph(
        [("m0", "main", 0, ()), ("m1", "main", 1, ()),
         ("f0", "feat", 2, ()), ("f1", "feat", 3, ())],
        [],
    )
    rows = TreeLayout(S)._row_by_node(dg)
    rng = TreeLayout(S)._row_ranges(dg, rows)
    assert rng["main"][0] < rng["main"][1]
    assert rng["feat"][0] < rng["feat"][1]
    assert rng["main"][1] < rng["feat"][0]  # main rows below feat rows


# ── _parent_branch_map ─────────────────────────────────────────────────────

def test_parent_branch_map_correct_direction():
    # branch edge: src=main_commit (parent), dst=feat_commit (child)
    dg = make_display_graph(
        [("m0", "main", 0, ()), ("f0", "feat", 1, ())],
        [("m0", "f0", "branch")],   # src=parent, dst=child
    )
    pm = TreeLayout(S)._parent_branch_map(dg)
    assert pm.get("feat") == "main"
    assert "main" not in pm  # main has no parent


def test_parent_branch_map_ignores_non_branch_edges():
    dg = make_display_graph(
        [("c0", "main", 0, ()), ("c1", "main", 1, ())],
        [("c0", "c1", "main")],
    )
    pm = TreeLayout(S)._parent_branch_map(dg)
    assert pm == {}


def test_parent_branch_map_skips_missing_nodes():
    dg = make_display_graph(
        [("m0", "main", 0, ())],
        [],
    )
    # Edge referencing non-existent node should not crash
    from git_lsvtree_ui.core.graph_model import DisplayEdge, DisplayGraph
    nodes = dict(dg.nodes)
    edges = (DisplayEdge("m0", "ghost", "branch"),)
    dg2 = DisplayGraph(nodes, edges)
    pm = TreeLayout(S)._parent_branch_map(dg2)
    assert "ghost" not in pm


# ── _pack_columns ──────────────────────────────────────────────────────────

def test_pack_columns_main_always_col0():
    rng = {"main": (0, 10)}
    col = TreeLayout(S)._pack_columns(["main"], rng, {}, "main")
    assert col["main"] == 0


def test_pack_columns_sibling_branches_share_column():
    """feat-A (rows 2–4) and feat-B (rows 7–9) are siblings; no overlap → share col 1."""
    rng = {"main": (0, 10), "feat-A": (2, 4), "feat-B": (7, 9)}
    pm = {"feat-A": "main", "feat-B": "main"}
    col = TreeLayout(S)._pack_columns(["main", "feat-A", "feat-B"], rng, pm, "main")
    assert col["main"] == 0
    assert col["feat-A"] == 1
    assert col["feat-B"] == 1  # shares col 1, no overlap


def test_pack_columns_overlapping_siblings_get_different_columns():
    """feat-A (rows 2–8) and feat-B (rows 5–9) overlap → different columns."""
    rng = {"main": (0, 10), "feat-A": (2, 8), "feat-B": (5, 9)}
    pm = {"feat-A": "main", "feat-B": "main"}
    col = TreeLayout(S)._pack_columns(["main", "feat-A", "feat-B"], rng, pm, "main")
    assert col["main"] == 0
    assert col["feat-A"] != col["feat-B"]


def test_pack_columns_child_right_of_parent():
    """feat-C is a child of feat-A (col 1) → feat-C must be in col ≥ 2."""
    rng = {"main": (0, 10), "feat-A": (2, 4), "feat-C": (3, 5)}
    pm = {"feat-A": "main", "feat-C": "feat-A"}
    col = TreeLayout(S)._pack_columns(["main", "feat-A", "feat-C"], rng, pm, "main")
    assert col["feat-C"] > col["feat-A"]


def test_pack_columns_deep_nesting():
    """main→A→B→C: columns must be strictly increasing."""
    rng = {"main": (0, 10), "A": (1, 3), "B": (2, 3), "C": (2, 3)}
    pm = {"A": "main", "B": "A", "C": "B"}
    col = TreeLayout(S)._pack_columns(["main", "A", "B", "C"], rng, pm, "main")
    assert col["main"] < col["A"] < col["B"] < col["C"]


def test_pack_columns_no_parent_treated_as_root():
    """A branch with no known parent gets assigned col ≥ 1."""
    rng = {"main": (0, 5), "orphan": (2, 4)}
    col = TreeLayout(S)._pack_columns(["main", "orphan"], rng, {}, "main")
    assert col["orphan"] >= 1


# ── layout: coordinates ────────────────────────────────────────────────────

def test_layout_node_x_matches_column():
    graph = linear_graph(3)
    dg = CollapseModel(enabled=False).build(graph)
    layout = _layout(dg, branch_order=("main",))
    for node in layout.nodes.values():
        expected_x = S.left_margin + 0 * S.branch_col_width  # main is col 0
        assert abs(node.center.x - expected_x) < 1


def test_layout_node_y_monotone_with_rank():
    graph = linear_graph(5)
    dg = CollapseModel(enabled=False).build(graph)
    layout = _layout(dg, branch_order=("main",))
    sorted_nodes = sorted(layout.nodes.values(), key=lambda n: n.topo_rank)
    ys = [n.center.y for n in sorted_nodes]
    assert ys == sorted(ys)


def test_layout_two_branch_column_separation():
    graph = two_branch_graph(main_n=6, fork_at=2, feat_n=3)
    dg = CollapseModel(enabled=False).build(graph)
    layout = _layout(dg, branch_order=("main", "feature"))
    main_x = {n.center.x for n in layout.nodes.values() if n.branch == "main"}
    feat_x = {n.center.x for n in layout.nodes.values() if n.branch == "feature"}
    assert len(main_x) == 1 and len(feat_x) == 1
    assert list(feat_x)[0] > list(main_x)[0]  # feature is to the right of main


# ── layout: edge endpoints ─────────────────────────────────────────────────

def test_layout_edge_endpoints_offset_by_radius():
    graph = linear_graph(3)
    dg = CollapseModel(enabled=False).build(graph)
    layout = _layout(dg, branch_order=("main",))
    r = S.node_radius
    for edge in layout.edges:
        sc = layout.nodes[edge.src].center
        dc = layout.nodes[edge.dst].center
        d_start = math.hypot(edge.start.x - sc.x, edge.start.y - sc.y)
        d_end = math.hypot(edge.end.x - dc.x, edge.end.y - dc.y)
        assert abs(d_start - r) < 0.5, f"start not at circle boundary: {d_start}"
        assert abs(d_end - r) < 0.5, f"end not at circle boundary: {d_end}"


def test_layout_fork_edges_at_most_one_column_wide():
    graph = two_branch_graph(main_n=8, fork_at=3, feat_n=4)
    dg = CollapseModel(enabled=False).build(graph)
    layout = _layout(dg, branch_order=("main", "feature"))
    branch_edges = [e for e in layout.edges if e.kind == "branch"]
    assert len(branch_edges) >= 1
    for e in branch_edges:
        dx = abs(layout.nodes[e.src].center.x - layout.nodes[e.dst].center.x)
        assert dx <= S.branch_col_width + 1, f"fork edge too wide: dx={dx}"


# ── layout: headers ────────────────────────────────────────────────────────

def test_layout_header_at_fork_row():
    """Each branch header should be near its first node's y position."""
    graph = two_branch_graph(main_n=8, fork_at=3, feat_n=4)
    dg = CollapseModel(enabled=False).build(graph)
    layout = _layout(dg, branch_order=("main", "feature"))

    for branch, hdr in layout.branch_headers.items():
        branch_nodes = [n for n in layout.nodes.values() if n.branch == branch]
        if not branch_nodes:
            continue
        first_node_y = min(n.center.y for n in branch_nodes)
        # Header must be above or at the first node
        assert hdr.rect.y < first_node_y, (
            f"{branch}: header y={hdr.rect.y} not above first node y={first_node_y}"
        )
        # Header must not be more than 2 rows above the first node
        assert hdr.rect.y >= first_node_y - 2 * S.row_height


def test_layout_main_header_at_top():
    graph = linear_graph(5)
    dg = CollapseModel(enabled=False).build(graph)
    layout = _layout(dg, branch_order=("main",))
    hdr_y = layout.branch_headers["main"].rect.y
    # For main (first row = 0), header should be near top_margin
    assert abs(hdr_y - (S.top_margin - 2)) < 1


# ── layout: tags ───────────────────────────────────────────────────────────

def test_layout_tags_propagated_to_layout_node():
    import dataclasses
    from git_lsvtree_ui.core.graph_model import GraphModel
    graph = linear_graph(3)
    tagged_id = h(0)
    new_nodes = dict(graph.nodes)
    new_nodes[tagged_id] = dataclasses.replace(graph.nodes[tagged_id], tags=("v0.1",))
    from git_lsvtree_ui.core.graph_model import GraphModel
    graph2 = GraphModel(
        nodes=new_nodes, edges=graph.edges,
        order_newest_first=graph.order_newest_first,
        order_oldest_first=graph.order_oldest_first,
        branches=graph.branches,
    )
    dg = CollapseModel(enabled=False).build(graph2)
    layout = _layout(dg, branch_order=("main",))
    assert layout.nodes[tagged_id].tags == ("v0.1",)
