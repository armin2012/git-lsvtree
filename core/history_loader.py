from __future__ import annotations

import dataclasses
import logging
import re

from .git_repo import GitRepo
from .graph_model import Edge, GraphModel, MergeParent, VersionNode


logger = logging.getLogger(__name__)

RS = "\x00"   # record separator — NUL is safe; git rejects NUL bytes in commit messages
GS = "\x02"   # field separator


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
    def __init__(self, repo: GitRepo, include_all: bool = False, include_repo_tags: bool = False):
        logger.debug(
            "init history loader rel_path=%s include_all=%s include_repo_tags=%s",
            repo.rel_path,
            include_all,
            include_repo_tags,
        )
        self.repo = repo
        self.include_all = include_all
        self.include_repo_tags = include_repo_tags

    def load(self) -> GraphModel:
        all_args = ("--all",) if self.include_all else ()
        fmt = "%x00%H %P%x02%D%x02%an%x02%ae%x02%at%x02%ct%x02%s%x02%cn%x02%ce%x02%b"
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
        records = [record for record in raw.split(RS) if record.strip()]
        if not records:
            logger.warning("no git history for rel_path=%s", self.repo.rel_path)
            return GraphModel({}, tuple(), tuple(), tuple(), {})

        parsed: dict[str, VersionNode] = {}
        order_newest: list[str] = []
        raw_parents: dict[str, tuple[str, ...]] = {}
        subjects: dict[str, str] = {}

        for rank, record in enumerate(records):
            fields = (record.split(GS, 9) + [""] * 10)[:10]
            (
                hash_and_parents,
                decorations,
                author_name,
                author_email,
                author_time,
                commit_time,
                subject,
                committer_name,
                committer_email,
                description,
            ) = fields
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
                committer_name=committer_name.strip(),
                committer_email=committer_email.strip(),
                description=description.strip(),
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
                committer_name=original.committer_name,
                committer_email=original.committer_email,
                description=original.description,
            )

        for commit in order_newest:
            node = nodes[commit]
            if node.main_parent:
                edges.append(Edge(node.main_parent, commit, "main"))
            for parent in node.merge_parents:
                label = f"merge from '{parent.label}'" if parent.label else ""
                edges.append(Edge(parent.hash, commit, "merge", label))

        if self.include_repo_tags:
            nodes = self._annotate_with_repo_tags(nodes)

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

    def _annotate_with_repo_tags(self, nodes: dict[str, VersionNode]) -> dict[str, VersionNode]:
        """Inject repo-wide git tags onto the nearest file-history ancestor node.

        git log -- <file> only captures tags on commits that directly touched the file.
        Release tags land on merge/release commits that often don't touch any single file,
        so we look up each tag separately with rev-list -1 to find its file-history anchor.
        """
        result = self.repo.git("tag", "-l", "--sort=-version:refname")
        if result.returncode != 0 or not result.stdout.strip():
            return nodes

        all_tags = result.stdout.strip().splitlines()[:50]
        updated = dict(nodes)

        for tag in all_tags:
            r = self.repo.git("rev-list", "-1", tag, "--", self.repo.rel_path)
            if r.returncode != 0 or not r.stdout.strip():
                continue
            commit_hash = r.stdout.strip()
            if commit_hash not in updated:
                continue
            existing = updated[commit_hash]
            if tag not in existing.tags:
                updated[commit_hash] = dataclasses.replace(existing, tags=existing.tags + (tag,))

        return updated

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
