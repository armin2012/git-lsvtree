from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path


logger = logging.getLogger(__name__)


@dataclass
class GitCommandError(RuntimeError):
    command: tuple[str, ...]
    cwd: Path
    returncode: int
    stdout: str
    stderr: str

    def __post_init__(self) -> None:
        RuntimeError.__init__(self, str(self))

    def __str__(self) -> str:
        command = " ".join(self.command)
        return (
            f"git command failed: {command} "
            f"(cwd={self.cwd}, exit={self.returncode})\n{self.stderr.strip()}"
        )


@dataclass(frozen=True)
class GitRepo:
    repo_root: Path
    file_path: Path
    rel_path: str

    @classmethod
    def from_file(cls, file_path: Path) -> "GitRepo":
        path = file_path.resolve()
        start = path.parent if path.is_file() else path
        logger.debug("resolving git repository for file=%s", path)
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=start,
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            raise GitCommandError(
                command=("git", "rev-parse", "--show-toplevel"),
                cwd=start,
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        root = Path(result.stdout.strip()).resolve()
        rel_path = path.relative_to(root).as_posix()
        logger.info("resolved git repo root=%s rel_path=%s", root, rel_path)
        return cls(repo_root=root, file_path=path, rel_path=rel_path)

    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        command = ("git", *args)
        logger.debug("running git command cwd=%s command=%s", self.repo_root, command)
        return subprocess.run(
            list(command),
            cwd=self.repo_root,
            text=True,
            capture_output=True,
        )

    def git_checked(self, *args: str) -> str:
        result = self.git(*args)
        if result.returncode != 0:
            command = ("git", *args)
            logger.warning(
                "git command failed cwd=%s command=%s returncode=%s stderr=%s",
                self.repo_root,
                command,
                result.returncode,
                result.stderr.strip(),
            )
            raise GitCommandError(
                command=command,
                cwd=self.repo_root,
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        return result.stdout
