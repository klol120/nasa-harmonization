#!/usr/bin/env bash
# Builds the function app package: functions/ plus the parts of backend/firecal_api the functions import.
# Output: functions/.build/ (the folder) and functions/.build.zip (what gets deployed).
set -euo pipefail
cd "$(dirname "$0")"

rm -rf .build .build.zip
mkdir -p .build/firecal_api
cp function_app.py host.json requirements.txt .build/
for f in __init__.py contract.py db.py; do cp "../backend/firecal_api/$f" ".build/firecal_api/$f"; done
cp -R ../backend/firecal_api/live .build/firecal_api/live
find .build -name __pycache__ -type d -prune -exec rm -rf {} +
(cd .build && zip -qr ../.build.zip .)
echo "built functions/.build.zip ($(du -h .build.zip | cut -f1))"
