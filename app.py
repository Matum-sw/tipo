import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from core.paths import APP_ICON_FILES, APP_NAME, ROOT_DIR, STYLE_FILE
from database.sqlite_store import SQLiteStore
from ui.main_window import MainWindow


def load_stylesheet(store: SQLiteStore) -> str:
    dark_mode = store.get_setting("dark_mode", "0") == "1"
    dark_file = ROOT_DIR / "styles" / "dark.qss"
    qss_file = dark_file if dark_mode and dark_file.exists() else STYLE_FILE
    if qss_file.exists():
        return qss_file.read_text(encoding="utf-8")
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

    store = SQLiteStore()
    app.setStyleSheet(load_stylesheet(store))

    app_icon = load_app_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)

    window = MainWindow(store)
    if not app_icon.isNull():
        window.setWindowIcon(app_icon)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
