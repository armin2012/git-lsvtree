from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QSizePolicy, QWidget

from git_lsvtree_ui.core.project_tree import ProjectTree
from git_lsvtree_ui.ui.project_navigator import ProjectNavigator


logger = logging.getLogger(__name__)

BTN_WIDTH = 18


class CollapsiblePanel(QWidget):
    """Generic collapsible sidebar panel with an 18-px toggle strip.

    side="left":  strip on right edge; ▶ = collapsed, ◀ = expanded
    side="right": strip on left edge;  ◀ = collapsed, ▶ = expanded
    """

    collapseToggled = Signal(bool)  # True = just collapsed, False = just expanded

    def __init__(self, widget: QWidget, side: Literal["left", "right"] = "left"):
        super().__init__()
        self._inner = widget
        self._collapsed = True

        if side == "left":
            self._txt_collapsed, self._txt_expanded = "▶", "◀"
        else:
            self._txt_collapsed, self._txt_expanded = "◀", "▶"

        self._btn = QPushButton(self._txt_collapsed)
        self._btn.setFixedWidth(BTN_WIDTH)
        self._btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._btn.setToolTip("Expand")
        self._btn.clicked.connect(self.toggle)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        if side == "left":
            layout.addWidget(widget)
            layout.addWidget(self._btn)
        else:
            layout.addWidget(self._btn)
            layout.addWidget(widget)

        self.setMinimumWidth(BTN_WIDTH)
        widget.hide()

    @property
    def is_collapsed(self) -> bool:
        return self._collapsed

    def expand(self) -> None:
        if not self._collapsed:
            return
        self._collapsed = False
        self._inner.show()
        self._btn.setText(self._txt_expanded)
        self._btn.setToolTip("Collapse")
        self.collapseToggled.emit(False)

    def collapse(self) -> None:
        if self._collapsed:
            return
        self._collapsed = True
        self._inner.hide()
        self._btn.setText(self._txt_collapsed)
        self._btn.setToolTip("Expand")
        self.collapseToggled.emit(True)

    def toggle(self) -> None:
        if self._collapsed:
            self.expand()
        else:
            self.collapse()


class CollapsibleNavigator(CollapsiblePanel):
    """CollapsiblePanel wrapping ProjectNavigator, with fileSelected forwarding."""

    fileSelected = Signal(Path)

    def __init__(self):
        self.navigator = ProjectNavigator()
        super().__init__(self.navigator, side="left")
        self.navigator.fileSelected.connect(self.fileSelected)
        logger.debug("init collapsible navigator")

    def set_project_tree(self, tree: ProjectTree) -> None:
        self.navigator.set_project_tree(tree)
