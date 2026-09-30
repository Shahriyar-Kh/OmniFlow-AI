#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
model="$(sed -n 's/^OLLAMA_MODEL=//p' .env | head -n1)"
model="${model:-qwen3:4b}"
curl --fail --silent --show-error http://localhost:11434/api/tags |
  grep -Fq "\"name\":\"$model\"" || { echo "Selected model is unavailable: $model" >&2; exit 1; }
curl --fail --silent --show-error http://localhost:11434/api/generate \
  -H 'Content-Type: application/json' \
  -d "{\"model\":\"$model\",\"prompt\":\"Reply with only OK\",\"stream\":false}" >/dev/null
response="$(curl --fail --silent --show-error http://localhost:11434/api/generate \
  -H 'Content-Type: application/json' \
  -d "{\"model\":\"$model\",\"prompt\":\"Return strict JSON with concept API and a Roman Urdu explanation\",\"stream\":false,\"format\":\"json\"}")"
printf '%s' "$response" | grep -Fq 'response' || { echo "Structured generation failed." >&2; exit 1; }
docker compose exec -T renderer-api python -c "import urllib.request; urllib.request.urlopen('http://host.docker.internal:11434/api/tags', timeout=5)"
echo "Ollama live checks passed for $model."
