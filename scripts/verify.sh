#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
docker compose config --quiet
for service in postgres n8n renderer-api; do
  container_id="$(docker compose ps -q "$service")"
  [[ -n "$container_id" ]] || { echo "Service is not running: $service" >&2; exit 1; }
  health="$(docker inspect --format '{{.State.Health.Status}}' "$container_id")"
  [[ "$health" == healthy ]] || { echo "Service is not healthy: $service ($health)" >&2; exit 1; }
done
curl --fail --silent --show-error http://localhost:8080/health/live >/dev/null
curl --fail --silent --show-error http://localhost:8080/health/ready >/dev/null
curl --fail --silent --show-error http://localhost:8080/api/v1/system/status >/dev/null
curl --fail --silent --show-error http://localhost:5678/healthz >/dev/null

# Feed SQL over stdin so database names never need nested shell quoting.
database_names="$(
  printf '%s\n' 'SELECT datname FROM pg_database;' |
    docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tA'
)"
application_database="$(docker compose exec -T postgres printenv APP_DB_NAME | tr -d '\r')"
n8n_database="$(docker compose exec -T postgres printenv N8N_DB_NAME | tr -d '\r')"
printf '%s\n' "$database_names" | grep -Fxq -- "$application_database" || {
  echo "Application database was not found." >&2
  exit 1
}
printf '%s\n' "$database_names" | grep -Fxq -- "$n8n_database" || {
  echo "n8n database was not found." >&2
  exit 1
}

docker compose exec -T renderer-api alembic -c database/alembic.ini current |
  grep -q '20260922_0001.*head'
seed_count="$(
  printf '%s\n' 'SELECT count(*) FROM system_settings;' |
    docker compose exec -T postgres sh -c 'psql -U "$APP_DB_USER" -d "$APP_DB_NAME" -tA' |
    tr -d '[:space:]'
)"
((seed_count >= 5)) || { echo "Repeatable seed data is missing." >&2; exit 1; }
echo "Phase 01 runtime verification passed."
