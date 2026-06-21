from __future__ import annotations

import logging
import posixpath
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal


logger = logging.getLogger(__name__)

ProjectTreeNodeKind = Literal["directory", "file"]


@dataclass(frozen=True)
class ProjectTreeNode:
    name: str
    rel_path: str
    kind: ProjectTreeNodeKind
    children: tuple["ProjectTreeNode", ...] = ()
    tracked: bool = False


@dataclass(frozen=True)
class ProjectTree:
    repo_root: Path
    root: ProjectTreeNode
    tracked_file_count: int


class ProjectTreeBuilder:
    def build(self, repo_root: Path, tracked_paths: Iterable[str]) -> ProjectTree:
        logger.info("building project tree repo_root=%s", repo_root)
        normalized = sorted(
            {
                path
                for raw_path in tracked_paths
                if (path := self._normalize_tracked_path(raw_path))
            },
            key=str.casefold,
        )
        if not normalized:
            logger.warning("project tree build failed no tracked files repo_root=%s", repo_root)
            raise ValueError("no tracked files in project")

        root_name = repo_root.name or str(repo_root)
        mutable_root: dict = {"dirs": {}, "files": set()}
        for rel_path in normalized:
            logger.debug("adding project tree path=%s", rel_path)
            self._insert_path(mutable_root, rel_path)

        root = ProjectTreeNode(
            name=root_name,
            rel_path="",
            kind="directory",
            children=self._freeze_children(mutable_root, ""),
            tracked=False,
        )
        tree = ProjectTree(
            repo_root=repo_root,
            root=root,
            tracked_file_count=len(normalized),
        )
        logger.info(
            "project tree built repo_root=%s tracked_file_count=%d",
            repo_root,
            tree.tracked_file_count,
        )
        return tree

    @staticmethod
    def _normalize_tracked_path(raw_path: str) -> str:
        path = raw_path.strip().replace("\\", "/")
        if not path or path == ".":
            return ""
        normalized = posixpath.normpath(path)
        if normalized in ("", ".") or normalized.startswith("../") or normalized == "..":
            return ""
        return normalized.lstrip("/")

    @classmethod
    def _insert_path(cls, root: dict, rel_path: str) -> None:
        parts = [part for part in rel_path.split("/") if part]
        if not parts:
            return
        current = root
        for part in parts[:-1]:
            current = current["dirs"].setdefault(part, {"dirs": {}, "files": set()})
        current["files"].add(parts[-1])

    @classmethod
    def _freeze_children(cls, node: dict, parent_rel_path: str) -> tuple[ProjectTreeNode, ...]:
        children: list[ProjectTreeNode] = []
        for name, child in sorted(node["dirs"].items(), key=lambda item: item[0].casefold()):
            rel_path = cls._join_rel_path(parent_rel_path, name)
            children.append(
                ProjectTreeNode(
                    name=name,
                    rel_path=rel_path,
                    kind="directory",
                    children=cls._freeze_children(child, rel_path),
                    tracked=False,
                )
            )
        for name in sorted(node["files"], key=str.casefold):
            rel_path = cls._join_rel_path(parent_rel_path, name)
            children.append(
                ProjectTreeNode(
                    name=name,
                    rel_path=rel_path,
                    kind="file",
                    children=(),
                    tracked=True,
                )
            )
        return tuple(children)

    @staticmethod
    def _join_rel_path(parent: str, name: str) -> str:
        return f"{parent}/{name}" if parent else name
