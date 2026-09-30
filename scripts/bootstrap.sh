#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

command -v git >/dev/null || { echo "git is required" >&2; exit 1; }
command -v docker >/dev/null || { echo "Docker is required" >&2; exit 1; }
docker compose version >/dev/null

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example."
else
  echo "Kept the existing .env unchanged."
fi

mkdir -p storage/{drafts,approved,published,handoff,tmp} backups n8n/{backups,workflows} \
  templates/{posters,reels} assets/{fonts,icons,music,broll}
echo "Next: edit .env, replace every CHANGE_ME value, then run ./scripts/up.sh"

