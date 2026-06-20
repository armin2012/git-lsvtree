from __future__ import annotations

import logging

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QPlainTextEdit

from git_lsvtree_ui.core.diff_service import DiffResult


logger = logging.getLogger(__name__)


class DiffPanel(QPlainTextEdit):
    def __init__(self):
        super().__init__()
        logger.debug("init diff panel")
        self.setReadOnly(True)
        self.setPlainText("")
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        self.setFont(font)

    def show_diff(self, result: DiffResult) -> None:
        logger.info(
            "diff panel show old=%s new=%s bytes=%d",
            result.old_hash[:12],
            result.new_hash[:12],
            len(result.text),
        )
        header = f"--- {result.old_hash[:12]}:{result.rel_path}\n+++ {result.new_hash[:12]}:{result.rel_path}\n\n"
        self.setPlainText(header + result.text)

    def show_error(self, message: str) -> None:
        logger.warning("diff panel show error message=%s", message)
        self.setPlainText(f"Diff failed:\n{message}")

    def show_loading(self) -> None:
        logger.debug("diff panel loading")
        self.setPlainText("Loading diff…")
