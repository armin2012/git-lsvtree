from __future__ import annotations

import logging
import re

from .git_repo import GitRepo
from .graph_model import Edge, GraphModel, MergeParent, VersionNode


logger = logging.getLogger(__name__)

US = "\x01"
GS = "\x02"


def parse_merge_source(subject: str) -> str:
    patterns = (
        r"Merge branch '([^']+)'",
        r"Merge remote-tracking branch '([^']+)'",
        r"Merge pull request .* from (\S+)",
    )
    for pattern in patterns:
        match = re.search(pattern, subject)
        if match:
            return match.group(1)
    return ""


def parse_tags(decorations: str) -> tuple[str, ...]:
    tags: list[str] = []
    for item in decorations.split(","):
        item = item.strip()
        if item.startswith("tag: "):
            tags.append(item[5:])
    return tuple(tags)


class HistoryLoader:
    def __init__(self, repo: GitRepo, include_all: bool = False):
        logger.debug("init history loader rel_path=%s include_all=%s", repo.rel_path, include_all)
        self.repo = repo
        self.include_all = include_all

    def load(self) -> GraphModel:
        all_args = ("--all",) if self.include_all else ()
        fmt = "%x01%H %P%x02%D%x02%an%x02%ae%x02%at%x02%ct%x02%s"
        logger.info(
            "loading file history rel_path=%s include_all=%s",
            self.repo.rel_path,
            self.include_all,
        )
        raw = self.repo.git_checked(
            "log",
            *all_args,
            "--topo-order",
            "--full-history",
            "--simplify-merges",
            "--parents",
            f"--format={fmt}",
            "--",
            self.repo.rel_path,
        )
        records = [record for record in raw.split(US) if record.strip()]
        if not records:
            logger.warning("no git history for rel_path=%s", self.repo.rel_path)
            return GraphModel({}, tuple(), tuple(), tuple(), {})

        parsed: dict[str, VersionNode] = {}
        order_newest: list[str] = []
        raw_parents: dict[str, tuple[str, ...]] = {}
        subjects: dict[str, str] = {}

        for rank, record in enumerate(records):
            fields = (record.split(GS) + ["", "", "", "", "", ""])[:7]
            hash_and_parents, decorations, author_name, author_email, author_time, commit_time, subject = fields
            tokens = hash_and_parents.split()
            commit = tokens[0]
            parents = tuple(tokens[1:])
            raw_parents[commit] = parents
            subjects[commit] = subject.strip()
            order_newest.append(commit)
            parsed[commit] = VersionNode(
                hash=commit,
                parents=parents,
                main_parent=parents[0] if parents else None,
                merge_parents=tuple(),
                tags=parse_tags(decorations),
                author_name=author_name,
                author_email=author_email,
                author_time=int(author_time or 0),
                commit_time=int(commit_time or 0),
                subject=subject.strip(),
                topo_rank=-1,
            )

        node_set = set(order_newest)
        order_oldest = tuple(reversed(order_newest))
        topo_rank = {commit: index for index, commit in enumerate(order_oldest)}
        nodes: dict[str, VersionNode] = {}
        edges: list[Edge] = []

        head_file_version = self._head_file_version()

        for commit in order_newest:
            parents = tuple(parent for parent in raw_parents[commit] if parent in node_set)
            main_parent = parents[0] if parents else None
            merge_parents = tuple(
                MergeParent(parent, parse_merge_source(subjects[commit]))
                for parent in parents[1:]
            )
            original = parsed[commit]
            nodes[commit] = VersionNode(
                hash=commit,
                parents=parents,
                main_parent=main_parent,
                merge_parents=merge_parents,
                tags=original.tags,
                author_name=original.author_name,
                author_email=original.author_email,
                author_time=original.author_time,
                commit_time=original.commit_time,
                subject=original.subject,
                topo_rank=topo_rank[commit],
                is_head_file_version=commit == head_file_version,
            )

        for commit in order_newest:
            node = nodes[commit]
            if node.main_parent:
                edges.append(Edge(node.main_parent, commit, "main"))
            for parent in node.merge_parents:
                label = f"merge from '{parent.label}'" if parent.label else ""
                edges.append(Edge(parent.hash, commit, "merge", label))

        logger.info(
            "loaded file history commits=%d edges=%d rel_path=%s",
            len(nodes),
            len(edges),
            self.repo.rel_path,
        )
        return GraphModel(
            nodes=nodes,
            edges=tuple(edges),
            order_newest_first=tuple(order_newest),
            order_oldest_first=order_oldest,
            branches={},
        )

    def load_message(self, commit: str) -> str:
        logger.debug("loading commit message rel_path=%s commit=%s", self.repo.rel_path, commit[:12])
        message = self.repo.git_checked("show", "-s", "--format=%B", commit)
        logger.debug("loaded commit message commit=%s bytes=%d", commit[:12], len(message))
        return message

    def _head_file_version(self) -> str:
        result = self.repo.git("rev-list", "-1", "HEAD", "--", self.repo.rel_path)
        if result.returncode != 0:
            logger.warning(
                "unable to resolve HEAD file version rel_path=%s stderr=%s",
                self.repo.rel_path,
                result.stderr.strip(),
            )
            return ""
        commit = result.stdout.strip()
        logger.debug("resolved HEAD file version rel_path=%s commit=%s", self.repo.rel_path, commit[:12])
        return commit
