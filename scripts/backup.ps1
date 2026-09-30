[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
$Timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$Destination = Join-Path $ProjectRoot "backups/$Timestamp"
New-Item -ItemType Directory -Path $Destination | Out-Null

$PostgresId = docker compose ps -q postgres
$N8nId = docker compose ps -q n8n
if (-not $PostgresId -or -not $N8nId) { throw 'PostgreSQL and n8n must be running.' }

docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$APP_DB_NAME" -Fc -f /tmp/tbos-app.dump'
docker cp "${PostgresId}:/tmp/tbos-app.dump" (Join-Path $Destination 'tbos-app.dump')
docker compose exec -T postgres rm -f /tmp/tbos-app.dump

docker compose exec -T n8n sh -c 'tar -czf /tmp/n8n-data.tar.gz -C "$N8N_USER_FOLDER" .'
docker cp "${N8nId}:/tmp/n8n-data.tar.gz" (Join-Path $Destination 'n8n-data.tar.gz')
docker compose exec -T n8n rm -f /tmp/n8n-data.tar.gz

foreach ($FileName in @('tbos-app.dump', 'n8n-data.tar.gz')) {
    $File = Get-Item -LiteralPath (Join-Path $Destination $FileName)
    if ($File.Length -le 0) { throw "Backup file is empty: $FileName" }
}
Write-Host "Verified backup created at $Destination. Treat it as sensitive data."

