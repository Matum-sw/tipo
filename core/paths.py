import os
import sys
from pathlib import Path


APP_NAME = "tipo"

if getattr(sys, "frozen", False):
    ROOT_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    USER_DIR = Path.home() / ".daily_time_box_planner"
else:
    ROOT_DIR = Path(__file__).resolve().parents[1]
    USER_DIR = ROOT_DIR

DATA_DIR = Path(os.getenv("TIMEBOX_DATA_DIR", USER_DIR / "data"))
REPORT_DIR = Path(os.getenv("TIMEBOX_REPORT_DIR", USER_DIR / "reports"))
ASSET_DIR = ROOT_DIR / "assets"
STYLE_FILE = ROOT_DIR / "styles" / "styles.qss"
APP_ICON_FILES = (
    ASSET_DIR / "app_icon.ico",
    ASSET_DIR / "app_icon.png",
    ASSET_DIR / "app_icon.icns",
    ASSET_DIR / "app_icon.jpg",
    ASSET_DIR / "app_icon.jpeg",
    ASSET_DIR / "아이콘.png",
)
DB_FILE = DATA_DIR / "planner.sqlite3"
