#!/usr/bin/env bash
set -euo pipefail
. .venv/bin/activate
python manage.py migrate
python manage.py load_portfolio_data
