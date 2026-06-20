from __future__ import annotations

import logging
from datetime import datetime

from PySide6.QtWidgets import QTextEdit

from git_lsvtree_ui.core.graph_model import GraphModel, VersionNode
from git_lsvtree_ui.layout.tree_layout import LayoutNode


logger = logging.getLogger(__name__)


class DetailPanel(QTextEdit):
    def __init__(self):
        super().__init__()
        logger.debug("init detail panel")
        self.setReadOnly(True)
        self.setPlainText("No version selected.")

    def show_version(self, layout_node: LayoutNode, graph: GraphModel) -> None:
        source = layout_node.source_hashes[0]
        vnode: VersionNode | None = graph.nodes.get(source)
        if vnode is None:
            logger.warning("detail panel node not found in graph id=%s", source)
            self.setPlainText(f"Node: {source}\n(no graph data)")
            return
        date = datetime.fromtimestamp(vnode.author_time).strftime("%Y-%m-%d %H:%M:%S")
        parents = []
        if vnode.main_parent:
            parents.append(vnode.main_parent[:12])
        parents.extend(mp.hash[:12] for mp in vnode.merge_parents)
        lines = [
            f"hash:    {vnode.hash}",
            f"branch:  {vnode.reconstructed_branch}",
            f"date:    {date}",
            f"author:  {vnode.author_name} <{vnode.author_email}>",
            f"subject: {vnode.subject}",
        ]
        if vnode.tags:
            lines.append(f"tags:    {', '.join(vnode.tags)}")
        if parents:
            lines.append(f"parents: {', '.join(parents)}")
        logger.debug("detail panel show version id=%s", source[:12])
        self.setPlainText("\n".join(lines))

    def show_run(self, layout_node: LayoutNode) -> None:
        lines = [
            f"Collapsed run: {layout_node.id}",
            f"branch:  {layout_node.branch}",
            f"versions: {len(layout_node.source_hashes)}",
            "",
            *layout_node.source_hashes,
        ]
        logger.debug("detail panel show run id=%s count=%d", layout_node.id, len(layout_node.source_hashes))
        self.setPlainText("\n".join(lines))

    def clear_selection(self) -> None:
        logger.debug("detail panel cleared")
        self.setPlainText("No version selected.")
