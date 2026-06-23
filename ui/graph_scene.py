from __future__ import annotations

import logging

from PySide6.QtCore import QRectF, Signal
from PySide6.QtGui import QBrush, QColor, QPen, QTransform
from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsScene, QGraphicsSimpleTextItem

from git_lsvtree_ui.layout.tree_layout import LayoutGraph

from .font_utils import choose_monospace_font
from .items import BranchHeaderItem, CollapsedRunItem, EdgeItem, VersionNodeItem


logger = logging.getLogger(__name__)

_LOD_LABEL_THRESHOLD = 0.35


class GraphScene(QGraphicsScene):
    nodeClickedWithModifiers = Signal(str, object)
    edgeClicked = Signal(str, str)
    runDoubleClicked = Signal(str)

    def __init__(self):
        super().__init__()
        logger.debug("init graph scene")
        self.item_by_id: dict[str, VersionNodeItem | CollapsedRunItem] = {}
        self.edge_by_id: dict[str, EdgeItem] = {}
        self._layout: LayoutGraph | None = None
        self._highlighted_id: str | None = None
        self._selected_ids: list[str] = []
        self._selected_edge_id: str | None = None
        self._edge_info_item: QGraphicsRectItem | None = None
        self._edge_info_text_item: QGraphicsSimpleTextItem | None = None

    def mousePressEvent(self, event):  # noqa: N802
        item = self.itemAt(event.scenePos(), self.views()[0].transform() if self.views() else QTransform())
        # Walk up to parent if child item (e.g. label_item) was hit
        while item and item.data(0) not in ("version_node", "run_node", "edge", None):
            item = item.parentItem()
        if item and item.data(0) == "edge":
            src_id = item.data(1)
            dst_id = item.data(2)
            logger.debug("scene edge clicked src=%s dst=%s", src_id, dst_id)
            self.set_edge_selection(src_id, dst_id)
            self.edgeClicked.emit(src_id, dst_id)
            event.accept()
            return
        if item and item.data(0) in ("version_node", "run_node"):
            node_id = item.data(1)
            logger.debug("scene node clicked node_id=%s kind=%s", node_id, item.data(0))
            self.clear_edge_selection()
            self.nodeClickedWithModifiers.emit(node_id, event.modifiers())
        elif item is None:
            self.clear_edge_selection()
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
        self._layout = layout
        self.item_by_id = {}
        self.edge_by_id = {}
        self._highlighted_id = None
        self._selected_ids = []
        self._selected_edge_id = None
        self._edge_info_item = None
        self._edge_info_text_item = None

        for header in layout.branch_headers.values():
            self.addItem(BranchHeaderItem(header))

        for edge in layout.edges:
            item = EdgeItem(edge)
            self.addItem(item)
            self.edge_by_id[item.edge_id] = item

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

    def set_edge_selection(self, src_id: str, dst_id: str) -> None:
        edge_id = f"{src_id}->{dst_id}"
        logger.debug("set edge selection old=%s new=%s", self._selected_edge_id, edge_id)
        old_rect = self._edge_info_scene_rect()
        self._clear_selected_edge_highlight()
        item = self.edge_by_id.get(edge_id)
        if not item or not self._layout:
            logger.debug("edge selection skipped missing edge=%s", edge_id)
            self._hide_edge_info_item(old_rect)
            return
        item.set_selected_state(True)
        self._selected_edge_id = edge_id
        self._update_edge_info_item(src_id, dst_id, item)
        self._refresh_region(old_rect, self._edge_info_scene_rect())

    def clear_edge_selection(self) -> None:
        logger.debug("clear edge selection current=%s", self._selected_edge_id)
        old_rect = self._edge_info_scene_rect()
        self._clear_selected_edge_highlight()
        self._hide_edge_info_item(old_rect)

    def _clear_selected_edge_highlight(self) -> None:
        if self._selected_edge_id and self._selected_edge_id in self.edge_by_id:
            self.edge_by_id[self._selected_edge_id].set_selected_state(False)
        self._selected_edge_id = None

    def _hide_edge_info_item(self, old_rect: QRectF | None = None) -> None:
        if self._edge_info_item is not None:
            self._edge_info_item.hide()
            self._refresh_region(old_rect or self._edge_info_scene_rect())

    def _ensure_edge_info_item(self) -> QGraphicsRectItem:
        if self._edge_info_item is not None and self._edge_info_text_item is not None:
            return self._edge_info_item
        panel = QGraphicsRectItem()
        panel.setBrush(QBrush(QColor("#fffbeb")))
        panel.setPen(QPen(QColor("#f59e0b"), 1.2))
        panel.setZValue(10.0)
        text_item = QGraphicsSimpleTextItem("", panel)
        text_item.setFont(choose_monospace_font())
        text_item.setBrush(QBrush(QColor("#111827")))
        panel.hide()
        self.addItem(panel)
        self._edge_info_item = panel
        self._edge_info_text_item = text_item
        logger.debug("created cached edge info overlay")
        return panel

    def _update_edge_info_item(self, src_id: str, dst_id: str, edge_item: EdgeItem) -> None:
        if not self._layout:
            return
        src = self._layout.nodes[src_id]
        dst = self._layout.nodes[dst_id]
        text = "\n".join((
            "edge endpoints",
            f"from: {self._format_node_summary(src)}",
            f"to:   {self._format_node_summary(dst)}",
        ))
        panel = self._ensure_edge_info_item()
        text_item = self._edge_info_text_item
        if text_item is None:
            return
        text_item.setText(text)
        bounds = text_item.boundingRect()
        pad = 6.0
        panel.setRect(QRectF(0, 0, bounds.width() + pad * 2, bounds.height() + pad * 2))
        text_item.setPos(pad, pad)
        anchor = edge_item.sceneBoundingRect().center()
        panel.setPos(anchor.x() + 10, anchor.y() + 10)
        panel.show()
        logger.debug("updated edge info overlay src=%s dst=%s pos=%s", src_id, dst_id, panel.pos())

    def _edge_info_scene_rect(self) -> QRectF | None:
        if self._edge_info_item is None or not self._edge_info_item.isVisible():
            return None
        return self._edge_info_item.sceneBoundingRect().adjusted(-2, -2, 2, 2)

    def _refresh_region(self, *rects: QRectF | None) -> None:
        refreshed = False
        for rect in rects:
            if rect is None or rect.isNull():
                continue
            self.invalidate(rect, QGraphicsScene.SceneLayer.AllLayers)
            self.update(rect)
            refreshed = True
        if not refreshed:
            self.update()
        for view in self.views():
            view.viewport().update()

    @staticmethod
    def _format_node_summary(node) -> str:
        return f"{node.label:<9} ｜ {node.id[:12]:<12} ｜ {node.branch}"

    def update_lod(self, zoom: float) -> None:
        show = zoom >= _LOD_LABEL_THRESHOLD
        for item in self.item_by_id.values():
            item.label_item.setVisible(show)
            tag_item = getattr(item, "tag_label_item", None)
            if tag_item is not None:
                tag_item.setVisible(show)
        logger.debug("lod updated zoom=%s show_labels=%s", zoom, show)
