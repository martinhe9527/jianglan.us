#!/usr/bin/env bash
set -euo pipefail
git rm -r --cached trading-dashboard/.venv trading-dashboard/db.sqlite3 2>/dev/null || true
find trading-dashboard -type d -name '__pycache__' -prune -exec git rm -r --cached {} + 2>/dev/null || true
find trading-dashboard -type f -name '*.pyc' -exec git rm --cached {} + 2>/dev/null || true
