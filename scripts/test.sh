#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
docker compose config --quiet
docker compose build renderer-api
docker compose run --rm --no-deps renderer-api python -m ruff check .
docker compose run --rm --no-deps renderer-api python -m ruff format --check .
docker compose run --rm --no-deps renderer-api python -m mypy apps/renderer/src
docker compose up -d postgres
docker compose run --rm renderer-api alembic -c database/alembic.ini upgrade head
docker compose run --rm -e RUN_DB_TESTS=1 renderer-api python -m pytest

