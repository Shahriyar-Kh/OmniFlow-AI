#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
docker compose ps
for endpoint in \
  http://localhost:8080/health/live \
  http://localhost:8080/health/ready \
  http://localhost:8080/api/v1/system/status; do
  if curl --fail --silent --show-error --max-time 5 "$endpoint" >/dev/null; then
    echo "$endpoint -> reachable"
  else
    echo "$endpoint -> unavailable" >&2
  fi
done

