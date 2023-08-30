#!/bin/bash
set -eo pipefail

echo "CREATE_DB_V4: $CREATE_DB_V4"
if [ "$CREATE_DB_V4" == "True" ]; then
    echo "Creating database with: postgresql://$POSTGRES_USER:$POSTGRES_PASSWORD@$SQL_HOST:$SQL_PORT/postgres "
    # Check if the database exists
    psql "postgresql://$POSTGRES_USER:$POSTGRES_PASSWORD@$SQL_HOST:$SQL_PORT/postgres" -t -c "SELECT 1 FROM pg_database WHERE datname='$POSTGRES_DB_V4'" | grep -q 1 || DATABASE_EXISTS="false"

    # If it doesn't exist, create it using Django's manage.py dbshell
    if [ "$DATABASE_EXISTS" != "true" ]; then
        echo "Database $POSTGRES_DB_V4 does not exist. Creating..."
        psql "postgresql://$POSTGRES_USER:$POSTGRES_PASSWORD@$SQL_HOST:$SQL_PORT/postgres" -c "CREATE DATABASE $POSTGRES_DB_V4;"
        echo "Database created."
    else
        echo "Database $POSTGRES_DB_V4 already exists. Skipping creation..."
    fi
else
    echo "Skipping database creation..."
fi

# Check if RUN_MIGRATIONS variable is set to "true"
echo "RUN_MIGRATIONS: $RUN_MIGRATIONS"
if [ "$RUN_MIGRATIONS" == "True" ]; then
    echo "Running migrations..."
    python manage.py makemigrations
    echo "Running migrations for users..."
    python manage.py makemigrations users
    #python manage.py makemigrations --noinput
    python manage.py migrate
    echo "Migrations complete."
else
    echo "Skipping migrations..."
fi
python manage.py init_celery # call utility to init celery
gunicorn ps_web.wsgi:application --keep-alive=300 --timeout 300 -b 0.0.0.0:8000
