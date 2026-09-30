[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
docker compose config --quiet
docker compose build renderer-api
docker compose run --rm --no-deps renderer-api python -m ruff check .
docker compose run --rm --no-deps renderer-api python -m ruff format --check .
docker compose run --rm --no-deps renderer-api python -m mypy apps/renderer/src
docker compose up -d postgres
docker compose run --rm renderer-api alembic -c database/alembic.ini upgrade head
docker compose run --rm -e RUN_DB_TESTS=1 renderer-api python -m pytest

