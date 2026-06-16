#!/usr/bin/env bash
set -euo pipefail

# Create venv, install requirements, then run the app with venv PySide6 prioritized
python -m venv .venv
.venv/bin/python -m pip install --upgrade pip setuptools wheel
.venv/bin/python -m pip install -r requirements.txt

export DYLD_FRAMEWORK_PATH=".venv/lib/python3.12/site-packages/PySide6/Qt/lib"
export QT_PLUGIN_PATH=".venv/lib/python3.12/site-packages/PySide6/Qt/plugins"
export DYLD_LIBRARY_PATH=""

.venv/bin/python -u "$(dirname "$0")/app.py"
