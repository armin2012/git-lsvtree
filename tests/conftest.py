"""Shared test factories — no Qt dependency."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from git_lsvtree_ui.core.graph_model import (
    BranchInfo,
    DisplayEdge,
    DisplayGraph,
    DisplayNode,
    Edge,
    GraphModel,
    MergeParent,
    VersionNode,
)


# ── commit ID helpers ──────────────────────────────────────────────────────


def h(n: int) -> str:
    """Return a 40-char hex commit ID from integer n."""
    return f"{n:040x}"


# ── VersionNode factory ────────────────────────────────────────────────────


def vnode(
    commit_id: str,
    *,
    parents: tuple[str, ...] = (),
    tags: tuple[str, ...] = (),
    topo_rank: int = 0,
    branch: str = "",
    per_branch_index: int = 0,
    is_head: bool = False,
    subject: str = "",
    merge_labels: tuple[str, ...] = (),
) -> VersionNode:
    main_parent = parents[0] if parents else None
    merge_parents = tuple(
        MergeParent(hash=p, label=lbl)
        for p, lbl in zip(parents[1:], merge_labels or [""] * len(parents))
    )
    return VersionNode(
        hash=commit_id,
        parents=parents,
        main_parent=main_parent,
        merge_parents=merge_parents,
        tags=tags,
        author_name="Test Author",
        author_email="test@example.com",
        author_time=topo_rank,
        commit_time=topo_rank,
        subject=subject or f"commit {commit_id[:8]}",
        topo_rank=topo_rank,
        reconstructed_branch=branch,
        per_branch_index=per_branch_index,
        is_head_file_version=is_head,
    )


# ── GraphModel factories ───────────────────────────────────────────────────


def linear_graph(n: int, branch: str = "main") -> GraphModel:
    """Post-BranchRebuilder linear graph: h(0) oldest → h(n-1) newest."""
    commits = [h(i) for i in range(n)]
    nodes = {
        c: vnode(
            c,
            parents=(commits[i - 1],) if i else (),
            topo_rank=i,
            branch=branch,
            per_branch_index=i,
            is_head=(i == n - 1),
        )
        for i, c in enumerate(commits)
    }
    edges = tuple(Edge(commits[i - 1], commits[i], "main") for i in range(1, n))
    order_oldest = tuple(commits)
    return GraphModel(
        nodes=nodes,
        edges=edges,
        order_newest_first=tuple(reversed(commits)),
        order_oldest_first=order_oldest,
        branches={branch: BranchInfo(name=branch, nodes=order_oldest)},
    )


def two_branch_graph(
    main_n: int,
    fork_at: int,
    feat_n: int,
    *,
    main_name: str = "main",
    feat_name: str = "feature",
) -> GraphModel:
    """
    main: h(0)..h(main_n-1)
    feature: h(main_n)..h(main_n+feat_n-1), forked from h(fork_at) on main.
    Branch edge: src=h(fork_at) [main], dst=h(main_n) [feature first commit].
    """
    main_c = [h(i) for i in range(main_n)]
    feat_c = [h(main_n + i) for i in range(feat_n)]

    nodes: dict[str, VersionNode] = {}
    for i, c in enumerate(main_c):
        nodes[c] = vnode(
            c,
            parents=(main_c[i - 1],) if i else (),
            topo_rank=i,
            branch=main_name,
            per_branch_index=i,
            is_head=(i == main_n - 1),
        )
    for i, c in enumerate(feat_c):
        parent = feat_c[i - 1] if i else main_c[fork_at]
        nodes[c] = vnode(
            c, parents=(parent,), topo_rank=main_n + i, branch=feat_name, per_branch_index=i
        )

    edges: list[Edge] = []
    for i in range(1, main_n):
        edges.append(Edge(main_c[i - 1], main_c[i], "main"))
    # branch edge: src=parent_branch_commit, dst=child_branch_first_commit
    edges.append(Edge(main_c[fork_at], feat_c[0], "branch"))
    for i in range(1, feat_n):
        edges.append(Edge(feat_c[i - 1], feat_c[i], "main"))

    order_oldest = tuple(main_c) + tuple(feat_c)
    return GraphModel(
        nodes=nodes,
        edges=tuple(edges),
        order_newest_first=tuple(reversed(order_oldest)),
        order_oldest_first=order_oldest,
        branches={
            main_name: BranchInfo(main_name, tuple(main_c), column_hint=0),
            feat_name: BranchInfo(feat_name, tuple(feat_c), column_hint=1),
        },
    )


# ── DisplayGraph factory ───────────────────────────────────────────────────


def make_display_graph(
    node_specs: list[tuple[str, str, int, tuple[str, ...]]],
    edge_specs: list[tuple[str, str, str]],
) -> DisplayGraph:
    """
    node_specs: [(id, branch, topo_rank, tags), ...]
    edge_specs: [(src, dst, kind), ...]
    """
    nodes = {
        nid: DisplayNode(
            id=nid,
            kind="version",
            branch=branch,
            per_branch_index=rank,
            topo_rank=rank,
            label=str(rank),
            source_hashes=(nid,),
            tags=tags,
        )
        for nid, branch, rank, tags in node_specs
    }
    edges = tuple(DisplayEdge(src, dst, kind) for src, dst, kind in edge_specs)
    return DisplayGraph(nodes, edges)
