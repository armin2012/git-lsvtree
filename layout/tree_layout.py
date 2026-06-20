from __future__ import annotations

import logging
import math
from collections import deque
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from git_lsvtree_ui.core.graph_model import DisplayGraph

from .geometry import Point, Rect


logger = logging.getLogger(__name__)
_CANDIDATE_POOL = 5
_CROSSING_WEIGHT = 200.0
_COLUMN_PENALTY = 2.0
_NEW_COLUMN_PENALTY = 25.0
_EXTRA_DEPTH_PENALTY = 10.0


@dataclass(frozen=True)
class LayoutSettings:
    branch_col_width: float = 180
    row_height: float = 54
    header_height: float = 32
    top_margin: float = 48
    left_margin: float = 40
    node_radius: float = 10
    branch_header_width: float = 90
    branch_header_height: float = 18
    label_offset_x: float = 16


@dataclass(frozen=True)
class LayoutNode:
    id: str
    kind: str
    branch: str
    topo_rank: int
    center: Point
    radius: float
    label: str
    source_hashes: tuple[str, ...]
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class LayoutEdge:
    src: str
    dst: str
    kind: str
    label: str
    start: Point
    end: Point


@dataclass(frozen=True)
class BranchHeader:
    branch: str
    rect: Rect
    label: str


@dataclass(frozen=True)
class LayoutGraph:
    nodes: Mapping[str, LayoutNode]
    edges: tuple[LayoutEdge, ...]
    branch_headers: Mapping[str, BranchHeader]
    bounds: Rect

    def __post_init__(self) -> None:
        object.__setattr__(self, "nodes", MappingProxyType(dict(self.nodes)))
        object.__setattr__(self, "branch_headers", MappingProxyType(dict(self.branch_headers)))


class TreeLayout:
    def __init__(self, settings: LayoutSettings | None = None):
        self.settings = settings or LayoutSettings()
        logger.debug("init tree layout settings=%s", self.settings)

    def layout(
        self,
        display_graph: DisplayGraph,
        branch_order: tuple[str, ...] | None = None,
    ) -> LayoutGraph:
        logger.info(
            "laying out display graph nodes=%d edges=%d",
            len(display_graph.nodes),
            len(display_graph.edges),
        )
        row_by_node = self._row_by_node(display_graph)

        # Dynamic column assignment via branch interval packing
        main_branch = self._infer_main_branch(display_graph, branch_order)
        all_branches = list(dict.fromkeys(
            [main_branch] + [n.branch for n in display_graph.nodes.values()]
        ))
        row_ranges = self._row_ranges(display_graph, row_by_node)
        parent_map = self._parent_branch_map(display_graph)
        merge_edges = self._merge_branch_edges(display_graph, row_by_node)
        branch_col = self._pack_columns(
            all_branches,
            row_ranges,
            parent_map,
            main_branch,
            merge_edges=merge_edges,
        )
        if merge_edges:
            branch_col = self._swap_optimize_columns(
                branch_col,
                row_ranges,
                parent_map,
                merge_edges,
            )

        nodes: dict[str, LayoutNode] = {}
        for node_id, node in display_graph.nodes.items():
            center = Point(
                self.settings.left_margin + branch_col[node.branch] * self.settings.branch_col_width,
                self.settings.top_margin
                + self.settings.header_height
                + self.settings.node_radius
                + row_by_node[node_id] * self.settings.row_height,
            )
            nodes[node_id] = LayoutNode(
                id=node_id,
                kind=node.kind,
                branch=node.branch,
                topo_rank=node.topo_rank,
                center=center,
                radius=self.settings.node_radius,
                label=node.label,
                source_hashes=node.source_hashes,
                tags=node.tags,
            )

        # Branch headers: placed just above each branch's first node (fork point)
        headers: dict[str, BranchHeader] = {}
        for branch, col in branch_col.items():
            if branch not in row_ranges:
                continue
            first_row, _ = row_ranges[branch]
            header_y = (
                self.settings.top_margin
                + first_row * self.settings.row_height
                - 2
            )
            headers[branch] = BranchHeader(
                branch=branch,
                rect=Rect(
                    self.settings.left_margin
                    + col * self.settings.branch_col_width
                    - self.settings.branch_header_width / 2,
                    header_y,
                    self.settings.branch_header_width,
                    self.settings.branch_header_height,
                ),
                label=f"{branch} (reconstructed)",
            )

        edges: list[LayoutEdge] = []
        r = self.settings.node_radius
        for edge in display_graph.edges:
            if edge.src not in nodes or edge.dst not in nodes:
                logger.debug("skip layout edge missing endpoint src=%s dst=%s", edge.src, edge.dst)
                continue
            sc = nodes[edge.src].center
            dc = nodes[edge.dst].center
            dx, dy = dc.x - sc.x, dc.y - sc.y
            length = math.hypot(dx, dy)
            if length > r * 2:
                ux, uy = dx / length, dy / length
                start = Point(sc.x + r * ux, sc.y + r * uy)
                end = Point(dc.x - r * ux, dc.y - r * uy)
            else:
                start, end = sc, dc
            edges.append(
                LayoutEdge(
                    src=edge.src,
                    dst=edge.dst,
                    kind=edge.kind,
                    label=edge.label,
                    start=start,
                    end=end,
                )
            )

        bounds = self._bounds(nodes, headers)
        logger.info(
            "layout complete layout_nodes=%d layout_edges=%d branches=%d bounds=%s",
            len(nodes),
            len(edges),
            len(headers),
            bounds,
        )
        return LayoutGraph(nodes=nodes, edges=tuple(edges), branch_headers=headers, bounds=bounds)

    # ── column packing ─────────────────────────────────────────────────────

    def _infer_main_branch(
        self,
        display_graph: DisplayGraph,
        hint: tuple[str, ...] | None,
    ) -> str:
        if hint:
            logger.debug("infer main branch from hint branch=%s", hint[0])
            return hint[0]
        if display_graph.nodes:
            branch = min(display_graph.nodes.values(), key=lambda n: n.topo_rank).branch
            logger.debug("infer main branch from oldest node branch=%s", branch)
            return branch
        logger.debug("infer main branch from empty graph")
        return ""

    def _row_ranges(
        self,
        display_graph: DisplayGraph,
        row_by_node: dict[str, int],
    ) -> dict[str, tuple[int, int]]:
        """Return {branch: (first_row, last_row)} from actual node positions."""
        bucket: dict[str, list[int]] = {}
        for node_id, node in display_graph.nodes.items():
            bucket.setdefault(node.branch, []).append(row_by_node[node_id])
        return {b: (min(rows), max(rows)) for b, rows in bucket.items()}

    def _parent_branch_map(self, display_graph: DisplayGraph) -> dict[str, str]:
        """Infer {child_branch: parent_branch} from branch-kind edges.

        Branch edges go src=parent_branch_commit → dst=child_branch_first_commit
        (both HistoryLoader and BranchRebuilder use older→newer direction).
        """
        parent_map: dict[str, str] = {}
        for edge in display_graph.edges:
            if edge.kind != "branch":
                continue
            if edge.src not in display_graph.nodes or edge.dst not in display_graph.nodes:
                continue
            parent_b = display_graph.nodes[edge.src].branch  # src = parent branch
            child_b = display_graph.nodes[edge.dst].branch   # dst = child branch
            if child_b != parent_b:
                parent_map.setdefault(child_b, parent_b)
        logger.debug("parent branch map inferred count=%d", len(parent_map))
        return parent_map

    def _merge_branch_edges(
        self,
        display_graph: DisplayGraph,
        row_by_node: dict[str, int],
    ) -> list[tuple[str, str, int, int]]:
        result: list[tuple[str, str, int, int]] = []
        for edge in display_graph.edges:
            if edge.kind != "merge":
                continue
            if edge.src not in display_graph.nodes or edge.dst not in display_graph.nodes:
                logger.debug("skip merge branch edge missing endpoint src=%s dst=%s", edge.src, edge.dst)
                continue
            if edge.src not in row_by_node or edge.dst not in row_by_node:
                logger.debug("skip merge branch edge missing row src=%s dst=%s", edge.src, edge.dst)
                continue
            src = display_graph.nodes[edge.src]
            dst = display_graph.nodes[edge.dst]
            result.append((src.branch, dst.branch, row_by_node[edge.src], row_by_node[edge.dst]))
        logger.debug("merge branch edges extracted count=%d", len(result))
        return result

    def _crossing_count(
        self,
        merge_edges: list[tuple[str, str, int, int]],
        col: dict[str, int],
    ) -> int:
        count = 0
        for i, edge_a in enumerate(merge_edges):
            src_a, dst_a, src_row_a, dst_row_a = edge_a
            if src_a not in col or dst_a not in col or col[src_a] == col[dst_a]:
                continue
            endpoints_a = {src_a, dst_a}
            for edge_b in merge_edges[i + 1:]:
                src_b, dst_b, src_row_b, dst_row_b = edge_b
                if src_b not in col or dst_b not in col or col[src_b] == col[dst_b]:
                    continue
                if endpoints_a & {src_b, dst_b}:
                    continue
                if not self._strict_row_spans_overlap(src_row_a, dst_row_a, src_row_b, dst_row_b):
                    continue
                if self._cols_strictly_interleave(col[src_a], col[dst_a], col[src_b], col[dst_b]):
                    count += 1
        logger.debug("merge crossing count=%d edge_count=%d", count, len(merge_edges))
        return count

    def _pack_columns(
        self,
        branches: list[str],
        row_ranges: dict[str, tuple[int, int]],
        parent_map: dict[str, str],
        main_branch: str,
        merge_edges: list[tuple[str, str, int, int]] | None = None,
    ) -> dict[str, int]:
        """Assign columns via interval packing.

        Two branches may share a column only when their row ranges don't
        overlap (plus a GAP buffer).  A child branch is always placed in a
        higher-numbered column than its parent.
        """
        GAP = 1
        col: dict[str, int] = {}
        col_slots: dict[int, list[tuple[int, int]]] = {}

        def overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
            return a[0] <= b[1] + GAP and b[0] <= a[1] + GAP

        def column_available(branch: str, column: int) -> bool:
            rng = row_ranges.get(branch, (0, 0))
            return not any(overlaps(rng, slot) for slot in col_slots.get(column, []))

        def legal_candidates(branch: str, min_c: int) -> list[int]:
            candidates: list[int] = []
            c = min_c
            while len(candidates) < _CANDIDATE_POOL:
                if column_available(branch, c):
                    candidates.append(c)
                c += 1
            return candidates

        def assign(branch: str, min_c: int) -> None:
            rng = row_ranges.get(branch, (0, 0))
            candidates = legal_candidates(branch, min_c)
            if merge_edges:
                best = min(
                    candidates,
                    key=lambda c: self._candidate_column_score(branch, c, candidates[0], min_c, col, merge_edges),
                )
            else:
                best = candidates[0]
            col[branch] = best
            col_slots.setdefault(best, []).append(rng)

        branch_set = set(branches)

        # Main branch always gets column 0
        if main_branch in branch_set:
            assign(main_branch, 0)

        # Build parent → children map
        children: dict[str, list[str]] = {}
        no_parent: list[str] = []
        for branch in branches:
            if branch == main_branch:
                continue
            parent = parent_map.get(branch)
            if parent and parent in branch_set:
                children.setdefault(parent, []).append(branch)
            else:
                no_parent.append(branch)

        # BFS: parent before child; within same parent, earliest fork first
        queue: deque[str] = deque(sorted(
            children.get(main_branch, []) + no_parent,
            key=lambda b: row_ranges.get(b, (0, 0))[0],
        ))
        visited: set[str] = {main_branch}

        while queue:
            branch = queue.popleft()
            if branch in visited:
                continue
            visited.add(branch)
            parent = parent_map.get(branch)
            parent_col = col.get(parent, col.get(main_branch, 0))
            assign(branch, parent_col + 1)
            queue.extend(sorted(
                children.get(branch, []),
                key=lambda b: row_ranges.get(b, (0, 0))[0],
            ))

        # Fallback for any branch not reached (shouldn't happen in practice)
        for branch in branches:
            if branch not in col:
                assign(branch, 1)

        if not self._columns_satisfy_parent_constraints(col, parent_map):
            logger.warning("packed columns violate parent constraints col=%s parent_map=%s", col, parent_map)
        if not self._columns_satisfy_interval_packing(col, row_ranges):
            logger.warning("packed columns violate interval packing col=%s row_ranges=%s", col, row_ranges)
        logger.debug("pack_columns result=%s", col)
        return col

    def _candidate_column_score(
        self,
        branch: str,
        candidate_col: int,
        baseline_col: int,
        min_col: int,
        placed_cols: dict[str, int],
        merge_edges: list[tuple[str, str, int, int]],
    ) -> float:
        baseline = dict(placed_cols)
        baseline[branch] = baseline_col
        candidate = dict(placed_cols)
        candidate[branch] = candidate_col
        crossing_delta = self._crossing_count(merge_edges, candidate) - self._crossing_count(merge_edges, baseline)
        span_cost = self._merge_span_cost(branch, candidate_col, placed_cols, merge_edges)
        current_max_col = max(placed_cols.values(), default=0)
        new_column_penalty = _NEW_COLUMN_PENALTY if candidate_col > current_max_col else 0.0
        extra_depth = max(0, candidate_col - min_col - 1)
        extra_depth_penalty = extra_depth * _EXTRA_DEPTH_PENALTY
        score = (
            crossing_delta * _CROSSING_WEIGHT
            + span_cost
            + candidate_col * _COLUMN_PENALTY
            + new_column_penalty
            + extra_depth_penalty
        )
        logger.debug(
            (
                "candidate column score branch=%s candidate=%d baseline=%d min_col=%d crossing_delta=%d "
                "span_cost=%s new_column_penalty=%s extra_depth_penalty=%s score=%s"
            ),
            branch,
            candidate_col,
            baseline_col,
            min_col,
            crossing_delta,
            span_cost,
            new_column_penalty,
            extra_depth_penalty,
            score,
        )
        return score

    def _merge_span_cost(
        self,
        branch: str,
        candidate_col: int,
        placed_cols: dict[str, int],
        merge_edges: list[tuple[str, str, int, int]],
    ) -> float:
        cost = 0.0
        for src_branch, dst_branch, src_row, dst_row in merge_edges:
            partner = ""
            if src_branch == branch:
                partner = dst_branch
            elif dst_branch == branch:
                partner = src_branch
            if not partner or partner not in placed_cols:
                continue
            row_weight = max(1, abs(dst_row - src_row))
            cost += abs(candidate_col - placed_cols[partner]) * row_weight
        return cost

    def _swap_optimize_columns(
        self,
        col: dict[str, int],
        row_ranges: dict[str, tuple[int, int]],
        parent_map: dict[str, str],
        merge_edges: list[tuple[str, str, int, int]],
        max_passes: int = 3,
    ) -> dict[str, int]:
        """Reduce merge crossings with bounded branch-column swaps."""
        logger.debug(
            "swap optimize columns start branches=%d merge_edges=%d max_passes=%d",
            len(col),
            len(merge_edges),
            max_passes,
        )
        if max_passes <= 0 or not merge_edges:
            logger.debug("swap optimize columns skipped")
            return dict(col)

        optimized = dict(col)
        branches = list(optimized)
        for pass_index in range(max_passes):
            changed = False
            before_pass = self._crossing_count(merge_edges, optimized)
            logger.debug(
                "swap optimize pass start pass=%d crossings=%d",
                pass_index + 1,
                before_pass,
            )
            for left_index, left in enumerate(branches):
                for right in branches[left_index + 1:]:
                    if optimized[left] == optimized[right]:
                        continue
                    swapped = dict(optimized)
                    swapped[left], swapped[right] = swapped[right], swapped[left]
                    if not self._columns_satisfy_parent_constraints(swapped, parent_map):
                        logger.debug("reject swap parent constraint left=%s right=%s", left, right)
                        continue
                    if not self._columns_satisfy_interval_packing(swapped, row_ranges):
                        logger.debug("reject swap interval packing left=%s right=%s", left, right)
                        continue

                    before = self._crossing_count(merge_edges, optimized)
                    after = self._crossing_count(merge_edges, swapped)
                    if after < before:
                        logger.debug(
                            "accept swap left=%s right=%s before=%d after=%d",
                            left,
                            right,
                            before,
                            after,
                        )
                        optimized = swapped
                        changed = True

            after_pass = self._crossing_count(merge_edges, optimized)
            logger.debug(
                "swap optimize pass complete pass=%d before=%d after=%d changed=%s",
                pass_index + 1,
                before_pass,
                after_pass,
                changed,
            )
            if not changed:
                break

        logger.debug("swap optimize columns complete result=%s", optimized)
        return optimized

    def _columns_satisfy_parent_constraints(
        self,
        col: dict[str, int],
        parent_map: dict[str, str],
    ) -> bool:
        for child, parent in parent_map.items():
            if child not in col or parent not in col:
                continue
            if col[child] <= col[parent]:
                logger.debug(
                    "parent constraint violation child=%s parent=%s child_col=%d parent_col=%d",
                    child,
                    parent,
                    col[child],
                    col[parent],
                )
                return False
        return True

    def _columns_satisfy_interval_packing(
        self,
        col: dict[str, int],
        row_ranges: dict[str, tuple[int, int]],
    ) -> bool:
        by_col: dict[int, list[tuple[str, tuple[int, int]]]] = {}
        for branch, column in col.items():
            if branch not in row_ranges:
                continue
            rng = row_ranges[branch]
            for other_branch, other_rng in by_col.get(column, []):
                if self._row_ranges_overlap_with_gap(rng, other_rng):
                    logger.debug(
                        "interval packing violation branch=%s other=%s column=%d branch_range=%s other_range=%s",
                        branch,
                        other_branch,
                        column,
                        rng,
                        other_rng,
                    )
                    return False
            by_col.setdefault(column, []).append((branch, rng))
        return True

    @staticmethod
    def _row_ranges_overlap_with_gap(
        a: tuple[int, int],
        b: tuple[int, int],
        gap: int = 1,
    ) -> bool:
        return a[0] <= b[1] + gap and b[0] <= a[1] + gap

    @staticmethod
    def _strict_row_spans_overlap(a0: int, a1: int, b0: int, b1: int) -> bool:
        lo_a, hi_a = sorted((a0, a1))
        lo_b, hi_b = sorted((b0, b1))
        return max(lo_a, lo_b) < min(hi_a, hi_b)

    @staticmethod
    def _cols_strictly_interleave(a0: int, a1: int, b0: int, b1: int) -> bool:
        lo_a, hi_a = sorted((a0, a1))
        lo_b, hi_b = sorted((b0, b1))
        return (lo_a < lo_b < hi_a < hi_b) or (lo_b < lo_a < hi_b < hi_a)

    # ── row / bounds helpers ───────────────────────────────────────────────

    def _row_by_node(self, display_graph: DisplayGraph) -> dict[str, int]:
        ordered = sorted(
            display_graph.nodes.values(),
            key=lambda node: (node.topo_rank, node.branch, node.id),
        )
        rows = {node.id: index for index, node in enumerate(ordered)}
        logger.debug("layout rows assigned count=%d", len(rows))
        return rows

    def _bounds(
        self,
        nodes: Mapping[str, LayoutNode],
        headers: Mapping[str, BranchHeader],
    ) -> Rect:
        logger.debug("computing layout bounds nodes=%d headers=%d", len(nodes), len(headers))
        xs = [node.center.x for node in nodes.values()]
        ys = [node.center.y for node in nodes.values()]
        xs.extend(header.rect.x for header in headers.values())
        ys.extend(header.rect.y for header in headers.values())
        if not xs or not ys:
            logger.debug("layout bounds empty")
            return Rect(0, 0, 0, 0)
        min_x = min(xs) - self.settings.node_radius
        min_y = min(ys) - self.settings.node_radius
        max_x = max(xs) + self.settings.branch_col_width
        max_y = max(ys) + self.settings.row_height
        bounds = Rect(min_x, min_y, max_x - min_x, max_y - min_y)
        logger.debug("computed layout bounds=%s", bounds)
        return bounds
