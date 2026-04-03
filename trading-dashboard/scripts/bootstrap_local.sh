#!/usr/bin/env bash
set -euo pipefail

. .venv/bin/activate
python manage.py makemigrations home dashboard
python manage.py migrate
python manage.py bootstrap_site
python manage.py load_portfolio_data
python manage.py load_sample_logs
