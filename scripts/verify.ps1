[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

docker compose config --quiet
$ExpectedServices = @('postgres', 'n8n', 'renderer-api')
foreach ($Service in $ExpectedServices) {
    $ContainerId = docker compose ps -q $Service
    if (-not $ContainerId) { throw "Service is not running: $Service" }
    $Health = docker inspect --format '{{.State.Health.Status}}' $ContainerId
    if ($Health -ne 'healthy') { throw "Service is not healthy: $Service ($Health)" }
}

$Live = Invoke-RestMethod -Uri 'http://localhost:8080/health/live' -TimeoutSec 5
if ($Live.status -ne 'alive') { throw 'Liveness response was invalid.' }
$Ready = Invoke-RestMethod -Uri 'http://localhost:8080/health/ready' -TimeoutSec 5
if ($Ready.status -ne 'ready' -or $Ready.database.status -ne 'ok') { throw 'Readiness response was invalid.' }
$Status = Invoke-RestMethod -Uri 'http://localhost:8080/api/v1/system/status' -TimeoutSec 5
if (-not $Status.version) { throw 'System status response was invalid.' }
Invoke-WebRequest -Uri 'http://localhost:5678/healthz' -UseBasicParsing -TimeoutSec 5 | Out-Null

# Feed SQL over stdin to avoid PowerShell's native-argument quote rewriting on Windows.
$DatabaseNames = 'SELECT datname FROM pg_database;' |
    docker compose exec -T postgres sh -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB -tA'
if ($LASTEXITCODE -ne 0) { throw 'Could not query PostgreSQL databases.' }
$ExpectedApplicationDatabase = docker compose exec -T postgres printenv APP_DB_NAME
$ExpectedN8nDatabase = docker compose exec -T postgres printenv N8N_DB_NAME
if (
    $DatabaseNames -notcontains $ExpectedApplicationDatabase.Trim() -or
    $DatabaseNames -notcontains $ExpectedN8nDatabase.Trim()
) {
    throw 'Expected application and n8n databases were not both found.'
}

$MigrationState = docker compose exec -T renderer-api alembic -c database/alembic.ini current
if ($MigrationState -notmatch '20260922_0001.*head') { throw 'Alembic is not at the latest revision.' }

$SeedCount = 'SELECT count(*) FROM system_settings;' |
    docker compose exec -T postgres sh -c 'psql -U $APP_DB_USER -d $APP_DB_NAME -tA'
if ($LASTEXITCODE -ne 0) { throw 'Could not query repeatable seed data.' }
if ([int]$SeedCount.Trim() -lt 5) { throw 'Repeatable seed data is missing.' }

Write-Host 'Phase 01 runtime verification passed.'
