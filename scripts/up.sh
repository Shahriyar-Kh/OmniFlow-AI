#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
timeout_seconds="${1:-240}"

[[ -f .env ]] || { echo "Missing .env. Run ./scripts/bootstrap.sh first." >&2; exit 1; }
if grep -q 'CHANGE_ME' .env; then
  echo "Replace every CHANGE_ME value in .env before starting the stack." >&2
  exit 1
fi
docker info >/dev/null
docker compose config --quiet
docker compose up -d --build

deadline=$((SECONDS + timeout_seconds))
services=(postgres n8n renderer-api)
while (( SECONDS < deadline )); do
  pending=()
  for service in "${services[@]}"; do
    container_id="$(docker compose ps -q "$service")"
    [[ -n "$container_id" ]] || { pending+=("$service"); continue; }
    health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id")"
    [[ "$health" == healthy ]] || pending+=("$service")
  done
  ((${#pending[@]} == 0)) && break
  sleep 3
done
if ((${#pending[@]} > 0)); then
  docker compose ps
  echo "Timed out waiting for healthy services: ${pending[*]}" >&2
  exit 1
fi
printf '%s\n' 'FastAPI: http://localhost:8080' 'API docs: http://localhost:8080/docs' 'n8n: http://localhost:5678'

