#!/bin/bash
set -e
FIRST_RUN_LOG=.first_log

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

uv sync
uv run manage.py collectstatic --noinput

until (PGPASSWORD=postgres psql -h "postgres" -U "postgres" -c '\q') 2> /dev/null; do
  >&2 echo "waiting for postgres"
  sleep 1
done

uv run manage.py makemigrations --noinput
uv run manage.py migrate


if [ ! -f "$SCRIPT_DIR/$FIRST_RUN_LOG" ]; then
    echo "Creating filler data..."
    mkdir -p /home/tjctgrader/autograder/media/problem_testcases
    cp /home/tjctgrader/autograder/dev/example_testcases.zip /home/tjctgrader/autograder/media/problem_testcases
    cp "$SCRIPT_DIR/filler_data.py" $PROJECT_ROOT
    uv run filler_data.py
    rm -rf filler_data.py
    DJANGO_SUPERUSER_PASSWORD=123 uv run manage.py createsuperuser --noinput --username=admin --email=admin@admin.com
    touch "$SCRIPT_DIR/$FIRST_RUN_LOG"
fi

while true
do
    uv run manage.py runserver 0.0.0.0:3000
    sleep 1
done
