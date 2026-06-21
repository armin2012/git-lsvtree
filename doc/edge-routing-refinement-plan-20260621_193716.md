# Phase 9 Plan: Edge Routing Refinement

- [KNOWN] Date: 2026-06-21
- [KNOWN] Timestamp: 20260621_193716 CST
- [KNOWN] Target module: `layout/tree_layout.py`, `ui/items.py`, `ui/graph_scene.py`
- [KNOWN] Related design doc: `doc/design.md` v1.5 §5.6, §9 Phase 9

---

## 1. Problem Statement

[KNOWN] Current `LayoutEdge` stores only `start` and `end`.

[INFERRED] Dense version trees can therefore render multiple merge edges on the same or nearly same visual path.

[INFERRED] Consequences:

1. [INFERRED] Overlapped merge lines look like one line.
2. [INFERRED] Clicking an overlapped line does not visually communicate which merge edge was selected.
3. [INFERRED] Straight merge lines may pass through unrelated version-node circles.
4. [INFERRED] The existing edge endpoint overlay is useful only after the user can identify and select the intended edge.

---

## 2. Design Decision

[INFERRED] Do not change branch column layout for this problem.

[INFERRED] Add an edge routing refinement layer after node coordinates are known:

- [INFERRED] Keep normal edges straight when they are clear.
- [INFERRED] Route overlapping merge edges as separated quadratic Bezier curves.
- [INFERRED] Route merge edges around unrelated version-node circles when direct paths are too close.
- [INFERRED] Keep edge hit-testing based on the actual rendered path.

[INFERRED] This is a local routing heuristic, not a full Graphviz/dot spline router.

---

## 3. Implementation Phases

### Phase 9.1 — Extend LayoutEdge route model

[KNOWN] File: `layout/tree_layout.py`

Add fields:

```python
route_kind: str = "line"
control_points: tuple[Point, ...] = ()
route_index: int = 0
route_group_size: int = 1
```

[INFERRED] Tests:

- `test_layout_edges_default_to_line_route`
- `test_layout_edge_route_fields_are_immutable_dataclass_values`

### Phase 9.2 — Same-path route grouping

[KNOWN] File: `layout/tree_layout.py`

Add route grouping after all node centers are available.

Suggested route key:

```python
(
    min(src_col, dst_col),
    max(src_col, dst_col),
    min(src_row, dst_row),
    max(src_row, dst_row),
    edge.kind,
)
```

[INFERRED] For each group with `k > 1`, assign symmetric offsets:

```python
offset_slot = index - (k - 1) / 2
offset_px = offset_slot * EDGE_PARALLEL_SPACING
```

[INFERRED] Tests:

- `test_parallel_merge_edges_get_distinct_route_offsets`
- `test_three_parallel_merge_edges_get_symmetric_offsets`
- `test_non_overlapping_edges_remain_line_routes`

### Phase 9.3 — Node obstacle avoidance

[KNOWN] File: `layout/tree_layout.py`

Implement:

```python
_distance_point_to_segment(point, start, end) -> float
_edge_near_non_endpoint_node(edge, nodes) -> bool
```

[INFERRED] If a direct path is closer than `node.radius + EDGE_OBSTACLE_PADDING` to a non-endpoint version node, convert edge to quadratic route with deterministic side offset.

[INFERRED] Tests:

- `test_merge_edge_through_intermediate_node_gets_curve_route`
- `test_endpoint_nodes_are_not_treated_as_obstacles`
- `test_obstacle_offset_is_clamped`

### Phase 9.4 — EdgeItem Bezier rendering

[KNOWN] File: `ui/items.py`

`EdgeItem` should:

- render `line` as today;
- render `quadratic` using `QPainterPath.quadTo(control, end_arrow_base)`;
- compute arrow tangent from `control -> end` for quadratic route;
- keep `shape()` based on the actual path.

[INFERRED] Tests:

- `test_edge_item_uses_quadratic_path_for_routed_edge`
- `test_edge_item_selection_preserves_routed_path`

### Phase 9.5 — Interaction verification

[KNOWN] Files: `ui/graph_scene.py`, `tests/test_app_phase1.py`

[INFERRED] Existing edge selection should remain valid because `itemAt()` and `shape()` will use the routed path.

[INFERRED] Tests:

- `test_graph_scene_routed_edge_selection_replaces_previous_overlay`
- `test_selected_routed_edge_overlay_shows_correct_endpoints`

---

## 4. Constants

Suggested constants:

```python
EDGE_PARALLEL_SPACING = 14.0
EDGE_OBSTACLE_PADDING = 8.0
MAX_ROUTE_OFFSET = 48.0
```

[INFERRED] These should be module-level constants in `layout/tree_layout.py` first, not user-configurable settings, until real repo screenshots prove tuning is needed.

---

## 5. Acceptance Criteria

1. [INFERRED] Same-path merge edges are not rendered on exactly the same path.
2. [INFERRED] Merge edges passing through unrelated version nodes are converted to curved routes.
3. [INFERRED] Main/branch edges remain straight unless they need routing.
4. [INFERRED] Edge click selection still selects the intended edge.
5. [INFERRED] Edge endpoint overlay continues to show correct source/destination metadata.
6. [COMPUTED] All existing tests pass.
7. [COMPUTED] New route tests pass.
8. [INFERRED] Branch column layout is unchanged by edge routing.

---

## 6. Non-goals

1. [INFERRED] No full global spline router.
2. [INFERRED] No Graphviz runtime dependency.
3. [INFERRED] No orthogonal routing.
4. [INFERRED] No guarantee of perfect obstacle avoidance in pathological graphs.
5. [INFERRED] No layout width expansion solely to route edges.

---

## 7. Risk Notes

1. [INFERRED] Curves can reduce overlap but may add visual clutter if offsets are too large.
2. [INFERRED] Too-wide hit-test shape can make nearby curves ambiguous; separated paths and moderate shape width must be balanced.
3. [INFERRED] Arrowhead tangent calculation must be correct, or merge direction becomes visually misleading.
4. [INFERRED] Obstacle avoidance should be deterministic to keep screenshots and tests stable.

[RULES I BROKE]: none.
