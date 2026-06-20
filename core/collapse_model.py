from __future__ import annotations

import logging
from collections import defaultdict

from .graph_model import DisplayEdge, DisplayGraph, DisplayNode, GraphModel


logger = logging.getLogger(__name__)


class CollapseModel:
    def __init__(self, enabled: bool = True):
        logger.debug("init collapse model enabled=%s", enabled)
        self.enabled = enabled

    def build(self, graph: GraphModel, expanded_runs: frozenset[str] | None = None) -> DisplayGraph:
        expanded_runs = expanded_runs or set()
        if not self.enabled:
            logger.info("building display graph without collapse")
            return self._without_collapse(graph)

        indeg: dict[str, int] = defaultdict(int)
        outdeg: dict[str, int] = defaultdict(int)
        for edge in graph.edges:
            if edge.kind not in ("main", "branch"):
                continue
            outdeg[edge.src] += 1
            indeg[edge.dst] += 1

        collapsible = {
            commit
            for commit, node in graph.nodes.items()
            if indeg[commit] == 1
            and outdeg[commit] == 1
            and not node.tags
            and node.reconstructed_branch
        }

        mapped: dict[str, str] = {}
        run_sources: dict[str, tuple[str, ...]] = {}

        for branch, info in graph.branches.items():
            current: list[str] = []
            for commit in info.nodes:
                if commit in collapsible:
                    current.append(commit)
                    continue
                self._flush_run(branch, current, graph, mapped, run_sources)
                current = []
            self._flush_run(branch, current, graph, mapped, run_sources)

        display_nodes: dict[str, DisplayNode] = {}
        for commit, node in graph.nodes.items():
            run_id = mapped.get(commit)
            if run_id and run_id not in expanded_runs:
                if run_id not in display_nodes:
                    source_hashes = run_sources[run_id]
                    first = graph.nodes[source_hashes[0]]
                    last = graph.nodes[source_hashes[-1]]
                    display_nodes[run_id] = DisplayNode(
                        id=run_id,
                        kind="run",
                        branch=first.reconstructed_branch,
                        per_branch_index=first.per_branch_index,
                        topo_rank=last.topo_rank,
                        label=f"#{first.per_branch_index}…#{last.per_branch_index}",
                        source_hashes=source_hashes,
                    )
                continue
            display_nodes[commit] = DisplayNode(
                id=commit,
                kind="version",
                branch=node.reconstructed_branch,
                per_branch_index=node.per_branch_index,
                topo_rank=node.topo_rank,
                label=str(node.per_branch_index),
                source_hashes=(commit,),
            )

        display_edges: list[DisplayEdge] = []
        seen: set[tuple[str, str, str, str]] = set()
        for edge in graph.edges:
            src = self._display_id(edge.src, mapped, expanded_runs)
            dst = self._display_id(edge.dst, mapped, expanded_runs)
            if src == dst or src not in display_nodes or dst not in display_nodes:
                continue
            key = (src, dst, edge.kind, edge.label)
            if key in seen:
                continue
            seen.add(key)
            display_edges.append(DisplayEdge(src, dst, edge.kind, edge.label))

        logger.info(
            "built collapsed display graph raw_nodes=%d display_nodes=%d runs=%d display_edges=%d",
            len(graph.nodes),
            len(display_nodes),
            len(run_sources),
            len(display_edges),
        )
        return DisplayGraph(display_nodes, tuple(display_edges))

    def _flush_run(
        self,
        branch: str,
        current: list[str],
        graph: GraphModel,
        mapped: dict[str, str],
        run_sources: dict[str, tuple[str, ...]],
    ) -> None:
        if len(current) < 2:
            logger.debug("skip collapse run branch=%s length=%d", branch, len(current))
            return
        run_id = f"RUN_{branch}_{current[0][:8]}_{current[-1][:8]}"
        sources = tuple(current)
        run_sources[run_id] = sources
        for commit in current:
            mapped[commit] = run_id
        logger.debug("flushed collapse run run_id=%s branch=%s length=%d", run_id, branch, len(sources))

    def _display_id(self, commit: str, mapped: dict[str, str], expanded_runs: set[str]) -> str:
        run_id = mapped.get(commit)
        if run_id and run_id not in expanded_runs:
            return run_id
        return commit

    def _without_collapse(self, graph: GraphModel) -> DisplayGraph:
        logger.debug("building display graph without collapse nodes=%d edges=%d", len(graph.nodes), len(graph.edges))
        nodes = {
            commit: DisplayNode(
                id=commit,
                kind="version",
                branch=node.reconstructed_branch,
                per_branch_index=node.per_branch_index,
                topo_rank=node.topo_rank,
                label=str(node.per_branch_index),
                source_hashes=(commit,),
            )
            for commit, node in graph.nodes.items()
        }
        edges = tuple(DisplayEdge(edge.src, edge.dst, edge.kind, edge.label) for edge in graph.edges)
        logger.debug("built non-collapsed display graph nodes=%d edges=%d", len(nodes), len(edges))
        return DisplayGraph(nodes, edges)
