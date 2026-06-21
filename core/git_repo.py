from __future__ import annotations

import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


logger = logging.getLogger(__name__)

# Suppress the black console window that flashes on each git call on Windows.
_POPEN_FLAGS: dict = (
    {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
)

# Force UTF-8 from git regardless of the system locale.
_GIT_ENV: dict[str, str] = {
    **os.environ,
    "GIT_TERMINAL_PROMPT": "0",
    "LANG": "en_US.UTF-8",
    "LC_ALL": "en_US.UTF-8",
}


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
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            env=_GIT_ENV,
            **_POPEN_FLAGS,
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
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            env=_GIT_ENV,
            **_POPEN_FLAGS,
        )

    @staticmethod
    def run_git_at(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
        """Run a git command rooted at `path` without a GitRepo instance."""
        command = ["git", *args]
        logger.debug("run_git_at path=%s command=%s", path, command)
        return subprocess.run(
            command,
            cwd=path,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            env=_GIT_ENV,
            **_POPEN_FLAGS,
        )

    def current_branch(self) -> str:
        result = self.git("symbolic-ref", "--short", "HEAD")
        name = result.stdout.strip()
        if result.returncode == 0 and name:
            return name
        # detached HEAD — consult git config, then fall back to "main"
        cfg = self.git("config", "--get", "init.defaultBranch")
        if cfg.returncode == 0 and cfg.stdout.strip():
            return cfg.stdout.strip()
        return "main"

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
