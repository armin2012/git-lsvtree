from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from .graph_model import BranchInfo, Edge, GraphModel


logger = logging.getLogger(__name__)

ViewMode = Literal["full", "key"]


@dataclass(frozen=True)
class KeySelection:
    graph: GraphModel
    partial: bool = False
    warning: str = ""


class KeySelector:
    def select(self, graph: GraphModel, mode: ViewMode = "key", threshold: int = 300) -> KeySelection:
        logger.info(
            "selecting graph mode=%s threshold=%d node_count=%d",
            mode,
            threshold,
            len(graph.nodes),
        )
        if mode == "full" or len(graph.nodes) <= threshold:
            logger.debug("key selector returning full graph mode=%s", mode)
            return KeySelection(graph)
        if threshold <= 0:
            raise ValueError("threshold must be positive")

        keep = self._skeleton(graph)
        partial = False
        warning = ""

        if len(keep) > threshold:
            partial = True
            warning = f"structure skeleton truncated: {len(keep)} > {threshold}"
            keep = set(self._priority_order(graph, keep)[:threshold])
            logger.warning(warning)
        else:
            budget = threshold - len(keep)
            keep.update(self._tag_nodes(graph, keep, budget))
            budget = threshold - len(keep)
            if budget > 0:
                keep.update(self._sample_nodes(graph, keep, budget))

        selected = self._build_selected_graph(graph, keep)
        logger.info(
            "selected key graph raw_nodes=%d selected_nodes=%d edges=%d partial=%s",
            len(graph.nodes),
            len(selected.nodes),
            len(selected.edges),
            partial,
        )
        return KeySelection(selected, partial=partial, warning=warning)

    def _skeleton(self, graph: GraphModel) -> set[str]:
        keep: set[str] = set()
        outdeg: dict[str, int] = {commit: 0 for commit in graph.nodes}
        indeg: dict[str, int] = {commit: 0 for commit in graph.nodes}

        for edge in graph.edges:
            outdeg[edge.src] = outdeg.get(edge.src, 0) + 1
            indeg[edge.dst] = indeg.get(edge.dst, 0) + 1
            if edge.kind == "merge":
                keep.add(edge.src)
                keep.add(edge.dst)

        for info in graph.branches.values():
            if info.nodes:
                keep.add(info.nodes[0])
                keep.add(info.nodes[-1])

        for commit, node in graph.nodes.items():
            if outdeg.get(commit, 0) > 1 or indeg.get(commit, 0) > 1:
                keep.add(commit)
            if node.is_head_file_version:
                keep.add(commit)

        logger.debug("built key skeleton size=%d", len(keep))
        return keep

    def _tag_nodes(self, graph: GraphModel, keep: set[str], budget: int) -> list[str]:
        if budget <= 0:
            return []
        tagged = [commit for commit in graph.order_oldest_first if commit not in keep and graph.nodes[commit].tags]
        selected = tagged[:budget]
        logger.debug("selected tag nodes count=%d budget=%d", len(selected), budget)
        return selected

    def _sample_nodes(self, graph: GraphModel, keep: set[str], budget: int) -> list[str]:
        plain = [commit for commit in graph.order_oldest_first if commit not in keep]
        if not plain or budget <= 0:
            return []
        step = max(1, len(plain) // budget)
        selected = plain[::step][:budget]
        logger.debug("selected sampled nodes count=%d budget=%d", len(selected), budget)
        return selected

    def _priority_order(self, graph: GraphModel, commits: set[str]) -> list[str]:
        def priority(commit: str) -> tuple[int, int]:
            node = graph.nodes[commit]
            if node.is_head_file_version:
                return (0, node.topo_rank)
            if node.tags:
                return (1, node.topo_rank)
            if node.is_merge:
                return (2, node.topo_rank)
            return (3, node.topo_rank)

        return sorted(commits, key=priority)

    def _build_selected_graph(self, graph: GraphModel, keep: set[str]) -> GraphModel:
        logger.debug("building selected graph keep_count=%d", len(keep))
        nodes = {commit: graph.nodes[commit] for commit in graph.order_newest_first if commit in keep}
        edges: list[Edge] = []
        seen: set[tuple[str, str, str, str]] = set()

        def add_edge(edge: Edge) -> None:
            key = (edge.src, edge.dst, edge.kind, edge.label)
            if edge.src == edge.dst or key in seen:
                return
            seen.add(key)
            edges.append(edge)

        for commit in graph.order_oldest_first:
            if commit not in keep:
                continue
            ancestor = self._nearest_visible_main_ancestor(graph, commit, keep)
            if ancestor:
                kind = "branch" if graph.nodes[ancestor].reconstructed_branch != graph.nodes[commit].reconstructed_branch else "main"
                add_edge(Edge(ancestor, commit, kind))

        for edge in graph.edges:
            if edge.kind != "merge" or edge.dst not in keep:
                continue
            src = edge.src if edge.src in keep else self._nearest_visible_main_ancestor(graph, edge.src, keep)
            if src:
                add_edge(Edge(src, edge.dst, "merge", edge.label))

        branches = {}
        for branch, info in graph.branches.items():
            visible = tuple(commit for commit in info.nodes if commit in keep)
            if visible:
                branches[branch] = BranchInfo(branch, visible, info.column_hint, info.reconstructed)

        selected = GraphModel(
            nodes=nodes,
            edges=tuple(edges),
            order_newest_first=tuple(commit for commit in graph.order_newest_first if commit in keep),
            order_oldest_first=tuple(commit for commit in graph.order_oldest_first if commit in keep),
            branches=branches,
        )
        logger.debug(
            "built selected graph nodes=%d edges=%d branches=%d",
            len(selected.nodes),
            len(selected.edges),
            len(selected.branches),
        )
        return selected

    def _nearest_visible_main_ancestor(self, graph: GraphModel, commit: str, keep: set[str]) -> str:
        logger.debug("finding nearest visible ancestor commit=%s keep_count=%d", commit[:12], len(keep))
        current = graph.nodes[commit].main_parent if commit in graph.nodes else None
        while current:
            if current in keep:
                logger.debug("found nearest visible ancestor commit=%s ancestor=%s", commit[:12], current[:12])
                return current
            current = graph.nodes[current].main_parent if current in graph.nodes else None
        logger.debug("no nearest visible ancestor commit=%s", commit[:12])
        return ""
