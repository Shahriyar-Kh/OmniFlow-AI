#!/usr/bin/env sh
set -eu

alembic -c database/alembic.ini upgrade head
python -m database.seed.seed
exec uvicorn tbos_renderer.main:create_app --factory --host "${APP_HOST:-0.0.0.0}" --port "${APP_PORT:-8080}"

