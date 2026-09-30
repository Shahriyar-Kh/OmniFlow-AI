#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
timestamp="$(date +%Y%m%d-%H%M%S)"
destination="$project_root/backups/$timestamp"
mkdir -p "$destination"

postgres_id="$(docker compose ps -q postgres)"
n8n_id="$(docker compose ps -q n8n)"
[[ -n "$postgres_id" && -n "$n8n_id" ]] || { echo "PostgreSQL and n8n must be running." >&2; exit 1; }
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$APP_DB_NAME" -Fc -f /tmp/tbos-app.dump'
docker cp "$postgres_id:/tmp/tbos-app.dump" "$destination/tbos-app.dump"
docker compose exec -T postgres rm -f /tmp/tbos-app.dump
docker compose exec -T n8n sh -c 'tar -czf /tmp/n8n-data.tar.gz -C "$N8N_USER_FOLDER" .'
docker cp "$n8n_id:/tmp/n8n-data.tar.gz" "$destination/n8n-data.tar.gz"
docker compose exec -T n8n rm -f /tmp/n8n-data.tar.gz
[[ -s "$destination/tbos-app.dump" && -s "$destination/n8n-data.tar.gz" ]] || { echo "Backup validation failed." >&2; exit 1; }
echo "Verified backup created at $destination. Treat it as sensitive data."

