#!/usr/bin/env bash
# Exit on error
set -o errexit

python manage.py migrate
python manage.py run_initial_seed

if [ "$POPULATE_DEMO_DATA" = "true" ]; then
    python manage.py populate_demo_data
fi

gunicorn config.wsgi --bind 0.0.0.0:$PORT --log-file -
