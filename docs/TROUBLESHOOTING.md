# Troubleshooting

## Docker Desktop is not running

Start Docker Desktop and wait for **Engine running**. Confirm with `docker info`. If the CLI reports permission/config access errors, close other Docker processes, check permissions on `%USERPROFILE%\.docker`, restart Docker Desktop, and retry from your normal user account.

## WSL2 problems

Run `wsl --status`, `wsl --update`, and `wsl --shutdown`, then restart Docker Desktop. Confirm Docker Desktop uses the WSL2 engine and that its WSL integration is enabled.

## Port 5678 or 8080 is already in use

Inspect listeners with `Get-NetTCPConnection -LocalPort 5678,8080`. Stop the conflicting local process or change `N8N_PORT`/`APP_PORT` in `.env`. Container ports stay 5678/8080; only the loopback host side changes.

## PostgreSQL is unhealthy

Run `docker compose ps` and `docker compose logs postgres`. Common causes are missing `.env` variables, placeholder values, or an old volume initialized with different credentials. Do not delete the volume before making a backup.

## n8n cannot connect to PostgreSQL

Check `docker compose logs n8n postgres`; ensure `N8N_DB_*` values did not change after volume initialization. The n8n database and role are created only when the PostgreSQL volume is first initialized.

## Migration or renderer database failure

Run:

```powershell
docker compose logs renderer-api
docker compose exec renderer-api alembic -c database/alembic.ini current
docker compose exec renderer-api alembic -c database/alembic.ini upgrade head
```

Confirm `DATABASE_URL` uses host `postgres`, port `5432`, the application role, and matching password. Do not expose port 5432 merely to work around container DNS.

## Ollama unavailable

This is expected in Phase 01 and does not fail readiness. Later, start native Ollama on Windows, verify `http://localhost:11434/api/tags`, and keep `OLLAMA_BASE_URL=http://host.docker.internal:11434`. Set `FEATURE_OLLAMA_ENABLED=true` only when wanted.

## Windows/WSL file permissions

Keep the workspace in a location Docker Desktop can share. Run scripts from PowerShell for the primary workflow. If Bash execution bits are lost on a Windows checkout, use `bash scripts/<name>.sh`; Docker builds explicitly set the container entrypoint executable.

## Data-preserving reset

First try `docker compose down`, restart Docker Desktop, then `.\scripts\up.ps1`. Rebuilding with `docker compose build --no-cache renderer-api` does not delete named volumes. Create `.\scripts\backup.ps1` output before any deeper reset.

## Destructive reset - manual, erases local databases and n8n state

Only after verifying a backup and accepting permanent local data loss, run `docker compose down --volumes`. Then run `.\scripts\up.ps1` to initialize empty volumes. No repository script runs this destructive command automatically.

