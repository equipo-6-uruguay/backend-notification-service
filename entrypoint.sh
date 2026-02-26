#!/bin/sh
set -e

echo "Running migrations..."
python manage.py migrate --noinput

echo "Starting notification consumer in background..."
# Ejecuta el consumidor como módulo para que Python resuelva paquetes correctamente
python -m notifications.messaging.consumer &

echo "Starting production server (gunicorn) on port 8001..."
exec gunicorn notification_service.wsgi:application \
    --bind 0.0.0.0:8001 \
    --workers "${GUNICORN_WORKERS:-2}" \
    --timeout "${GUNICORN_TIMEOUT:-30}" \
    --access-logfile - \
    --error-logfile -
