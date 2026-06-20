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
        branch_col = self._pack_columns(all_branches, row_ranges, parent_map, main_branch)

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
            return hint[0]
        if display_graph.nodes:
            return min(display_graph.nodes.values(), key=lambda n: n.topo_rank).branch
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
        """Infer {child_branch: parent_branch} from branch-kind edges."""
        parent_map: dict[str, str] = {}
        for edge in display_graph.edges:
            if edge.kind != "branch":
                continue
            if edge.src not in display_graph.nodes or edge.dst not in display_graph.nodes:
                continue
            child_b = display_graph.nodes[edge.src].branch
            parent_b = display_graph.nodes[edge.dst].branch
            if child_b != parent_b:
                parent_map.setdefault(child_b, parent_b)
        return parent_map

    def _pack_columns(
        self,
        branches: list[str],
        row_ranges: dict[str, tuple[int, int]],
        parent_map: dict[str, str],
        main_branch: str,
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

        def assign(branch: str, min_c: int) -> None:
            rng = row_ranges.get(branch, (0, 0))
            c = min_c
            while True:
                if not any(overlaps(rng, slot) for slot in col_slots.get(c, [])):
                    col[branch] = c
                    col_slots.setdefault(c, []).append(rng)
                    return
                c += 1

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

        logger.debug("pack_columns result=%s", col)
        return col

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
