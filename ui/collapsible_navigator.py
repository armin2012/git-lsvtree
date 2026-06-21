from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QSizePolicy, QWidget

from git_lsvtree_ui.core.project_tree import ProjectTree
from git_lsvtree_ui.ui.project_navigator import ProjectNavigator


logger = logging.getLogger(__name__)

BTN_WIDTH = 18


class CollapsibleNavigator(QWidget):
    """ProjectNavigator in a collapsible left-sidebar container.

    Collapsed: BTN_WIDTH px wide, only the ▶ toggle strip is visible.
    Expanded:  full width, navigator visible, ◀ strip on the right edge.
    """

    collapseToggled = Signal(bool)  # True = just collapsed, False = just expanded
    fileSelected = Signal(Path)

    def __init__(self):
        super().__init__()
        logger.debug("init collapsible navigator")
        self._collapsed = True

        self.navigator = ProjectNavigator()
        self.navigator.fileSelected.connect(self.fileSelected)

        self._toggle_btn = QPushButton("▶")
        self._toggle_btn.setFixedWidth(BTN_WIDTH)
        self._toggle_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._toggle_btn.setToolTip("Expand project navigator")
        self._toggle_btn.clicked.connect(self.toggle)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.navigator)
        layout.addWidget(self._toggle_btn)

        self.setMinimumWidth(BTN_WIDTH)
        self.navigator.hide()

    @property
    def is_collapsed(self) -> bool:
        return self._collapsed

    def set_project_tree(self, tree: ProjectTree) -> None:
        self.navigator.set_project_tree(tree)

    def expand(self) -> None:
        if not self._collapsed:
            return
        self._collapsed = False
        self.navigator.show()
        self._toggle_btn.setText("◀")
        self._toggle_btn.setToolTip("Collapse project navigator")
        logger.debug("collapsible navigator expanded")
        self.collapseToggled.emit(False)

    def collapse(self) -> None:
        if self._collapsed:
            return
        self._collapsed = True
        self.navigator.hide()
        self._toggle_btn.setText("▶")
        self._toggle_btn.setToolTip("Expand project navigator")
        logger.debug("collapsible navigator collapsed")
        self.collapseToggled.emit(True)

    def toggle(self) -> None:
        if self._collapsed:
            self.expand()
        else:
            self.collapse()
