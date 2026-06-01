import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from core.paths import APP_ICON_FILES, APP_NAME, STYLE_FILE
from database.sqlite_store import SQLiteStore
from ui.main_window import MainWindow


def load_stylesheet() -> str:
    if STYLE_FILE.exists():
        return STYLE_FILE.read_text(encoding="utf-8")
    return ""


def load_app_icon() -> QIcon:
    for icon_file in APP_ICON_FILES:
        if icon_file.exists():
            return QIcon(str(icon_file))
    return QIcon()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    app.setStyleSheet(load_stylesheet())
    app_icon = load_app_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)

    store = SQLiteStore()
    window = MainWindow(store)
    if not app_icon.isNull():
        window.setWindowIcon(app_icon)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
