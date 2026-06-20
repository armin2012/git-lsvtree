from __future__ import annotations

import logging
import math
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
        branches = self._branch_order(display_graph, branch_order)
        branch_col = {branch: index for index, branch in enumerate(branches)}
        row_by_node = self._row_by_node(display_graph)

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

        headers = {
            branch: BranchHeader(
                branch=branch,
                rect=Rect(
                    self.settings.left_margin
                    + col * self.settings.branch_col_width
                    - self.settings.branch_header_width / 2,
                    self.settings.top_margin,
                    self.settings.branch_header_width,
                    self.settings.branch_header_height,
                ),
                label=f"{branch} (reconstructed)",
            )
            for branch, col in branch_col.items()
        }

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

    def _branch_order(
        self,
        display_graph: DisplayGraph,
        hint: tuple[str, ...] | None,
    ) -> tuple[str, ...]:
        # Start from hint (BranchRebuilder column order: main first), then append unseen branches.
        result: list[str] = list(hint or [])
        seen = set(result)
        for node in display_graph.nodes.values():
            if node.branch not in seen:
                seen.add(node.branch)
                result.append(node.branch)
        logger.debug("layout branch order=%s", result)
        return tuple(result)

    def _row_by_node(self, display_graph: DisplayGraph) -> dict[str, int]:
        ordered = sorted(
            display_graph.nodes.values(),
            key=lambda node: (node.topo_rank, node.branch, node.id),
        )
        rows = {node.id: index for index, node in enumerate(ordered)}
        logger.debug("layout rows assigned count=%d", len(rows))
        return rows

    def _bounds(self, nodes: Mapping[str, LayoutNode], headers: Mapping[str, BranchHeader]) -> Rect:
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
