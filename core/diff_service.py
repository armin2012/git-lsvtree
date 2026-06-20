from __future__ import annotations

import logging
from dataclasses import dataclass

from .git_repo import GitRepo


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DiffResult:
    old_hash: str
    new_hash: str
    rel_path: str
    text: str


class DiffService:
    def __init__(self, repo: GitRepo):
        logger.debug("init diff service rel_path=%s", repo.rel_path)
        self.repo = repo

    def diff(self, old_hash: str, new_hash: str) -> DiffResult:
        logger.info(
            "running diff rel_path=%s old=%s new=%s",
            self.repo.rel_path,
            old_hash[:12],
            new_hash[:12],
        )
        text = self.repo.git_checked(
            "diff",
            f"{old_hash}:{self.repo.rel_path}",
            f"{new_hash}:{self.repo.rel_path}",
        )
        logger.debug(
            "diff complete rel_path=%s old=%s new=%s bytes=%d",
            self.repo.rel_path,
            old_hash[:12],
            new_hash[:12],
            len(text),
        )
        return DiffResult(old_hash, new_hash, self.repo.rel_path, text)
