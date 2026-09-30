[CmdletBinding()]
param(
    [string]$RcloneRemote = $env:RCLONE_REMOTE,
    [int]$LocalRetentionDays = 7,
    [int]$CloudRetentionDays = 30
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

# Load .env variables if present and not already defined
$EnvFile = Join-Path $ProjectRoot '.env'
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith('#') -and $line.Contains('=')) {
            $parts = $line.Split('=', 2)
            $varName = $parts[0].Trim()
            $varVal = $parts[1].Trim().Trim('"').Trim("'")
            if (-not [System.Environment]::GetEnvironmentVariable($varName)) {
                [System.Environment]::SetEnvironmentVariable($varName, $varVal, 'Process')
            }
        }
    }
}

if (-not $RcloneRemote) {
    $RcloneRemote = $env:RCLONE_REMOTE
}

$Timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$Destination = Join-Path $ProjectRoot "backups/$Timestamp"
New-Item -ItemType Directory -Path $Destination -Force | Out-Null

Write-Host "=== TBOS Automation Backup Starting ($Timestamp) ===" -ForegroundColor Cyan

# 1. Verify required containers are running
$PostgresId = docker compose ps -q postgres 2>$null
$N8nId = docker compose ps -q n8n 2>$null

if (-not $PostgresId -or -not $N8nId) {
    throw 'ERROR: PostgreSQL and n8n services must be running to create an atomic backup.'
}

# 2. Database Backup
Write-Host "-> Dumping PostgreSQL database ($env:APP_DB_NAME)..."
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$APP_DB_NAME" -Fc -f /tmp/tbos-app.dump'
docker cp "${PostgresId}:/tmp/tbos-app.dump" (Join-Path $Destination 'tbos-app.dump')
docker compose exec -T postgres rm -f /tmp/tbos-app.dump

# 3. n8n Configuration & Workflows Backup
Write-Host "-> Archiving n8n workflows and user data..."
docker compose exec -T n8n sh -c 'tar -czf /tmp/n8n-data.tar.gz -C "$N8N_USER_FOLDER" .'
docker cp "${N8nId}:/tmp/n8n-data.tar.gz" (Join-Path $Destination 'n8n-data.tar.gz')
docker compose exec -T n8n rm -f /tmp/n8n-data.tar.gz

# 4. Storage & Rendered Media Backup
$StorageDir = Join-Path $ProjectRoot 'storage'
if ((Test-Path $StorageDir) -and (Get-ChildItem -Path $StorageDir -Force | Select-Object -First 1)) {
    Write-Host "-> Archiving storage assets, renders, and handoff bundles..."
    $StorageArchive = Join-Path $Destination 'storage-media.zip'
    Compress-Archive -Path $StorageDir -DestinationPath $StorageArchive -Force
} else {
    Write-Host "-> Storage directory empty or not present; skipping media archive."
}

# 5. Integrity Verification
foreach ($FileName in @('tbos-app.dump', 'n8n-data.tar.gz')) {
    $FilePath = Join-Path $Destination $FileName
    if (-not (Test-Path $FilePath) -or (Get-Item $FilePath).Length -le 0) {
        throw "ERROR: Backup integrity check failed: $FileName is missing or empty."
    }
}

Write-Host "[OK] Local backup successfully staged at: $Destination" -ForegroundColor Green
Get-ChildItem -Path $Destination | Format-Table Name, Length, LastWriteTime

# 6. Cloud Synchronization via rclone
if ($RcloneRemote) {
    $RcloneCmd = Get-Command 'rclone' -ErrorAction SilentlyContinue
    if ($RcloneCmd) {
        Write-Host "-> Synchronizing backup to remote: $RcloneRemote/$Timestamp..."
        & rclone copy $Destination "$RcloneRemote/$Timestamp" --transfers 4 --checkers 8 --stats-one-line
        Write-Host "[OK] Cloud upload completed." -ForegroundColor Green

        if ($CloudRetentionDays -gt 0) {
            Write-Host "-> Pruning cloud backups older than $CloudRetentionDays days..."
            & rclone delete --min-age "${CloudRetentionDays}d" $RcloneRemote
            & rclone rmdirs --leave-root $RcloneRemote 2>$null
        }
    } else {
        Write-Warning "rclone is not installed or not in PATH. Skipping cloud upload."
        Write-Host "Install rclone (choco install rclone or https://rclone.org) and run 'rclone config' for Google Drive."
    }
} else {
    Write-Host "NOTICE: RCLONE_REMOTE not configured in .env or passed via -RcloneRemote. Cloud upload skipped."
}

# 7. Local Retention Pruning
if ($LocalRetentionDays -gt 0) {
    Write-Host "-> Pruning local backups older than $LocalRetentionDays days..."
    $Cutoff = (Get-Date).AddDays(-$LocalRetentionDays)
    Get-ChildItem -Path (Join-Path $ProjectRoot 'backups') -Directory | Where-Object { $_.CreationTime -lt $Cutoff } | Remove-Item -Recurse -Force
}

Write-Host "=== TBOS Backup Finished Successfully ===" -ForegroundColor Cyan
