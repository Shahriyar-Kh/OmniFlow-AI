#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
week_start="${1:-$(date -d 'monday this week' +%F)}"
api_key="$(sed -n 's/^INTERNAL_API_KEY=//p' .env | head -n1)"
[[ -n "$api_key" ]] || { echo "INTERNAL_API_KEY is missing from .env." >&2; exit 1; }
curl --fail --silent --show-error http://localhost:8080/api/v1/plans/weekly -H "X-TBOS-API-Key: $api_key" -H 'Content-Type: application/json' -d "{\"week_start\":\"$week_start\",\"language\":\"roman_urdu\"}"
echo
