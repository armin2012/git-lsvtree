from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from git_lsvtree_ui.core.branch_rebuilder import BranchRebuilder
from git_lsvtree_ui.core.collapse_model import CollapseModel
from git_lsvtree_ui.core.diff_service import DiffResult, DiffService
from git_lsvtree_ui.core.git_repo import GitRepo
from git_lsvtree_ui.core.graph_model import GraphModel
from git_lsvtree_ui.core.history_loader import HistoryLoader
from git_lsvtree_ui.core.key_selector import KeySelector
from git_lsvtree_ui.layout.tree_layout import LayoutGraph, TreeLayout


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GraphLoadRequest:
    file_path: Path
    mode: Literal["full", "key"] = "key"
    key_threshold: int = 300
    collapse_enabled: bool = True
    include_all: bool = False
    expanded_runs: frozenset[str] | None = None


@dataclass(frozen=True)
class GraphLoadResult:
    file_path: Path
    layout: LayoutGraph
    mode: str
    graph: GraphModel
    partial: bool = False
    warning: str = ""


@dataclass(frozen=True)
class DiffLoadRequest:
    file_path: Path
    old_hash: str
    new_hash: str


class GraphLoaderSignals(QObject):
    loaded = Signal(object)
    failed = Signal(str)


class GraphLoaderWorker(QRunnable):
    def __init__(self, request: GraphLoadRequest):
        super().__init__()
        logger.debug("init graph loader worker request=%s", request)
        self.request = request
        self.signals = GraphLoaderSignals()

    @Slot()
    def run(self) -> None:
        logger.info("loading graph in worker file=%s mode=%s", self.request.file_path, self.request.mode)
        try:
            repo = GitRepo.from_file(self.request.file_path)
            graph = HistoryLoader(repo, include_all=self.request.include_all).load()
            graph = BranchRebuilder().rebuild(graph, main_branch=repo.current_branch())
            key_result = KeySelector().select(
                graph,
                mode=self.request.mode,
                threshold=self.request.key_threshold,
            )
            graph = key_result.graph
            branch_order = tuple(graph.branches.keys())
            display = CollapseModel(enabled=self.request.collapse_enabled).build(
                graph,
                expanded_runs=self.request.expanded_runs,
            )
            layout = TreeLayout().layout(display, branch_order=branch_order)
            result = GraphLoadResult(
                file_path=self.request.file_path,
                layout=layout,
                mode=self.request.mode,
                graph=graph,
                partial=key_result.partial,
                warning=key_result.warning,
            )
        except Exception as exc:
            logger.exception("graph worker failed file=%s", self.request.file_path)
            self.signals.failed.emit(str(exc))
            return

        logger.info("graph worker loaded file=%s nodes=%d", self.request.file_path, len(result.layout.nodes))
        self.signals.loaded.emit(result)


class DiffLoaderSignals(QObject):
    loaded = Signal(object)
    failed = Signal(str)


class DiffLoaderWorker(QRunnable):
    def __init__(self, request: DiffLoadRequest):
        super().__init__()
        logger.debug("init diff loader worker old=%s new=%s", request.old_hash[:12], request.new_hash[:12])
        self.request = request
        self.signals = DiffLoaderSignals()

    @Slot()
    def run(self) -> None:
        logger.info(
            "loading diff in worker old=%s new=%s", self.request.old_hash[:12], self.request.new_hash[:12]
        )
        try:
            repo = GitRepo.from_file(self.request.file_path)
            result: DiffResult = DiffService(repo).diff(self.request.old_hash, self.request.new_hash)
        except Exception as exc:
            logger.exception(
                "diff worker failed old=%s new=%s", self.request.old_hash[:12], self.request.new_hash[:12]
            )
            self.signals.failed.emit(str(exc))
            return

        logger.info("diff worker complete bytes=%d", len(result.text))
        self.signals.loaded.emit(result)
