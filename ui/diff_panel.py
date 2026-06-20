from __future__ import annotations

import difflib
import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFontDatabase, QTextBlockFormat, QTextCursor
from PySide6.QtWidgets import (
    QLabel,
    QPlainTextEdit,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from git_lsvtree_ui.core.diff_service import DiffResult


logger = logging.getLogger(__name__)

_COLOR_DELETED = "#fee2e2"
_COLOR_ADDED = "#dcfce7"

_Side = list[tuple[str, str | None]]


def _align_sides(old_lines: list[str], new_lines: list[str]) -> tuple[_Side, _Side]:
    left: _Side = []
    right: _Side = []
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for line in old_lines[i1:i2]:
                left.append((line, None))
                right.append((line, None))
        elif tag == "replace":
            ob, nb = old_lines[i1:i2], new_lines[j1:j2]
            for k in range(max(len(ob), len(nb))):
                left.append((ob[k] if k < len(ob) else "", _COLOR_DELETED if k < len(ob) else None))
                right.append((nb[k] if k < len(nb) else "", _COLOR_ADDED if k < len(nb) else None))
        elif tag == "delete":
            for line in old_lines[i1:i2]:
                left.append((line, _COLOR_DELETED))
                right.append(("", None))
        else:  # insert
            for line in new_lines[j1:j2]:
                left.append(("", None))
                right.append((line, _COLOR_ADDED))
    return left, right


def _populate(pane: QPlainTextEdit, lines: _Side) -> None:
    pane.clear()
    if not lines:
        return
    cursor = pane.textCursor()
    cursor.beginEditBlock()
    for i, (text, color) in enumerate(lines):
        if i > 0:
            cursor.insertBlock()
        if color:
            fmt = QTextBlockFormat()
            fmt.setBackground(QColor(color))
            cursor.mergeBlockFormat(fmt)
        cursor.insertText(text)
    cursor.endEditBlock()
    pane.moveCursor(QTextCursor.MoveOperation.Start)


def _make_pane(font) -> QPlainTextEdit:
    pane = QPlainTextEdit()
    pane.setReadOnly(True)
    pane.setFont(font)
    pane.setUndoRedoEnabled(False)
    pane.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
    return pane


class DiffPanel(QWidget):
    def __init__(self):
        super().__init__()
        logger.debug("init diff panel")
        self._syncing = False
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)

        self._old_label = QLabel("—")
        self._new_label = QLabel("—")
        for lbl in (self._old_label, self._new_label):
            lbl.setStyleSheet("padding: 2px 4px; background: #f1f5f9; font-weight: bold;")

        self._left = _make_pane(font)
        self._right = _make_pane(font)

        self._left.verticalScrollBar().valueChanged.connect(self._sync_v_from_left)
        self._right.verticalScrollBar().valueChanged.connect(self._sync_v_from_right)
        self._left.horizontalScrollBar().valueChanged.connect(self._sync_h_from_left)
        self._right.horizontalScrollBar().valueChanged.connect(self._sync_h_from_right)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        left_w = QWidget()
        lv = QVBoxLayout(left_w)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(0)
        lv.addWidget(self._old_label)
        lv.addWidget(self._left)

        right_w = QWidget()
        rv = QVBoxLayout(right_w)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)
        rv.addWidget(self._new_label)
        rv.addWidget(self._right)

        splitter.addWidget(left_w)
        splitter.addWidget(right_w)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(splitter)

    # ── scroll sync ────────────────────────────────────────────────────────

    def _sync_v_from_left(self, value: int) -> None:
        if self._syncing:
            return
        self._syncing = True
        self._right.verticalScrollBar().setValue(value)
        self._syncing = False

    def _sync_v_from_right(self, value: int) -> None:
        if self._syncing:
            return
        self._syncing = True
        self._left.verticalScrollBar().setValue(value)
        self._syncing = False

    def _sync_h_from_left(self, value: int) -> None:
        if self._syncing:
            return
        self._syncing = True
        self._right.horizontalScrollBar().setValue(value)
        self._syncing = False

    def _sync_h_from_right(self, value: int) -> None:
        if self._syncing:
            return
        self._syncing = True
        self._left.horizontalScrollBar().setValue(value)
        self._syncing = False

    # ── public API ─────────────────────────────────────────────────────────

    def show_diff(self, result: DiffResult) -> None:
        logger.info("diff panel show old=%s new=%s", result.old_hash[:12], result.new_hash[:12])
        self._old_label.setText(f"  Old  {result.old_hash[:12]}  —  {result.rel_path}")
        self._new_label.setText(f"  New  {result.new_hash[:12]}  —  {result.rel_path}")
        old_lines = result.old_content.splitlines()
        new_lines = result.new_content.splitlines()
        left_lines, right_lines = _align_sides(old_lines, new_lines)
        _populate(self._left, left_lines)
        _populate(self._right, right_lines)

    def show_error(self, message: str) -> None:
        logger.warning("diff panel show error message=%s", message)
        self._old_label.setText("Error")
        self._new_label.setText("")
        self._left.setPlainText(f"Diff failed:\n{message}")
        self._right.clear()

    def show_loading(self) -> None:
        logger.debug("diff panel loading")
        self._old_label.setText("Loading…")
        self._new_label.setText("")
        self._left.setPlainText("Loading diff…")
        self._right.clear()
