#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
type="${1:-poster}"
language="${2:-roman_urdu}"
api_key="$(sed -n 's/^INTERNAL_API_KEY=//p' .env | head -n1)"
[[ -n "$api_key" ]] || { echo "INTERNAL_API_KEY is missing from .env." >&2; exit 1; }
if [[ "$type" == poster ]]; then topic="What Is an API?"; pillar="Computer Science Concepts"; audience="Beginner BS students"; else topic="Python List vs Tuple"; pillar="Python and Automation"; audience="Beginner Python learners"; fi
key="sample-$type-$(date +%s)-$RANDOM"
payload="{\"brief\":{\"content_type\":\"$type\",\"topic\":\"$topic\",\"content_pillar\":\"$pillar\",\"target_audience\":\"$audience\",\"objective\":\"Teach one clear concept\",\"language\":\"$language\",\"fact_sensitivity\":\"LOW\"},\"idempotency_key\":\"$key\"}"
curl --fail --silent --show-error http://localhost:8080/api/v1/content/generate -H "X-TBOS-API-Key: $api_key" -H 'Content-Type: application/json' -d "$payload"
echo
