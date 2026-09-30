[CmdletBinding()]
param([int]$TimeoutSeconds = 240)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

if (-not (Test-Path -LiteralPath '.env')) { throw 'Missing .env. Run .\scripts\bootstrap.ps1 first.' }
if (Select-String -LiteralPath '.env' -SimpleMatch 'CHANGE_ME' -Quiet) {
    throw 'Replace every CHANGE_ME value in .env before starting the stack.'
}
docker info | Out-Null
docker compose config --quiet
docker compose up -d --build

$Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$Services = @('postgres', 'n8n', 'renderer-api')
do {
    $Pending = @()
    foreach ($Service in $Services) {
        $ContainerId = docker compose ps -q $Service
        if (-not $ContainerId) { $Pending += $Service; continue }
        $Health = docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' $ContainerId
        if ($Health -ne 'healthy') { $Pending += $Service }
    }
    if ($Pending.Count -eq 0) { break }
    Start-Sleep -Seconds 3
} while ((Get-Date) -lt $Deadline)

if ($Pending.Count -gt 0) {
    docker compose ps
    throw "Timed out waiting for healthy services: $($Pending -join ', ')"
}

Write-Host 'FastAPI: http://localhost:8080'
Write-Host 'API docs: http://localhost:8080/docs'
Write-Host 'n8n: http://localhost:5678'

