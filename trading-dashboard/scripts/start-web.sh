#!/usr/bin/env sh
set -eu

python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py shell -c "from django.contrib.auth import get_user_model; User = get_user_model(); username='admin'; password='admin123456'; email='admin@example.com'; User.objects.filter(username=username).exists() or User.objects.create_superuser(username, email, password)"
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 120
