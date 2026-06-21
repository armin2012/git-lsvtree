from __future__ import annotations

from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Literal, Mapping


EdgeKind = Literal["main", "branch", "merge"]
DisplayNodeKind = Literal["version", "run"]


@dataclass(frozen=True)
class MergeParent:
    hash: str
    label: str = ""


@dataclass(frozen=True)
class VersionNode:
    hash: str
    parents: tuple[str, ...]
    main_parent: str | None
    merge_parents: tuple[MergeParent, ...]
    tags: tuple[str, ...]
    author_name: str
    author_email: str
    author_time: int
    commit_time: int
    subject: str
    topo_rank: int
    reconstructed_branch: str = ""
    per_branch_index: int = -1
    is_head_file_version: bool = False
    committer_name: str = ""
    committer_email: str = ""
    description: str = ""

    @property
    def is_merge(self) -> bool:
        return bool(self.merge_parents)

    def with_branch(self, branch: str, per_branch_index: int) -> "VersionNode":
        return replace(
            self,
            reconstructed_branch=branch,
            per_branch_index=per_branch_index,
        )


@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    kind: EdgeKind
    label: str = ""


@dataclass(frozen=True)
class BranchInfo:
    name: str
    nodes: tuple[str, ...]
    column_hint: int = 0
    reconstructed: bool = True


@dataclass(frozen=True)
class GraphModel:
    nodes: Mapping[str, VersionNode]
    edges: tuple[Edge, ...]
    order_newest_first: tuple[str, ...]
    order_oldest_first: tuple[str, ...]
    branches: Mapping[str, BranchInfo]

    def __post_init__(self) -> None:
        object.__setattr__(self, "nodes", MappingProxyType(dict(self.nodes)))
        object.__setattr__(self, "branches", MappingProxyType(dict(self.branches)))


@dataclass(frozen=True)
class DisplayNode:
    id: str
    kind: DisplayNodeKind
    branch: str
    per_branch_index: int
    topo_rank: int
    label: str
    source_hashes: tuple[str, ...]
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class DisplayEdge:
    src: str
    dst: str
    kind: EdgeKind
    label: str = ""


@dataclass(frozen=True)
class DisplayGraph:
    nodes: Mapping[str, DisplayNode]
    edges: tuple[DisplayEdge, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "nodes", MappingProxyType(dict(self.nodes)))
