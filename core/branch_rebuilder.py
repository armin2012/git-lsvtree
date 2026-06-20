from __future__ import annotations

import logging
from collections import defaultdict

from .graph_model import BranchInfo, Edge, GraphModel, VersionNode


logger = logging.getLogger(__name__)


class BranchRebuilder:
    def rebuild(self, graph: GraphModel, main_branch: str = "main") -> GraphModel:
        if not graph.nodes:
            logger.info("skip branch rebuild for empty graph")
            return graph

        logger.info("rebuilding branches node_count=%d main_branch=%s", len(graph.nodes), main_branch)
        branch_of: dict[str, str] = {}

        def assign_chain(start: str, branch: str) -> None:
            current = start
            while current and current in graph.nodes and current not in branch_of:
                branch_of[current] = branch
                current = graph.nodes[current].main_parent or ""

        main_tip = self._main_tip(graph)
        assign_chain(main_tip, main_branch)
        changed = True
        while changed:
            changed = False
            for commit in graph.order_newest_first:
                if commit not in branch_of:
                    continue
                for merge_parent in graph.nodes[commit].merge_parents:
                    if merge_parent.hash in graph.nodes and merge_parent.hash not in branch_of:
                        branch = merge_parent.label or f"branch@{merge_parent.hash[:7]}"
                        assign_chain(merge_parent.hash, branch)
                        changed = True

        for commit in graph.order_newest_first:
            if commit not in branch_of:
                assign_chain(commit, f"branch@{commit[:7]}")

        by_branch: dict[str, list[str]] = defaultdict(list)
        for commit in graph.order_oldest_first:
            by_branch[branch_of[commit]].append(commit)

        nodes: dict[str, VersionNode] = {}
        for branch, commits in by_branch.items():
            for index, commit in enumerate(commits):
                nodes[commit] = graph.nodes[commit].with_branch(branch, index)

        branch_order: list[str] = []
        if main_branch in by_branch:
            branch_order.append(main_branch)
        for commit in graph.order_newest_first:
            branch = branch_of[commit]
            if branch not in branch_order:
                branch_order.append(branch)

        branches = {
            branch: BranchInfo(
                name=branch,
                nodes=tuple(by_branch[branch]),
                column_hint=index,
                reconstructed=True,
            )
            for index, branch in enumerate(branch_order)
        }

        edges: list[Edge] = []
        for edge in graph.edges:
            if edge.kind == "merge":
                edges.append(edge)
                continue
            kind = "branch" if nodes[edge.src].reconstructed_branch != nodes[edge.dst].reconstructed_branch else "main"
            edges.append(Edge(edge.src, edge.dst, kind, edge.label))

        logger.info("rebuilt branches branch_count=%d edge_count=%d", len(branches), len(edges))
        return GraphModel(
            nodes=nodes,
            edges=tuple(edges),
            order_newest_first=graph.order_newest_first,
            order_oldest_first=graph.order_oldest_first,
            branches=branches,
        )

    def _main_tip(self, graph: GraphModel) -> str:
        for commit in graph.order_newest_first:
            if graph.nodes[commit].is_head_file_version:
                logger.debug("using HEAD file version as main tip commit=%s", commit[:12])
                return commit
        fallback = graph.order_newest_first[0]
        logger.debug("using topo newest commit as main tip fallback commit=%s", fallback[:12])
        return fallback
