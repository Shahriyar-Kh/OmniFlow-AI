#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
./scripts/verify.sh
topic_count="$(curl --fail --silent --show-error http://localhost:8080/api/v1/topics | python -c 'import json,sys; print(json.load(sys.stdin)["total"])')"
((topic_count >= 70)) || { echo "Topic library contains fewer than 70 active topics." >&2; exit 1; }
status="$(curl --silent --output /dev/null --write-out '%{http_code}' -X POST http://localhost:8080/api/v1/plans/weekly -H 'Content-Type: application/json' -d '{"week_start":"2026-09-21"}')"
[[ "$status" == 401 ]] || { echo "Mutation endpoint did not reject a missing key." >&2; exit 1; }
prompt_count="$(printf '%s\n' 'SELECT count(*) FROM prompt_templates WHERE is_active = true;' | docker compose exec -T postgres sh -c 'psql -U "$APP_DB_USER" -d "$APP_DB_NAME" -tA' | tr -d '[:space:]')"
((prompt_count >= 7)) || { echo "Seven active prompt templates were not synchronized." >&2; exit 1; }
curl --fail --silent --show-error http://localhost:8080/api/v1/ai/status >/dev/null
echo "Phase 02 implementation verification passed."
