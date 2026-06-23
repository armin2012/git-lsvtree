from __future__ import annotations

import inspect

import pytest
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import QApplication

from git_lsvtree_ui.ui.graph_scene import GraphScene


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def qapp():
    return _app()


def test_font_utils_return_qfonts_and_css_stacks():
    _app()
    from git_lsvtree_ui.ui.font_utils import (
        choose_monospace_font,
        choose_ui_font,
        monospace_font_family_stack,
        ui_font_family_stack,
    )

    ui_font = choose_ui_font()
    mono_font = choose_monospace_font()

    assert isinstance(ui_font, QFont)
    assert isinstance(mono_font, QFont)
    assert ui_font.family()
    assert mono_font.family()
    assert "sans-serif" in ui_font_family_stack()
    assert "monospace" in monospace_font_family_stack()


def test_selected_fonts_can_render_mixed_english_and_chinese_when_available():
    _app()
    from git_lsvtree_ui.ui.font_utils import CJK_PROBE_TEXT, choose_monospace_font, choose_ui_font

    sample = f"Commit subject: {CJK_PROBE_TEXT} patient module"
    for font in (choose_ui_font(), choose_monospace_font()):
        metrics = QFontMetrics(font)
        missing = [char for char in sample if not metrics.inFontUcs4(ord(char))]
        assert missing == []


def test_graph_scene_edge_overlay_does_not_hardcode_menlo(qapp):
    from git_lsvtree_ui.ui.font_utils import choose_monospace_font

    scene = GraphScene()
    panel = scene._ensure_edge_info_item()
    text_items = [child for child in panel.childItems() if hasattr(child, "font")]

    assert text_items
    assert text_items[0].font().family() == choose_monospace_font().family()
    assert 'QFont("Menlo")' not in inspect.getsource(GraphScene._ensure_edge_info_item)
