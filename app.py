import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from core.paths import APP_NAME, STYLE_FILE
from database.sqlite_store import SQLiteStore
from ui.main_window import MainWindow


def load_stylesheet() -> str:
    if STYLE_FILE.exists():
        return STYLE_FILE.read_text(encoding="utf-8")
    return ""


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    app.setStyleSheet(load_stylesheet())

    store = SQLiteStore()
    window = MainWindow(store)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
