from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QAbstractItemView, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from git_lsvtree_ui.core.project_tree import ProjectTree, ProjectTreeNode


logger = logging.getLogger(__name__)

_ROLE_KIND = 32
_ROLE_REL_PATH = 33


class ProjectNavigator(QWidget):
    fileSelected = Signal(Path)

    def __init__(self):
        super().__init__()
        logger.debug("init project navigator")
        self.project_tree: ProjectTree | None = None
        self.selected_project_file: str | None = None
        self._expanded_dirs: set[str] = set()
        self._item_by_rel_path: dict[str, QTreeWidgetItem] = {}

        self.tree_widget = QTreeWidget(self)
        self.tree_widget.setHeaderHidden(True)
        self.tree_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree_widget.itemClicked.connect(self.activate_item)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tree_widget)

    def set_project_tree(self, tree: ProjectTree) -> None:
        logger.info(
            "set project tree repo_root=%s tracked_files=%d",
            tree.repo_root,
            tree.tracked_file_count,
        )
        previous_expanded = set(self._expanded_dirs)
        previous_selected = self.selected_project_file
        self.project_tree = tree
        self.tree_widget.clear()
        self._item_by_rel_path = {}

        for child in tree.root.children:
            self.tree_widget.addTopLevelItem(self._make_item(child))

        self.restore_expanded_dirs(previous_expanded)
        if previous_selected:
            self.set_selected_file(previous_selected)

    def activate_item(self, item: QTreeWidgetItem, _column: int = 0) -> None:
        kind = item.data(0, _ROLE_KIND)
        rel_path = item.data(0, _ROLE_REL_PATH)
        logger.debug("project navigator item activated kind=%s rel_path=%s", kind, rel_path)
        if kind == "directory":
            self.toggle_directory_item(item)
            return
        if kind != "file" or self.project_tree is None:
            return
        self.selected_project_file = rel_path
        self.tree_widget.setCurrentItem(item)
        selected = self.project_tree.repo_root / rel_path
        logger.info("project navigator file selected path=%s", selected)
        self.fileSelected.emit(selected)

    def toggle_directory_item(self, item: QTreeWidgetItem) -> None:
        if item.data(0, _ROLE_KIND) != "directory":
            return
        rel_path = item.data(0, _ROLE_REL_PATH)
        expanded = not item.isExpanded()
        item.setExpanded(expanded)
        if expanded:
            self._expanded_dirs.add(rel_path)
        else:
            self._expanded_dirs.discard(rel_path)
        self._update_directory_item_text(item)
        logger.debug("project directory toggled rel_path=%s expanded=%s", rel_path, expanded)

    def expanded_dirs(self) -> set[str]:
        return set(self._expanded_dirs)

    def restore_expanded_dirs(self, dirs: set[str]) -> None:
        self._expanded_dirs = set()
        for rel_path, item in self._item_by_rel_path.items():
            if item.data(0, _ROLE_KIND) != "directory":
                continue
            expanded = rel_path in dirs
            item.setExpanded(expanded)
            if expanded:
                self._expanded_dirs.add(rel_path)
            self._update_directory_item_text(item)
        logger.debug("project navigator expanded dirs restored count=%d", len(self._expanded_dirs))

    def set_selected_file(self, rel_path: str | None) -> None:
        self.selected_project_file = rel_path
        if rel_path is None:
            self.tree_widget.setCurrentItem(None)
            return
        item = self._item_by_rel_path.get(rel_path)
        if item is None:
            logger.debug("selected project file not visible rel_path=%s", rel_path)
            return
        self.tree_widget.setCurrentItem(item)
        logger.debug("project navigator selected file marked rel_path=%s", rel_path)

    def _make_item(self, node: ProjectTreeNode) -> QTreeWidgetItem:
        item = QTreeWidgetItem()
        item.setData(0, _ROLE_KIND, node.kind)
        item.setData(0, _ROLE_REL_PATH, node.rel_path)
        self._item_by_rel_path[node.rel_path] = item
        if node.kind == "directory":
            item.setText(0, f"+ {node.name}")
            for child in node.children:
                item.addChild(self._make_item(child))
        else:
            item.setText(0, f"  {node.name}")
        return item

    def _update_directory_item_text(self, item: QTreeWidgetItem) -> None:
        rel_path = item.data(0, _ROLE_REL_PATH)
        name = Path(rel_path).name if rel_path else ""
        prefix = "-" if item.isExpanded() else "+"
        item.setText(0, f"{prefix} {name}")
