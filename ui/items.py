from __future__ import annotations

import logging

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsLineItem, QGraphicsRectItem, QGraphicsSimpleTextItem

from git_lsvtree_ui.layout.tree_layout import BranchHeader, LayoutEdge, LayoutNode


logger = logging.getLogger(__name__)

_COLOR_NODE_FILL = QColor("#dbeafe")
_COLOR_NODE_BORDER = QColor("#1d4ed8")
_COLOR_NODE_SELECTED_FILL = QColor("#fef08a")
_COLOR_NODE_SELECTED_BORDER = QColor("#ca8a04")
_COLOR_NODE_HIGHLIGHT = QColor("#fbbf24")
_COLOR_RUN_FILL = QColor("#f3f4f6")
_COLOR_RUN_BORDER = QColor("#6b7280")


class VersionNodeItem(QGraphicsEllipseItem):
    def __init__(self, node: LayoutNode):
        logger.debug("create version node item id=%s branch=%s topo_rank=%s", node.id, node.branch, node.topo_rank)
        r = node.radius
        super().__init__(QRectF(node.center.x - r, node.center.y - r, r * 2, r * 2))
        self.setData(0, "version_node")
        self.setData(1, node.id)
        self._selected_state = False
        self.setBrush(QBrush(_COLOR_NODE_FILL))
        self.setPen(QPen(_COLOR_NODE_BORDER, 1.4))
        self.setToolTip(node.id[:12])
        self.label_item = QGraphicsSimpleTextItem(node.label, self)
        self.label_item.setBrush(QBrush(QColor("#111827")))
        self.label_item.setPos(node.center.x + r + 4, node.center.y - r)

    def set_selected_state(self, on: bool) -> None:
        self._selected_state = on
        if on:
            self.setBrush(QBrush(_COLOR_NODE_SELECTED_FILL))
            self.setPen(QPen(_COLOR_NODE_SELECTED_BORDER, 2.5))
        else:
            self.setBrush(QBrush(_COLOR_NODE_FILL))
            self.setPen(QPen(_COLOR_NODE_BORDER, 1.4))

    def set_highlighted(self, on: bool) -> None:
        if not self._selected_state:
            self.setBrush(QBrush(_COLOR_NODE_HIGHLIGHT if on else _COLOR_NODE_FILL))


class CollapsedRunItem(QGraphicsRectItem):
    def __init__(self, node: LayoutNode):
        logger.debug("create collapsed run item id=%s branch=%s topo_rank=%s", node.id, node.branch, node.topo_rank)
        width = node.radius * 4
        height = node.radius * 2
        super().__init__(
            QRectF(
                node.center.x - width / 2,
                node.center.y - height / 2,
                width,
                height,
            )
        )
        self.setData(0, "run_node")
        self.setData(1, node.id)
        self.setBrush(QBrush(_COLOR_RUN_FILL))
        pen = QPen(_COLOR_RUN_BORDER, 1.2)
        pen.setStyle(Qt.PenStyle.DashLine)
        self.setPen(pen)
        self.setToolTip(f"{node.label}: {len(node.source_hashes)} versions — double-click to expand")
        self.label_item = QGraphicsSimpleTextItem(node.label, self)
        self.label_item.setBrush(QBrush(QColor("#374151")))
        self.label_item.setPos(node.center.x + width / 2 + 4, node.center.y - height / 2)

    def set_selected_state(self, on: bool) -> None:
        pass  # run nodes are not diffable; no selection visual needed

    def set_highlighted(self, on: bool) -> None:
        self.setBrush(QBrush(QColor("#fde68a") if on else _COLOR_RUN_FILL))


class BranchHeaderItem(QGraphicsRectItem):
    def __init__(self, header: BranchHeader):
        logger.debug("create branch header item branch=%s", header.branch)
        rect = header.rect
        super().__init__(QRectF(rect.x, rect.y, rect.width, rect.height))
        self.setData(0, "branch_header")
        self.setData(1, header.branch)
        self.setBrush(QBrush(QColor("#bfdbfe")))
        self.setPen(QPen(QColor("#1e40af"), 1.2))
        self.setToolTip(header.label)
        self.label_item = QGraphicsSimpleTextItem(header.label, self)
        self.label_item.setBrush(QBrush(QColor("#1e3a8a")))
        self.label_item.setPos(rect.x + 4, rect.y + 1)


class EdgeItem(QGraphicsLineItem):
    def __init__(self, edge: LayoutEdge):
        logger.debug("create edge item src=%s dst=%s kind=%s", edge.src, edge.dst, edge.kind)
        super().__init__(edge.start.x, edge.start.y, edge.end.x, edge.end.y)
        self.setData(0, "edge")
        self.setData(1, f"{edge.src}->{edge.dst}")
        color = QColor("#dc2626") if edge.kind == "merge" else QColor("#374151")
        pen = QPen(color, 1.4)
        if edge.kind == "merge":
            pen.setStyle(Qt.PenStyle.DashLine)
        self.setPen(pen)
        self.setZValue(-1)
        self.setToolTip(edge.label or edge.kind)
