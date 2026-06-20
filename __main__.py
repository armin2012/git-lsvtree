from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication

from git_lsvtree_ui.app.main_window import MainWindow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(1280, 800)
    window.show()
    if len(sys.argv) > 1:
        from pathlib import Path
        window.load_file(Path(sys.argv[1]))
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
