[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

foreach ($CommandName in @('git', 'docker')) {
    if (-not (Get-Command $CommandName -ErrorAction SilentlyContinue)) {
        throw "Required command '$CommandName' was not found. See docs/SETUP_WINDOWS.md."
    }
}

docker compose version | Out-Null
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    Write-Warning 'The Python launcher is not installed. Docker can run all Phase 01 checks; host Python is optional.'
}

$EnvironmentFile = Join-Path $ProjectRoot '.env'
if (-not (Test-Path -LiteralPath $EnvironmentFile)) {
    Copy-Item -LiteralPath (Join-Path $ProjectRoot '.env.example') -Destination $EnvironmentFile
    Write-Host 'Created .env from .env.example. Existing files are never overwritten.'
} else {
    Write-Host 'Kept the existing .env unchanged.'
}

$Directories = @(
    'storage/drafts', 'storage/approved', 'storage/published', 'storage/handoff',
    'storage/tmp', 'backups', 'n8n/backups', 'n8n/workflows', 'templates/posters',
    'templates/reels', 'assets/fonts', 'assets/icons', 'assets/music', 'assets/broll'
)
foreach ($RelativeDirectory in $Directories) {
    New-Item -ItemType Directory -Force -Path (Join-Path $ProjectRoot $RelativeDirectory) | Out-Null
}

Write-Host 'Next: edit .env, replace every CHANGE_ME value, then run .\scripts\up.ps1'

