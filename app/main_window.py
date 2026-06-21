from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QAction, QPainter, QPixmap
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QStackedWidget,
    QToolBar,
)

from git_lsvtree_ui.app.graph_loader import (
    DiffLoadRequest,
    DiffLoaderWorker,
    GraphLoadRequest,
    GraphLoadResult,
    GraphLoaderWorker,
)
from git_lsvtree_ui.core.diff_service import DiffResult
from git_lsvtree_ui.core.graph_model import GraphModel
from git_lsvtree_ui.layout.tree_layout import LayoutGraph
from git_lsvtree_ui.ui.detail_panel import DetailPanel
from git_lsvtree_ui.ui.diff_panel import DiffPanel
from git_lsvtree_ui.ui.graph_view import GraphView
from git_lsvtree_ui.ui.status_bar import GitLsvtreeStatusBar


logger = logging.getLogger(__name__)
MAX_EXPORT_PIXELS = 12_000_000


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        logger.debug("init main window")
        self.setWindowTitle("git-lsvtree-ui")
        self.thread_pool = QThreadPool.globalInstance()
        self.current_file: Path | None = None
        self.current_mode = "key"
        self.collapse_enabled = True
        self.expanded_runs: frozenset[str] = frozenset()
        self.selected_versions: list[str] = []
        self.current_run: str | None = None
        self._pending_run: str | None = None
        self.current_layout: LayoutGraph | None = None
        self.current_graph: GraphModel | None = None

        self.graph_view = GraphView()
        self.graph_view.scene().nodeClickedWithModifiers.connect(self._on_node_clicked_with_modifiers)
        self.graph_view.scene().edgeClicked.connect(self._on_edge_clicked)
        self.graph_view.scene().runDoubleClicked.connect(self.expand_run)

        self.empty_label = QLabel("Open a file to begin (Ctrl+O)")
        self.empty_label.setObjectName("emptyLabel")
        self.stack = QStackedWidget()
        self.stack.addWidget(self.empty_label)
        self.stack.addWidget(self.graph_view)
        self.setCentralWidget(self.stack)

        self.detail_panel = DetailPanel()
        self.diff_panel = DiffPanel()
        self.status_bar = GitLsvtreeStatusBar()
        self.setStatusBar(self.status_bar)

        self._create_actions()
        self._create_menus()
        self._create_toolbar()
        self._create_docks()
        self.set_empty_state()
        logger.debug("main window initialized")

    # ── action / menu / toolbar / dock construction ────────────────────────

    def _create_actions(self) -> None:
        logger.debug("creating main window actions")
        self.open_action = self._make_action("Open", self.open_file_dialog, "Ctrl+O")
        self.reload_action = self._make_action("Reload", self.reload_current_file, "F5")
        self.full_action = self._make_action("Full", lambda: self.reload_current_file(mode="full"))
        self.key_action = self._make_action("Key", lambda: self.reload_current_file(mode="key"))
        self.collapse_action = self._make_action("Collapse", self.toggle_collapse)
        self.collapse_action.setCheckable(True)
        self.collapse_action.setChecked(self.collapse_enabled)
        self.expand_run_action = self._make_action("Expand Run", self.expand_current_run)
        self.collapse_run_action = self._make_action("Collapse Run", self.collapse_current_run)
        self.diff_action = self._make_action("Diff", self.run_diff, "Ctrl+D")
        self.zoom_in_action = self._make_action("Zoom In", self.graph_view.zoom_in, "Ctrl++")
        self.zoom_out_action = self._make_action("Zoom Out", self.graph_view.zoom_out, "Ctrl+-")
        self.fit_action = self._make_action("Fit", self.graph_view.fit_to_view, "Ctrl+0")
        self.reset_zoom_action = self._make_action("100%", self.graph_view.reset_zoom, "Ctrl+1")
        self.export_action = self._make_action("Export PNG…", self.export_png, "Ctrl+E")
        logger.debug("created main window actions")

    def _make_action(self, text: str, slot, shortcut: str | None = None) -> QAction:
        action = QAction(text, self)
        action.triggered.connect(slot)
        if shortcut:
            action.setShortcut(shortcut)
        return action

    def _create_menus(self) -> None:
        logger.debug("creating main menus")
        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction(self.open_action)
        file_menu.addAction(self.reload_action)
        file_menu.addSeparator()
        file_menu.addAction(self.export_action)

        view_menu = self.menuBar().addMenu("View")
        for action in (
            self.full_action,
            self.key_action,
            self.collapse_action,
            self.expand_run_action,
            self.collapse_run_action,
            self.diff_action,
            self.zoom_in_action,
            self.zoom_out_action,
            self.fit_action,
            self.reset_zoom_action,
        ):
            view_menu.addAction(action)

        self.menuBar().addMenu("Tools")
        self.menuBar().addMenu("Help")
        logger.debug("created main menus")

    def _create_toolbar(self) -> None:
        logger.debug("creating main toolbar")
        toolbar = QToolBar("Main")
        self.addToolBar(toolbar)
        for action in (
            self.open_action,
            self.reload_action,
            self.full_action,
            self.key_action,
            self.collapse_action,
            self.expand_run_action,
            self.collapse_run_action,
            self.diff_action,
            self.zoom_in_action,
            self.zoom_out_action,
            self.fit_action,
            self.reset_zoom_action,
            self.export_action,
        ):
            toolbar.addAction(action)

        toolbar.addSeparator()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search hash / label…")
        self.search_box.setMaximumWidth(200)
        self.search_box.textChanged.connect(self._search_node)
        toolbar.addWidget(self.search_box)
        logger.debug("created main toolbar action_count=%d", len(toolbar.actions()))

    def _create_docks(self) -> None:
        logger.debug("creating dock widgets")
        _no_float = QDockWidget.DockWidgetFeature.DockWidgetClosable | QDockWidget.DockWidgetFeature.DockWidgetMovable

        detail_dock = QDockWidget("Details", self)
        detail_dock.setObjectName("detailDock")
        detail_dock.setFeatures(_no_float)
        detail_dock.setWidget(self.detail_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, detail_dock)

        diff_dock = QDockWidget("Diff", self)
        diff_dock.setObjectName("diffDock")
        diff_dock.setFeatures(_no_float)
        diff_dock.setWidget(self.diff_panel)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, diff_dock)
        logger.debug("created dock widgets")

    # ── state setters ──────────────────────────────────────────────────────

    def set_empty_state(self) -> None:
        logger.info("main window set empty state")
        self.current_file = None
        self.current_layout = None
        self.current_graph = None
        self.selected_versions = []
        self.current_run = None
        self._pending_run = None
        self.stack.setCurrentWidget(self.empty_label)
        self._set_graph_actions_enabled(False)
        self._update_selection_actions()

    def set_loading_state(self, file_path: Path) -> None:
        logger.info("main window loading file=%s", file_path)
        self.current_file = file_path
        self.empty_label.setText(f"Loading {file_path} …")
        self.stack.setCurrentWidget(self.empty_label)
        self._set_graph_actions_enabled(False)

    def set_loaded_layout(self, result: GraphLoadResult) -> None:
        logger.info(
            "main window loaded layout file=%s nodes=%d partial=%s",
            result.file_path,
            len(result.layout.nodes),
            result.partial,
        )
        self.current_file = Path(result.file_path)
        self.current_layout = result.layout
        self.current_graph = result.graph
        self.current_mode = result.mode
        self.selected_versions = []
        self.current_run = self._pending_run
        self._pending_run = None
        self.graph_view.scene().set_layout_graph(result.layout)
        self.stack.setCurrentWidget(self.graph_view)
        self._set_graph_actions_enabled(True)
        self._update_selection_actions()
        self.status_bar.set_loaded(
            result.file_path,
            result.mode,
            version_count=len(result.layout.nodes),
            branch_count=len(result.layout.branch_headers),
            zoom=self.graph_view.zoom_factor,
            warning=result.warning,
        )

    # ── file loading ───────────────────────────────────────────────────────

    def open_file_dialog(self) -> None:
        logger.debug("opening file dialog")
        path, _ = QFileDialog.getOpenFileName(self, "Open file")
        logger.debug("file dialog selected path=%s", path)
        if path:
            self.load_file(Path(path))

    def load_file(self, file_path: Path, mode: str = "key") -> None:
        logger.info("main window load file requested file=%s mode=%s", file_path, mode)
        self.current_mode = mode
        self.set_loading_state(file_path)
        worker = GraphLoaderWorker(
            GraphLoadRequest(
                file_path=file_path,
                mode=mode,
                collapse_enabled=self.collapse_enabled,
                include_repo_tags=True,
                expanded_runs=self.expanded_runs,
            )
        )
        worker.signals.loaded.connect(self._on_graph_loaded)
        worker.signals.failed.connect(self._on_graph_failed)
        self.thread_pool.start(worker)

    def reload_current_file(self, mode: str = "key") -> None:
        logger.debug("reload requested current_file=%s mode=%s", self.current_file, mode)
        if self.current_file:
            self.load_file(self.current_file, mode=mode)

    # ── collapse / expand ──────────────────────────────────────────────────

    def toggle_collapse(self) -> None:
        self.collapse_enabled = self.collapse_action.isChecked()
        logger.info("toggle collapse enabled=%s", self.collapse_enabled)
        if self.current_file:
            self.load_file(self.current_file, mode=self.current_mode)

    def expand_current_run(self) -> None:
        logger.debug("expand current run current_run=%s", self.current_run)
        if self.current_run:
            self.expand_run(self.current_run)

    def expand_run(self, run_id: str) -> None:
        logger.info("expand run requested run_id=%s", run_id)
        self.expanded_runs = frozenset((*self.expanded_runs, run_id))
        self._pending_run = run_id
        if self.current_file:
            self.load_file(self.current_file, mode=self.current_mode)

    def collapse_current_run(self) -> None:
        logger.info("collapse current run requested current_run=%s", self.current_run)
        if not self.current_run:
            return
        self.expanded_runs = frozenset(r for r in self.expanded_runs if r != self.current_run)
        self._pending_run = None
        self.current_run = None
        if self.current_file:
            self.load_file(self.current_file, mode=self.current_mode)

    # ── diff ───────────────────────────────────────────────────────────────

    def run_diff(self) -> None:
        logger.info("run diff selected_versions=%s", self.selected_versions)
        if not self.current_file or len(self.selected_versions) != 2 or not self.current_layout:
            return
        nodes = self.current_layout.nodes
        v0, v1 = self.selected_versions
        # Ensure old→new order by topo_rank (lower rank = older)
        if nodes[v0].topo_rank > nodes[v1].topo_rank:
            v0, v1 = v1, v0
        graph_nodes = self.current_graph.nodes if self.current_graph else {}
        n0 = graph_nodes.get(v0)
        n1 = graph_nodes.get(v1)
        self.diff_panel.show_loading()
        worker = DiffLoaderWorker(DiffLoadRequest(
            file_path=self.current_file,
            old_hash=v0,
            new_hash=v1,
            old_branch=n0.reconstructed_branch if n0 else "",
            old_branch_index=n0.per_branch_index if n0 else -1,
            new_branch=n1.reconstructed_branch if n1 else "",
            new_branch_index=n1.per_branch_index if n1 else -1,
        ))
        worker.signals.loaded.connect(self._on_diff_loaded)
        worker.signals.failed.connect(self._on_diff_failed)
        self.thread_pool.start(worker)

    # ── export ─────────────────────────────────────────────────────────────

    def export_png(self) -> None:
        logger.debug("export png requested")
        scene = self.graph_view.scene()
        if not scene or scene.sceneRect().isEmpty():
            logger.debug("export skipped: empty scene")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export PNG", "", "PNG (*.png)")
        if not path:
            return
        rect = scene.sceneRect()
        width = max(1, int(rect.width()))
        height = max(1, int(rect.height()))
        pixels = width * height
        if pixels > MAX_EXPORT_PIXELS:
            scale = (MAX_EXPORT_PIXELS / pixels) ** 0.5
            width = max(1, int(width * scale))
            height = max(1, int(height * scale))
            logger.info("export png scaled to width=%d height=%d", width, height)
        pixmap = QPixmap(width, height)
        pixmap.fill(Qt.GlobalColor.white)
        painter = QPainter(pixmap)
        scene.render(painter)
        painter.end()
        ok = pixmap.save(path)
        logger.info("export png saved=%s path=%s", ok, path)

    # ── search ─────────────────────────────────────────────────────────────

    def _search_node(self, text: str) -> None:
        logger.debug("search node text=%s", text)
        if not text or not self.current_layout:
            self.graph_view.scene().highlight_node(None)
            return
        text_lower = text.lower()
        for node_id, node in self.current_layout.nodes.items():
            if node_id.startswith(text_lower) or text_lower in node.label.lower():
                self.graph_view.scene().highlight_node(node_id)
                return
        self.graph_view.scene().highlight_node(None)

    # ── slot handlers ──────────────────────────────────────────────────────

    def _on_graph_loaded(self, result: GraphLoadResult) -> None:
        logger.debug("graph loaded signal received file=%s mode=%s", result.file_path, result.mode)
        self.set_loaded_layout(result)

    def _on_graph_failed(self, message: str) -> None:
        logger.warning("graph load failed message=%s", message)
        self._pending_run = None
        self.empty_label.setText(f"Error: {message}")
        self.stack.setCurrentWidget(self.empty_label)
        self._set_graph_actions_enabled(False)

    def _on_node_clicked_with_modifiers(self, node_id: str, modifiers) -> None:
        logger.debug("main window node clicked node_id=%s", node_id)
        if not self.current_layout or node_id not in self.current_layout.nodes:
            return
        node = self.current_layout.nodes[node_id]
        if node.kind == "run":
            self.current_run = node.id
            self.selected_versions = []
            if self.current_graph:
                self.detail_panel.show_run(node)
            else:
                self.detail_panel.setPlainText(f"Collapsed run: {node.id}\nVersions: {len(node.source_hashes)}")
        else:
            self.current_run = None
            if modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
                self.selected_versions = [*self.selected_versions, node.id][-2:]
            else:
                self.selected_versions = [node.id]
            if self.current_graph:
                self.detail_panel.show_version(node, self.current_graph)
            else:
                self.detail_panel.setPlainText(f"Node: {node.id}\nbranch: {node.branch}")
        self.graph_view.scene().set_selection(self.selected_versions)
        self._update_selection_actions()

    def _on_edge_clicked(self, src_id: str, dst_id: str) -> None:
        logger.debug("main window edge clicked src=%s dst=%s", src_id, dst_id)
        self.selected_versions = []
        self.current_run = None
        self.graph_view.scene().set_selection([])
        self._update_selection_actions()
        self.status_bar.showMessage(f"Edge selected: {src_id[:12]} -> {dst_id[:12]}")

    def _on_diff_loaded(self, result: DiffResult) -> None:
        logger.debug("diff loaded old=%s new=%s", result.old_hash[:12], result.new_hash[:12])
        self.diff_panel.show_diff(result)

    def _on_diff_failed(self, message: str) -> None:
        logger.warning("diff load failed message=%s", message)
        self.diff_panel.show_error(message)

    # ── action state helpers ───────────────────────────────────────────────

    def _update_selection_actions(self) -> None:
        enabled_diff = len(self.selected_versions) == 2
        enabled_run = bool(self.current_run)
        logger.debug(
            "update selection actions diff=%s run=%s selected=%s current_run=%s",
            enabled_diff,
            enabled_run,
            self.selected_versions,
            self.current_run,
        )
        self.diff_action.setEnabled(enabled_diff)
        self.expand_run_action.setEnabled(enabled_run)
        self.collapse_run_action.setEnabled(enabled_run and self.current_run in self.expanded_runs)
        self._update_hint_message()

    def _update_hint_message(self) -> None:
        n = len(self.selected_versions)
        if n == 0:
            hint = "Click a version node to select it  •  Ctrl+click to select a second node  •  then press Diff (Ctrl+D)"
        elif n == 1:
            hint = f"1 version selected: {self.selected_versions[0][:12]}  •  Ctrl+click a second node to enable Diff"
        else:
            hint = (
                f"2 versions selected: {self.selected_versions[0][:12]} … {self.selected_versions[1][:12]}"
                "  •  Press Diff (Ctrl+D) or click the Diff button"
            )
        self.status_bar.showMessage(hint)

    def _set_graph_actions_enabled(self, enabled: bool) -> None:
        logger.debug("set graph actions enabled=%s", enabled)
        for action in (
            self.reload_action,
            self.full_action,
            self.key_action,
            self.collapse_action,
            self.expand_run_action,
            self.collapse_run_action,
            self.diff_action,
            self.zoom_in_action,
            self.zoom_out_action,
            self.fit_action,
            self.reset_zoom_action,
            self.export_action,
        ):
            action.setEnabled(enabled)
        if enabled:
            self._update_selection_actions()
        logger.debug("graph actions updated enabled=%s", enabled)
