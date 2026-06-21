"""Tests for TreeLayout: row assignment, interval packing, coordinates, edges."""
from __future__ import annotations

import math

import pytest

from git_lsvtree_ui.core.collapse_model import CollapseModel
from git_lsvtree_ui.layout.geometry import Point
from git_lsvtree_ui.layout.tree_layout import LayoutEdge, LayoutNode, LayoutSettings, TreeLayout

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


# ── merge crossing metric ───────────────────────────────────────────────────

def test_merge_branch_edges_skip_missing_endpoints():
    from git_lsvtree_ui.core.graph_model import DisplayEdge, DisplayGraph

    dg = make_display_graph(
        [("a0", "A", 0, ()), ("m0", "main", 3, ())],
        [],
    )
    dg = DisplayGraph(dict(dg.nodes), (DisplayEdge("a0", "m0", "merge"), DisplayEdge("ghost", "m0", "merge")))
    rows = TreeLayout(S)._row_by_node(dg)

    edges = TreeLayout(S)._merge_branch_edges(dg, rows)

    assert edges == [("A", "main", rows["a0"], rows["m0"])]


def test_crossing_count_shared_endpoint_not_crossing():
    merge_edges = [
        ("A", "main", 0, 10),
        ("B", "main", 2, 8),
    ]
    col = {"main": 0, "A": 3, "B": 1}

    assert TreeLayout(S)._crossing_count(merge_edges, col) == 0


def test_crossing_count_strict_interleave_counts_one():
    merge_edges = [
        ("A", "B", 0, 10),
        ("C", "D", 2, 8),
    ]
    col = {"A": 0, "B": 2, "C": 1, "D": 3}

    assert TreeLayout(S)._crossing_count(merge_edges, col) == 1


def test_crossing_count_touching_rows_not_crossing():
    merge_edges = [
        ("A", "B", 0, 5),
        ("C", "D", 5, 10),
    ]
    col = {"A": 0, "B": 2, "C": 1, "D": 3}

    assert TreeLayout(S)._crossing_count(merge_edges, col) == 0


def test_crossing_count_ignores_same_column_merge_edge():
    merge_edges = [
        ("A", "B", 0, 10),
        ("C", "D", 2, 8),
    ]
    col = {"A": 1, "B": 1, "C": 0, "D": 2}

    assert TreeLayout(S)._crossing_count(merge_edges, col) == 0


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


def test_columns_satisfy_parent_constraints_accepts_valid_columns():
    col = {"main": 0, "feature": 1, "nested": 2}
    pm = {"feature": "main", "nested": "feature"}
    assert TreeLayout(S)._columns_satisfy_parent_constraints(col, pm)


def test_columns_satisfy_parent_constraints_rejects_child_not_right_of_parent():
    col = {"main": 0, "feature": 0}
    pm = {"feature": "main"}
    assert not TreeLayout(S)._columns_satisfy_parent_constraints(col, pm)


def test_parent_constraint_violation_count_counts_all_violations():
    col = {"main": 0, "feature": 0, "nested": 1}
    pm = {"feature": "main", "nested": "feature"}
    assert TreeLayout(S)._parent_constraint_violation_count(col, pm) == 1


def test_columns_satisfy_interval_packing_accepts_non_overlapping_same_column():
    col = {"feature-a": 1, "feature-b": 1}
    rng = {"feature-a": (2, 4), "feature-b": (7, 9)}
    assert TreeLayout(S)._columns_satisfy_interval_packing(col, rng)


def test_columns_satisfy_interval_packing_rejects_overlap_with_gap():
    col = {"feature-a": 1, "feature-b": 1}
    rng = {"feature-a": (2, 4), "feature-b": (5, 9)}
    assert not TreeLayout(S)._columns_satisfy_interval_packing(col, rng)


def test_interval_packing_violation_count_counts_overlaps():
    col = {"A": 1, "B": 1, "C": 1}
    rng = {"A": (0, 5), "B": (3, 7), "C": (10, 12)}
    assert TreeLayout(S)._interval_packing_violation_count(col, rng) == 1


def test_pack_columns_output_satisfies_constraints():
    rng = {"main": (0, 10), "A": (2, 5), "B": (7, 9), "C": (3, 4)}
    pm = {"A": "main", "B": "main", "C": "A"}
    layout = TreeLayout(S)
    col = layout._pack_columns(["main", "A", "B", "C"], rng, pm, "main")
    assert layout._columns_satisfy_parent_constraints(col, pm)
    assert layout._columns_satisfy_interval_packing(col, rng)


def test_pack_columns_without_merge_edges_keeps_greedy_behavior():
    rng = {"main": (0, 10), "X": (1, 5), "A": (2, 3), "B": (7, 8)}
    pm = {"X": "main", "A": "main", "B": "main"}

    col = TreeLayout(S)._pack_columns(["main", "X", "A", "B"], rng, pm, "main")

    assert col["X"] == 1
    assert col["A"] == 2
    assert col["B"] == 1


def test_pack_columns_merge_span_prefers_legal_column_near_partner():
    rng = {"main": (0, 10), "X": (1, 5), "A": (2, 3), "B": (7, 8)}
    pm = {"X": "main", "A": "main", "B": "main"}
    merge_edges = [("A", "B", 2, 8)]

    layout = TreeLayout(S)
    col = layout._pack_columns(["main", "X", "A", "B"], rng, pm, "main", merge_edges=merge_edges)

    assert col["X"] == 1
    assert col["A"] == 2
    assert col["B"] == 2
    assert layout._columns_satisfy_parent_constraints(col, pm)
    assert layout._columns_satisfy_interval_packing(col, rng)


def test_pack_columns_merge_aware_does_not_violate_child_constraint():
    rng = {"main": (0, 10), "A": (1, 3), "B": (4, 5)}
    pm = {"A": "main", "B": "A"}
    merge_edges = [("main", "B", 0, 5)]

    col = TreeLayout(S)._pack_columns(["main", "A", "B"], rng, pm, "main", merge_edges=merge_edges)

    assert col["main"] < col["A"] < col["B"]


def test_candidate_column_score_prefers_narrower_column_when_crossing_equal():
    layout = TreeLayout(S)
    placed = {"main": 0}
    merge_edges = [("A", "B", 0, 1)]

    narrow = layout._candidate_column_score("A", 1, 1, 1, placed, merge_edges)
    wide = layout._candidate_column_score("A", 3, 1, 1, placed, merge_edges)

    assert narrow < wide


def test_candidate_column_score_rejects_far_column_for_small_span_gain():
    layout = TreeLayout(S)
    placed = {"main": 0, "partner": 4}
    merge_edges = [("A", "partner", 0, 1)]

    narrow = layout._candidate_column_score("A", 1, 1, 1, placed, merge_edges)
    far = layout._candidate_column_score("A", 4, 1, 1, placed, merge_edges)

    assert narrow < far


def test_swap_optimize_reduces_crossings_when_constraints_allow():
    layout = TreeLayout(S)
    col = {"A": 0, "B": 2, "C": 1, "D": 3}
    row_ranges = {"A": (0, 10), "B": (0, 10), "C": (0, 10), "D": (0, 10)}
    merge_edges = [("A", "B", 0, 10), ("C", "D", 2, 8)]

    optimized = layout._swap_optimize_columns(col, row_ranges, {}, merge_edges)

    assert layout._crossing_count(merge_edges, optimized) < layout._crossing_count(merge_edges, col)
    assert layout._columns_satisfy_parent_constraints(optimized, {})
    assert layout._columns_satisfy_interval_packing(optimized, row_ranges)


def test_swap_optimize_rejects_parent_child_violation(monkeypatch):
    layout = TreeLayout(S)
    col = {"A": 0, "C": 1}
    row_ranges = {"A": (0, 1), "C": (0, 1)}
    parent_map = {"C": "A"}
    merge_edges = [("A", "C", 0, 1)]

    def fake_crossing_count(_merge_edges, candidate_col):
        return 0 if candidate_col == {"A": 1, "C": 0} else 1

    monkeypatch.setattr(layout, "_crossing_count", fake_crossing_count)

    optimized = layout._swap_optimize_columns(col, row_ranges, parent_map, merge_edges)

    assert optimized == col
    assert layout._columns_satisfy_parent_constraints(optimized, parent_map)


def test_swap_optimize_rejects_interval_overlap(monkeypatch):
    layout = TreeLayout(S)
    col = {"A": 0, "B": 1, "C": 1}
    row_ranges = {"A": (10, 11), "B": (0, 1), "C": (10, 11)}
    merge_edges = [("A", "B", 10, 0)]

    def fake_crossing_count(_merge_edges, candidate_col):
        return 0 if candidate_col == {"A": 1, "B": 0, "C": 1} else 1

    monkeypatch.setattr(layout, "_crossing_count", fake_crossing_count)

    optimized = layout._swap_optimize_columns(col, row_ranges, {}, merge_edges)

    assert optimized == col
    assert layout._columns_satisfy_interval_packing(optimized, row_ranges)


def test_swap_optimize_stops_after_max_passes():
    layout = TreeLayout(S)
    col = {"A": 0, "B": 2, "C": 1, "D": 3}
    row_ranges = {"A": (0, 10), "B": (0, 10), "C": (0, 10), "D": (0, 10)}
    merge_edges = [("A", "B", 0, 10), ("C", "D", 2, 8)]

    optimized = layout._swap_optimize_columns(col, row_ranges, {}, merge_edges, max_passes=0)

    assert optimized == col


def test_layout_invokes_swap_optimizer_for_merge_edges(monkeypatch):
    calls = []

    def fake_swap(self, col, row_ranges, parent_map, merge_edges, max_passes=3):
        calls.append((dict(col), dict(row_ranges), dict(parent_map), list(merge_edges), max_passes))
        return col

    monkeypatch.setattr(TreeLayout, "_swap_optimize_columns", fake_swap)
    dg = make_display_graph(
        [("a0", "A", 0, ()), ("m0", "main", 1, ())],
        [("a0", "m0", "merge")],
    )

    TreeLayout(S).layout(dg, branch_order=("main", "A"))

    assert len(calls) == 1
    assert calls[0][3] == [("A", "main", 0, 1)]


def test_layout_metrics_reports_width_crossings_and_merge_span():
    dg = make_display_graph(
        [
            ("m0", "main", 0, ()),
            ("m1", "main", 5, ()),
            ("a0", "A", 1, ()),
            ("a1", "A", 2, ()),
        ],
        [
            ("m0", "a0", "branch"),
            ("a1", "m1", "merge"),
        ],
    )

    metrics = TreeLayout(S).layout_metrics(dg, branch_order=("main", "A"))

    assert metrics.branch_count == 2
    assert metrics.max_column == 1
    assert metrics.canvas_width == S.branch_col_width * 2
    assert metrics.merge_edge_count == 1
    assert metrics.merge_crossing_count == 0
    assert metrics.total_merge_span == 1
    assert metrics.max_merge_span == 1
    assert metrics.parent_constraint_violations == 0
    assert metrics.interval_packing_violations == 0


def test_layout_metrics_empty_graph_is_zeroed():
    dg = make_display_graph([], [])

    metrics = TreeLayout(S).layout_metrics(dg)

    assert metrics.branch_count == 0
    assert metrics.max_column == 0
    assert metrics.canvas_width == 0
    assert metrics.merge_edge_count == 0
    assert metrics.merge_crossing_count == 0


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


def test_layout_respects_non_main_branch_order_hint_for_primary_column():
    dg = make_display_graph(
        [("d0", "develop", 0, ()), ("d1", "develop", 1, ()), ("f0", "feature", 2, ())],
        [("d1", "f0", "branch")],
    )

    layout = _layout(dg, branch_order=("develop", "feature"))

    develop_x = {n.center.x for n in layout.nodes.values() if n.branch == "develop"}
    feature_x = {n.center.x for n in layout.nodes.values() if n.branch == "feature"}
    assert develop_x == {S.left_margin}
    assert min(feature_x) > S.left_margin


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


def test_layout_edges_default_to_line_route():
    graph = linear_graph(3)
    dg = CollapseModel(enabled=False).build(graph)
    layout = _layout(dg, branch_order=("main",))

    assert layout.edges
    assert all(edge.route_kind == "line" for edge in layout.edges)
    assert all(edge.control_points == () for edge in layout.edges)


def test_parallel_merge_edges_get_distinct_quadratic_routes():
    dg = make_display_graph(
        [
            ("a0", "A", 0, ()),
            ("b0", "B", 1, ()),
        ],
        [
            ("a0", "b0", "merge"),
            ("b0", "a0", "merge"),
        ],
    )

    layout = _layout(dg, branch_order=("A", "B"))
    merge_edges = [edge for edge in layout.edges if edge.kind == "merge"]

    assert len(merge_edges) == 2
    assert all(edge.route_kind == "quadratic" for edge in merge_edges)
    assert merge_edges[0].control_points != merge_edges[1].control_points
    assert {edge.route_group_size for edge in merge_edges} == {2}
    assert min(
        math.hypot(
            left.control_points[0].x - right.control_points[0].x,
            left.control_points[0].y - right.control_points[0].y,
        )
        for index, left in enumerate(merge_edges)
        for right in merge_edges[index + 1:]
    ) >= 12.0


def test_many_parallel_merge_edges_reduce_stroke_and_keep_control_separation():
    dg = make_display_graph(
        [
            ("a0", "A", 0, ()),
            ("b0", "B", 1, ()),
        ],
        [
            ("a0", "b0", "merge"),
            ("b0", "a0", "merge"),
            ("a0", "b0", "merge"),
            ("b0", "a0", "merge"),
            ("a0", "b0", "merge"),
        ],
    )

    layout = _layout(dg, branch_order=("A", "B"))
    merge_edges = [edge for edge in layout.edges if edge.kind == "merge"]
    control_points = [edge.control_points[0] for edge in merge_edges]

    assert len(merge_edges) == 5
    assert all(edge.route_kind == "quadratic" for edge in merge_edges)
    assert all(edge.stroke_width < 2.0 for edge in merge_edges)
    assert min(
        math.hypot(left.x - right.x, left.y - right.y)
        for index, left in enumerate(control_points)
        for right in control_points[index + 1:]
    ) >= 12.0


def test_merge_edge_through_intermediate_node_gets_curve_route():
    dg = make_display_graph(
        [
            ("a0", "main", 0, ()),
            ("mid", "main", 1, ()),
            ("a1", "main", 2, ()),
        ],
        [
            ("a0", "a1", "merge"),
        ],
    )

    layout = _layout(dg, branch_order=("main",))
    edge = layout.edges[0]

    assert edge.route_kind == "quadratic"
    assert edge.control_points
    assert edge.route_offset != 0


def test_route_offset_mirrors_when_other_side_reduces_crossing():
    layout = TreeLayout(S)
    candidate = LayoutEdge(
        src="a",
        dst="b",
        kind="merge",
        label="",
        start=Point(0, 0),
        end=Point(100, 0),
    )
    routed = [
        LayoutEdge(
            src="c",
            dst="d",
            kind="merge",
            label="",
            start=Point(0, 20),
            end=Point(100, 20),
        )
    ]

    chosen = layout._choose_mirrored_route_offset(candidate, 60.0, routed, {})

    assert chosen == -60.0
    assert layout._route_candidate_score(candidate, chosen, routed, {}) < layout._route_candidate_score(
        candidate,
        60.0,
        routed,
        {},
    )


def test_route_offset_keeps_side_when_mirror_would_hit_node_obstacle():
    layout = TreeLayout(S)
    candidate = LayoutEdge(
        src="a",
        dst="b",
        kind="merge",
        label="",
        start=Point(0, 0),
        end=Point(100, 100),
    )
    mirror_control = layout._quadratic_control_point(candidate.start, candidate.end, -60.0)
    nodes = {
        "a": LayoutNode("a", "version", "main", 0, candidate.start, 10, "a", ("a",)),
        "b": LayoutNode("b", "version", "main", 1, candidate.end, 10, "b", ("b",)),
        "obstacle": LayoutNode("obstacle", "version", "main", 2, mirror_control, 10, "o", ("o",)),
    }

    chosen = layout._choose_mirrored_route_offset(candidate, 60.0, [], nodes)

    assert chosen == 60.0


def test_endpoint_nodes_are_not_treated_as_obstacles():
    dg = make_display_graph(
        [
            ("a0", "main", 0, ()),
            ("a1", "main", 1, ()),
        ],
        [
            ("a0", "a1", "merge"),
        ],
    )

    layout = _layout(dg, branch_order=("main",))
    edge = layout.edges[0]

    assert edge.route_kind == "line"
    assert edge.stroke_width == 2.0


def test_distance_point_to_segment():
    distance = TreeLayout(S)._distance_point_to_segment(
        point=Point(5, 3),
        start=Point(0, 0),
        end=Point(10, 0),
    )

    assert abs(distance - 3) < 0.001


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
