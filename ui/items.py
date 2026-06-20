from __future__ import annotations

import logging
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainterPath, QPainterPathStroker, QPen, QPolygonF
from PySide6.QtWidgets import (
    QGraphicsEllipseItem, QGraphicsPathItem, QGraphicsRectItem, QGraphicsSimpleTextItem,
)

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
        tip = node.id[:12]
        if node.tags:
            tip += "\n" + "  ".join(node.tags)
        self.setToolTip(tip)
        self.label_item = QGraphicsSimpleTextItem(node.label, self)
        self.label_item.setBrush(QBrush(QColor("#111827")))
        self.label_item.setPos(node.center.x + r + 4, node.center.y - r)
        self.tag_label_item: QGraphicsRectItem | None = None
        if node.tags:
            tag_text = "  ".join(node.tags[:2])
            # measure text to size the badge background
            _tmp = QGraphicsSimpleTextItem(tag_text)
            _br = _tmp.boundingRect()
            _px, _py = 4, 1
            _bw, _bh = _br.width() + _px * 2, _br.height() + _py * 2
            # position badge to the right of node, just below the version-number label
            _bx = node.center.x + r + 4
            _by = node.center.y - r + _br.height() + 4
            badge = QGraphicsRectItem(QRectF(0, 0, _bw, _bh), self)
            badge.setPos(_bx, _by)
            badge.setBrush(QBrush(QColor("#fef3c7")))
            badge.setPen(QPen(QColor("#d97706"), 0.8))
            tag_lbl = QGraphicsSimpleTextItem(tag_text, badge)
            tag_lbl.setPos(_px, _py)
            tag_lbl.setBrush(QBrush(QColor("#92400e")))
            self.tag_label_item = badge

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


class EdgeItem(QGraphicsPathItem):
    _ARROW_LEN: float = 9.0
    _ARROW_W: float = 5.0

    def __init__(self, edge: LayoutEdge):
        logger.debug("create edge item src=%s dst=%s kind=%s", edge.src, edge.dst, edge.kind)
        super().__init__()
        self.edge_id = f"{edge.src}->{edge.dst}"
        self.setData(0, "edge")
        self.setData(1, edge.src)
        self.setData(2, edge.dst)
        self.setData(3, edge.kind)
        self.setToolTip(edge.label or edge.kind)
        self._selected_state = False

        if edge.kind == "merge":
            color = QColor("#dc2626")
            line_width = 2.0
            dash = True
            self.setZValue(1.0)   # above nodes so merge lines are always visible
        elif edge.kind == "branch":
            color = QColor("#1d4ed8")
            line_width = 1.8
            dash = False
            self.setZValue(-0.5)  # behind nodes
        else:
            color = QColor("#374151")
            line_width = 1.8
            dash = False
            self.setZValue(-1.0)  # furthest behind
        self._base_z = self.zValue()

        sx, sy = edge.start.x, edge.start.y
        ex, ey = edge.end.x, edge.end.y
        dx, dy = ex - sx, ey - sy
        length = math.hypot(dx, dy)

        path = QPainterPath()
        if length < 1.0:
            path.moveTo(sx, sy)
            path.lineTo(ex, ey)
        else:
            ux, uy = dx / length, dy / length
            bx = ex - self._ARROW_LEN * ux
            by = ey - self._ARROW_LEN * uy
            path.moveTo(sx, sy)
            path.lineTo(bx, by)
            px, py = -uy, ux
            arrow = QPolygonF([
                QPointF(ex, ey),
                QPointF(bx + self._ARROW_W * px, by + self._ARROW_W * py),
                QPointF(bx - self._ARROW_W * px, by - self._ARROW_W * py),
            ])
            path.addPolygon(arrow)
            path.closeSubpath()

        self.setPath(path)
        pen = QPen(color, line_width)
        if dash:
            pen.setStyle(Qt.PenStyle.DashLine)
        self._base_pen = QPen(pen)
        self._selected_pen = QPen(QColor("#f59e0b"), line_width + 2.5)
        self._base_brush = QBrush(color)
        self._selected_brush = QBrush(QColor("#f59e0b"))
        self.setPen(pen)
        self.setBrush(self._base_brush)

    def set_selected_state(self, on: bool) -> None:
        logger.debug("set edge selected edge=%s selected=%s", self.edge_id, on)
        self._selected_state = on
        if on:
            self.setPen(self._selected_pen)
            self.setBrush(self._selected_brush)
            self.setZValue(max(self.zValue(), 2.0))
        else:
            self.setPen(self._base_pen)
            self.setBrush(self._base_brush)
            self.setZValue(self._base_z)

    def shape(self):  # noqa: D102
        stroker = QPainterPathStroker()
        stroker.setWidth(max(10.0, self.pen().widthF() + 6.0))
        return stroker.createStroke(self.path()).united(self.path())
