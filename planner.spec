# Build with: pyinstaller planner.spec

from pathlib import Path


block_cipher = None
icon_file = Path("assets/app_icon.ico")

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[
        ("C:/Users/0/miniconda3/Library/bin/sqlite3.dll", "."),
        ("C:/Users/0/miniconda3/Library/bin/libcrypto-3-x64.dll", "."),
        ("C:/Users/0/miniconda3/Library/bin/liblzma.dll", "."),
        ("C:/Users/0/miniconda3/Library/bin/libbz2.dll", "."),
    ],
    datas=[("styles/styles.qss", "styles"), ("assets", "assets")],
    hiddenimports=[
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtMultimedia",
        "PySide6.QtWidgets",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="DailyTimeBoxPlanner",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    icon=str(icon_file) if icon_file.exists() else None,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
