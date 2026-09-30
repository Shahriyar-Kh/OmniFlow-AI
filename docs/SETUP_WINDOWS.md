# Windows 11 setup

## 1. Prerequisites

Enable virtualization in firmware if needed. In an Administrator PowerShell, install/update WSL2, then restart when Windows requests it:

```powershell
wsl --install
wsl --update
wsl --status
```

Install Docker Desktop, select **Use the WSL 2 based engine**, and wait for the whale icon to report that Docker is running. No system installation is performed by this repository.

## 2. Open and inspect the project

Open VS Code, choose **File > Open Folder**, and select `TBOS_Automation`. In its PowerShell terminal run:

```powershell
docker --version
docker compose version
git --version
py -3.13 --version  # optional for host-side Python work; Docker is sufficient
```

## 3. Configure local secrets

```powershell
Copy-Item .env.example .env
notepad .env
```

Replace every `CHANGE_ME` password and `N8N_ENCRYPTION_KEY`. Use unique random values; the encryption key should be at least 32 random characters. Keep service names and database names unchanged for the first run. Do not add future Telegram, Meta, or R2 secrets in Phase 01.

Alternatively, `.\scripts\bootstrap.ps1` safely creates `.env` only when missing and creates local directories. It never overwrites an existing `.env`.

## 4. Validate and start

```powershell
docker compose config
.\scripts\up.ps1
# Equivalent low-level command:
docker compose up -d --build
docker compose ps
```

The first pull/build can take several minutes. Startup automatically applies Alembic migrations and repeatable seed data. To run them manually:

```powershell
docker compose exec renderer-api alembic -c database/alembic.ini upgrade head
docker compose exec renderer-api python -m database.seed.seed
```

## 5. Initialize n8n locally

Open <http://localhost:5678>. On the first visit, n8n shows its owner setup form. Create the local owner with a real email-shaped identifier and a strong password you control. The repository does not fabricate or store this login. Do not expose this HTTP-only development instance beyond your PC.

## 6. Check the API

```powershell
Invoke-RestMethod http://localhost:8080/health/live
Invoke-RestMethod http://localhost:8080/health/ready
Invoke-RestMethod http://localhost:8080/api/v1/system/status
Invoke-RestMethod http://localhost:8080/api/v1/config/public
```

Development API docs are at <http://localhost:8080/docs>. Production mode disables them.

## 7. Test and verify

```powershell
.\scripts\test.ps1
.\scripts\verify.ps1
```

The test script runs Ruff, formatting, mypy, migrations, unit tests, and real PostgreSQL integration tests inside Docker. No host Python packages are required.

## 8. Stop, restart, and back up

```powershell
.\scripts\backup.ps1
.\scripts\down.ps1
```

`down.ps1` keeps named volumes. After a PC restart, start Docker Desktop, wait until it is ready, reopen this folder, and run `.\scripts\up.ps1`. See [database documentation](DATABASE.md) for restore details.

