from __future__ import annotations

import difflib
import logging

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFontDatabase, QPainter, QTextBlockFormat, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from git_lsvtree_ui.core.diff_service import DiffResult


logger = logging.getLogger(__name__)

_COLOR_SAME = "#ffffff"
_COLOR_DELETED = "#fee2e2"
_COLOR_ADDED = "#dbeafe"

_Side = list[tuple[str, str | None]]


def _align_sides(
    old_lines: list[str], new_lines: list[str]
) -> tuple[_Side, _Side, list[tuple[int, int]]]:
    left: _Side = []
    right: _Side = []
    diff_ranges: list[tuple[int, int]] = []

    matcher = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        start = len(left)
        if tag == "equal":
            for line in old_lines[i1:i2]:
                left.append((line, _COLOR_SAME))
                right.append((line, _COLOR_SAME))
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
        if tag != "equal":
            diff_ranges.append((start, len(left)))

    return left, right, diff_ranges


def _populate(pane: QPlainTextEdit, lines: _Side) -> None:
    pane.clear()
    if not lines:
        return
    cursor = pane.textCursor()
    default_fmt = QTextBlockFormat()
    cursor.beginEditBlock()
    for i, (text, color) in enumerate(lines):
        if i > 0:
            cursor.insertBlock()
        if color:
            fmt = QTextBlockFormat()
            fmt.setBackground(QColor(color))
            cursor.mergeBlockFormat(fmt)
        else:
            cursor.mergeBlockFormat(default_fmt)
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


class DiffOverviewRuler(QWidget):
    _BG = QColor("#f8fafc")
    _MARK = QColor("#ef4444")
    _W = 12

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._total_lines = 0
        self._ranges: list[tuple[int, int]] = []
        self.setFixedWidth(self._W)

    def set_ranges(self, total_lines: int, ranges: list[tuple[int, int]]) -> None:
        self._total_lines = total_lines
        self._ranges = ranges
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(self._W, 100)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), self._BG)
        if self._total_lines <= 0 or not self._ranges:
            return
        h = self.height()
        w = self.width()
        for start, end in self._ranges:
            y1 = int(start * h / self._total_lines)
            y2 = max(y1 + 2, int(end * h / self._total_lines))
            painter.fillRect(QRect(1, y1, w - 2, y2 - y1), self._MARK)


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
        self._ruler = DiffOverviewRuler()

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

        content = QWidget()
        ch = QHBoxLayout(content)
        ch.setContentsMargins(0, 0, 0, 0)
        ch.setSpacing(0)
        ch.addWidget(splitter)
        ch.addWidget(self._ruler)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(content)

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
        left_lines, right_lines, diff_ranges = _align_sides(old_lines, new_lines)
        _populate(self._left, left_lines)
        _populate(self._right, right_lines)
        self._ruler.set_ranges(len(left_lines), diff_ranges)

    def show_error(self, message: str) -> None:
        logger.warning("diff panel show error message=%s", message)
        self._old_label.setText("Error")
        self._new_label.setText("")
        self._left.setPlainText(f"Diff failed:\n{message}")
        self._right.clear()
        self._ruler.set_ranges(0, [])

    def show_loading(self) -> None:
        logger.debug("diff panel loading")
        self._old_label.setText("Loading…")
        self._new_label.setText("")
        self._left.setPlainText("Loading diff…")
        self._right.clear()
        self._ruler.set_ranges(0, [])
