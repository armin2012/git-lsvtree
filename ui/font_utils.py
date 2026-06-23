from __future__ import annotations

import logging
from functools import lru_cache

from PySide6.QtGui import QFont, QFontDatabase, QFontMetrics
from PySide6.QtWidgets import QApplication


logger = logging.getLogger(__name__)

CJK_PROBE_TEXT = "中文测试【图像查看】患者模块"
ASCII_PROBE_TEXT = "Git version tree 0123456789"

_UI_FONT_CANDIDATES = (
    "PingFang SC",
    "Heiti SC",
    "Hiragino Sans GB",
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "SimSun",
    "Noto Sans CJK SC",
    "WenQuanYi Micro Hei",
)

_MONOSPACE_FONT_CANDIDATES = (
    "Noto Sans Mono CJK SC",
    "Sarasa Mono SC",
    "Microsoft YaHei Mono",
    "Cascadia Mono",
    "Consolas",
    "Menlo",
    "Monaco",
    "DejaVu Sans Mono",
)

_warned_no_cjk_font = False


def choose_ui_font(point_size: int = 10) -> QFont:
    logger.debug("choose ui font point_size=%d", point_size)
    family = _choose_font_family(_UI_FONT_CANDIDATES, require_fixed_pitch=False)
    if family:
        return QFont(family, point_size)
    _warn_no_cjk_font_once()
    font = QApplication.font() if QApplication.instance() is not None else QFont()
    font.setPointSize(point_size)
    return font


def choose_monospace_font(point_size: int = 10) -> QFont:
    logger.debug("choose monospace font point_size=%d", point_size)
    family = _choose_font_family(_MONOSPACE_FONT_CANDIDATES, require_fixed_pitch=True)
    if family:
        font = QFont(family, point_size)
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setFixedPitch(True)
        return font

    family = _choose_font_family(_UI_FONT_CANDIDATES, require_fixed_pitch=False)
    if family:
        font = QFont(family, point_size)
        font.setStyleHint(QFont.StyleHint.Monospace)
        return font

    _warn_no_cjk_font_once()
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    font.setPointSize(point_size)
    return font


def ui_font_family_stack() -> str:
    return _css_stack((*_UI_FONT_CANDIDATES, "sans-serif"))


def monospace_font_family_stack() -> str:
    return _css_stack((*_MONOSPACE_FONT_CANDIDATES, *_UI_FONT_CANDIDATES, "monospace"))


def font_supports_text(font: QFont, text: str) -> bool:
    metrics = QFontMetrics(font)
    return all(metrics.inFontUcs4(ord(char)) for char in text)


@lru_cache(maxsize=32)
def _choose_font_family(candidates: tuple[str, ...], require_fixed_pitch: bool) -> str:
    installed = set(QFontDatabase.families())
    probe = f"{ASCII_PROBE_TEXT} {CJK_PROBE_TEXT}"
    for family in candidates:
        if family not in installed:
            continue
        font = QFont(family)
        if require_fixed_pitch:
            font.setStyleHint(QFont.StyleHint.Monospace)
        if font_supports_text(font, probe):
            logger.info("selected font family=%s fixed_pitch=%s", family, require_fixed_pitch)
            return family
    logger.debug("no matching font family found fixed_pitch=%s", require_fixed_pitch)
    return ""


def _css_stack(families: tuple[str, ...]) -> str:
    rendered = []
    for family in families:
        if family in ("sans-serif", "monospace"):
            rendered.append(family)
        else:
            rendered.append(f"'{family}'")
    return ", ".join(rendered)


def _warn_no_cjk_font_once() -> None:
    global _warned_no_cjk_font
    if _warned_no_cjk_font:
        return
    _warned_no_cjk_font = True
    logger.warning(
        "no CJK-capable UI font detected; Chinese text may render as square boxes. "
        "Install a CJK font such as Noto Sans CJK SC."
    )
