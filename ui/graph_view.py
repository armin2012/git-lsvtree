from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGraphicsView

from .graph_scene import GraphScene


logger = logging.getLogger(__name__)


class GraphView(QGraphicsView):
    def __init__(self):
        super().__init__()
        logger.debug("init graph view")
        self.zoom_factor = 1.0
        self.setScene(GraphScene())
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._panning = False

    def zoom_in(self) -> None:
        logger.debug("graph view zoom in current=%s", self.zoom_factor)
        self._set_zoom(self.zoom_factor * 1.2)

    def zoom_out(self) -> None:
        logger.debug("graph view zoom out current=%s", self.zoom_factor)
        self._set_zoom(self.zoom_factor / 1.2)

    def reset_zoom(self) -> None:
        self.resetTransform()
        self.zoom_factor = 1.0
        self.scene().update_lod(self.zoom_factor)
        logger.debug("graph view reset zoom")

    def fit_to_view(self) -> None:
        scene = self.scene()
        if not scene or scene.sceneRect().isEmpty():
            logger.debug("fit skipped: empty scene")
            return
        self.fitInView(scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self.zoom_factor = self.transform().m11()
        self.scene().update_lod(self.zoom_factor)
        logger.debug("graph view fit to scene rect=%s zoom=%s", scene.sceneRect(), self.zoom_factor)

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._panning:
            delta = event.position().toPoint() - self._pan_start
            self._pan_start = event.position().toPoint()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):  # noqa: N802
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            logger.debug("graph view wheel zoom delta=%s", event.angleDelta().y())
            if event.angleDelta().y() > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            event.accept()
        else:
            super().wheelEvent(event)

    def _set_zoom(self, zoom: float) -> None:
        zoom = max(0.1, min(8.0, zoom))
        ratio = zoom / self.zoom_factor
        self.scale(ratio, ratio)
        self.zoom_factor = zoom
        self.scene().update_lod(zoom)
        logger.debug("graph view zoom=%s", self.zoom_factor)
