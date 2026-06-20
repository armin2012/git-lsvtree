from __future__ import annotations

import logging

from PySide6.QtCore import Signal
from PySide6.QtGui import QTransform
from PySide6.QtWidgets import QGraphicsScene

from git_lsvtree_ui.layout.tree_layout import LayoutGraph

from .items import BranchHeaderItem, CollapsedRunItem, EdgeItem, VersionNodeItem


logger = logging.getLogger(__name__)

_LOD_LABEL_THRESHOLD = 0.35


class GraphScene(QGraphicsScene):
    nodeClickedWithModifiers = Signal(str, object)
    runDoubleClicked = Signal(str)

    def __init__(self):
        super().__init__()
        logger.debug("init graph scene")
        self.item_by_id: dict[str, VersionNodeItem | CollapsedRunItem] = {}
        self._highlighted_id: str | None = None
        self._selected_ids: list[str] = []

    def mousePressEvent(self, event):  # noqa: N802
        item = self.itemAt(event.scenePos(), self.views()[0].transform() if self.views() else QTransform())
        # Walk up to parent if child item (e.g. label_item) was hit
        while item and item.data(0) not in ("version_node", "run_node", None):
            item = item.parentItem()
        if item and item.data(0) in ("version_node", "run_node"):
            node_id = item.data(1)
            logger.debug("scene node clicked node_id=%s kind=%s", node_id, item.data(0))
            self.nodeClickedWithModifiers.emit(node_id, event.modifiers())
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):  # noqa: N802
        item = self.itemAt(event.scenePos(), self.views()[0].transform() if self.views() else QTransform())
        while item and item.data(0) not in ("version_node", "run_node", None):
            item = item.parentItem()
        if item and item.data(0) == "run_node":
            run_id = item.data(1)
            logger.debug("scene run double clicked run_id=%s", run_id)
            self.runDoubleClicked.emit(run_id)
        super().mouseDoubleClickEvent(event)

    def set_layout_graph(self, layout: LayoutGraph) -> None:
        logger.info(
            "rendering layout graph to scene nodes=%d edges=%d branches=%d",
            len(layout.nodes),
            len(layout.edges),
            len(layout.branch_headers),
        )
        self.clear()
        self.item_by_id = {}
        self._highlighted_id = None
        self._selected_ids = []

        for header in layout.branch_headers.values():
            self.addItem(BranchHeaderItem(header))

        for edge in layout.edges:
            self.addItem(EdgeItem(edge))

        for node in layout.nodes.values():
            item = CollapsedRunItem(node) if node.kind == "run" else VersionNodeItem(node)
            self.addItem(item)
            self.item_by_id[node.id] = item

        self.setSceneRect(self.itemsBoundingRect())
        logger.debug("scene render complete item_count=%d", len(self.items()))

    def set_selection(self, node_ids: list[str]) -> None:
        for nid in self._selected_ids:
            if nid in self.item_by_id:
                self.item_by_id[nid].set_selected_state(False)
        self._selected_ids = list(node_ids)
        for nid in self._selected_ids:
            if nid in self.item_by_id:
                self.item_by_id[nid].set_selected_state(True)
        logger.debug("scene selection set ids=%s", self._selected_ids)

    def highlight_node(self, node_id: str | None) -> None:
        logger.debug("highlight node old=%s new=%s", self._highlighted_id, node_id)
        if self._highlighted_id and self._highlighted_id in self.item_by_id:
            self.item_by_id[self._highlighted_id].set_highlighted(False)
        self._highlighted_id = node_id
        if node_id and node_id in self.item_by_id:
            item = self.item_by_id[node_id]
            item.set_highlighted(True)
            for view in self.views():
                view.ensureVisible(item)

    def update_lod(self, zoom: float) -> None:
        show = zoom >= _LOD_LABEL_THRESHOLD
        for item in self.item_by_id.values():
            item.label_item.setVisible(show)
            tag_item = getattr(item, "tag_label_item", None)
            if tag_item is not None:
                tag_item.setVisible(show)
        logger.debug("lod updated zoom=%s show_labels=%s", zoom, show)
