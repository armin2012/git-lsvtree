from __future__ import annotations

import difflib
import logging

from PySide6.QtCore import QObject, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QTextBlockFormat, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from git_lsvtree_ui.core.diff_service import DiffResult

from .font_utils import choose_monospace_font


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


class _RulerSignals(QObject):
    jumpRequested = Signal(int)


class DiffOverviewRuler(QWidget):
    _BG = QColor("#f8fafc")
    _MARK = QColor("#ef4444")
    _W = 12

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._signals = _RulerSignals()
        self.jumpRequested: Signal = self._signals.jumpRequested
        self._total_lines = 0
        self._ranges: list[tuple[int, int]] = []
        self.setFixedWidth(self._W)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

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

    def mouseDoubleClickEvent(self, event) -> None:
        if self._total_lines <= 0 or not self._ranges:
            return
        clicked_line = int(event.position().y() / self.height() * self._total_lines)
        target = self._nearest_diff_start(clicked_line)
        self._signals.jumpRequested.emit(target)

    def _nearest_diff_start(self, line: int) -> int:
        # prefer a range that contains the clicked line
        for start, end in self._ranges:
            if start <= line < end:
                return start
        # otherwise pick the range whose start is closest
        return min(self._ranges, key=lambda r: abs(r[0] - line))[0]


class DiffPanel(QWidget):
    def __init__(self):
        super().__init__()
        logger.debug("init diff panel")
        self._syncing = False
        font = choose_monospace_font()

        # ── header row (outside splitter so ruler height == pane height) ──
        self._old_label = QLabel("—")
        self._new_label = QLabel("—")
        _lbl_style = "padding: 2px 4px; background: #f1f5f9; font-weight: bold;"
        self._old_label.setStyleSheet(_lbl_style)
        self._new_label.setStyleSheet(_lbl_style)

        header_row = QWidget()
        header_row.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        hr = QHBoxLayout(header_row)
        hr.setContentsMargins(0, 0, 0, 0)
        hr.setSpacing(0)
        hr.addWidget(self._old_label, stretch=1)
        hr.addWidget(self._new_label, stretch=1)

        # ── panes ──────────────────────────────────────────────────────────
        self._left = _make_pane(font)
        self._right = _make_pane(font)
        self._ruler = DiffOverviewRuler()
        self._ruler.jumpRequested.connect(self._jump_to_line)

        self._left.verticalScrollBar().valueChanged.connect(self._sync_v_from_left)
        self._right.verticalScrollBar().valueChanged.connect(self._sync_v_from_right)
        self._left.horizontalScrollBar().valueChanged.connect(self._sync_h_from_left)
        self._right.horizontalScrollBar().valueChanged.connect(self._sync_h_from_right)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._left)
        splitter.addWidget(self._right)

        # ── content row: splitter | ruler (ruler.height == pane.height) ───
        content_row = QWidget()
        cr = QHBoxLayout(content_row)
        cr.setContentsMargins(0, 0, 0, 0)
        cr.setSpacing(0)
        cr.addWidget(splitter)
        cr.addWidget(self._ruler)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(header_row, stretch=0)
        root.addWidget(content_row, stretch=1)

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

    # ── ruler jump ─────────────────────────────────────────────────────────

    def _jump_to_line(self, line: int) -> None:
        logger.debug("diff panel jump to line=%d", line)
        self._syncing = True
        for pane in (self._left, self._right):
            block = pane.document().findBlockByLineNumber(line)
            if block.isValid():
                cursor = QTextCursor(block)
                pane.setTextCursor(cursor)
                pane.centerCursor()
        self._syncing = False

    # ── public API ─────────────────────────────────────────────────────────

    @staticmethod
    def _branch_suffix(branch: str, index: int) -> str:
        if not branch:
            return ""
        n = index if index >= 0 else "?"
        return f"  @  {branch}/{n}"

    def show_diff(self, result: DiffResult) -> None:
        logger.info("diff panel show old=%s new=%s", result.old_hash[:12], result.new_hash[:12])
        old_suffix = self._branch_suffix(result.old_branch, result.old_branch_index)
        new_suffix = self._branch_suffix(result.new_branch, result.new_branch_index)
        self._old_label.setText(f"  Old  {result.old_hash[:12]}  —  {result.rel_path}{old_suffix}")
        self._new_label.setText(f"  New  {result.new_hash[:12]}  —  {result.rel_path}{new_suffix}")
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
