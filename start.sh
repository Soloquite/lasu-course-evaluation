#!/usr/bin/env bash
# Exit on error
set -o errexit

python manage.py migrate
python manage.py run_initial_seed
gunicorn config.wsgi --log-file -
