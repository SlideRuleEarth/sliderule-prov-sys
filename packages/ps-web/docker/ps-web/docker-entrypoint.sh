#!/bin/bash
set -eo pipefail
# Check if RUN_MIGRATIONS variable is set to "true"
if [ "$RUN_MIGRATIONS" == "true" ]; then
    echo "Running migrations..."
    python manage.py makemigrations users
    python manage.py makemigrations
    #python manage.py makemigrations --noinput
    python manage.py migrate
else
    echo "Skipping migrations..."
fi
python manage.py init_celery # call utility to init celery
python manage.py get_ps_server_versions
gunicorn ps_web.wsgi:application --keep-alive=300 --timeout 300 -b 0.0.0.0:8000
