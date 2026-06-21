from __future__ import annotations

import logging
from datetime import datetime
from html import escape

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
        author_date = datetime.fromtimestamp(vnode.author_time).strftime("%Y-%m-%d %H:%M:%S")
        commit_date = datetime.fromtimestamp(vnode.commit_time).strftime("%Y-%m-%d %H:%M:%S")
        parents = []
        if vnode.main_parent:
            parents.append(vnode.main_parent[:12])
        parents.extend(mp.hash[:12] for mp in vnode.merge_parents)
        committer = self._person(vnode.committer_name, vnode.committer_email)
        if not committer:
            committer = self._person(vnode.author_name, vnode.author_email)
        tags = ", ".join(vnode.tags) if vnode.tags else "none"
        parent_text = ", ".join(parents) if parents else "none"
        description = vnode.description.strip() or "No description."
        logger.debug("detail panel show version id=%s", source[:12])
        self.setHtml(
            f"""
            <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                        color: #111827; font-size: 13px;">
              <h2 style="margin: 0 0 4px 0; font-size: 18px; font-weight: 700;">
                {escape(vnode.subject or "(no subject)")}
              </h2>
              <div style="color: #6b7280; margin-bottom: 12px;">
                {escape(vnode.hash[:12])} · {escape(vnode.reconstructed_branch or "unknown branch")}
              </div>

              {self._section("Identity", (
                  ("Hash", vnode.hash),
                  ("Branch", vnode.reconstructed_branch or "unknown"),
                  ("Tags", tags),
                  ("Parents", parent_text),
              ))}

              {self._section("People & Time", (
                  ("Author", self._person(vnode.author_name, vnode.author_email)),
                  ("Author date", author_date),
                  ("Committer", committer),
                  ("Commit date", commit_date),
              ))}

              <div style="margin-top: 14px;">
                <div style="font-weight: 700; color: #374151; margin-bottom: 6px;">Description</div>
                <pre style="white-space: pre-wrap; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
                            background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 6px;
                            padding: 8px; margin: 0;">{escape(description)}</pre>
              </div>
            </div>
            """
        )

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

    @staticmethod
    def _person(name: str, email: str) -> str:
        name = name.strip()
        email = email.strip()
        if name and email:
            return f"{name} <{email}>"
        return name or email

    @staticmethod
    def _section(title: str, rows: tuple[tuple[str, str], ...]) -> str:
        rendered_rows = "\n".join(
            (
                "<tr>"
                f"<td style='color: #6b7280; width: 86px; padding: 3px 10px 3px 0; vertical-align: top;'>{escape(label)}</td>"
                f"<td style='color: #111827; padding: 3px 0; word-break: break-word;'>{escape(value)}</td>"
                "</tr>"
            )
            for label, value in rows
        )
        return (
            "<div style='margin-top: 12px;'>"
            f"<div style='font-weight: 700; color: #374151; margin-bottom: 4px;'>{escape(title)}</div>"
            "<table style='border-collapse: collapse; width: 100%;'>"
            f"{rendered_rows}"
            "</table>"
            "</div>"
        )
