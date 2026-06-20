from __future__ import annotations

import logging

from PySide6.QtWidgets import QStatusBar


logger = logging.getLogger(__name__)


class GitLsvtreeStatusBar(QStatusBar):
    def __init__(self):
        super().__init__()
        logger.debug("init git-lsvtree status bar")
        self.current_file = ""
        self.mode = ""

    def set_loaded(
        self,
        file_path,
        mode: str,
        version_count: int,
        branch_count: int,
        zoom: float,
        warning: str = "",
    ) -> None:
        logger.info(
            "status bar set loaded file=%s mode=%s versions=%d branches=%d zoom=%s warning=%r",
            file_path,
            mode,
            version_count,
            branch_count,
            zoom,
            warning,
        )
        self.current_file = str(file_path)
        self.mode = mode
        msg = f"{self.current_file} | mode={mode} | versions={version_count} | branches={branch_count} | zoom={zoom:.0%}"
        if warning:
            msg += f" | ⚠ {warning}"
        self.showMessage(msg)
