#!/usr/bin/env bash
set -euo pipefail

# ------------------------------------------------------------------------------
# TBOS Automation - Cloud & Local Backup Script
# Performs atomic backups of PostgreSQL database, n8n data, and rendered media,
# then synchronizes the archive to Google Drive / cloud storage using rclone.
# ------------------------------------------------------------------------------

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

# Source environment variables if .env exists
if [[ -f "$project_root/.env" ]]; then
    # shellcheck disable=SC1091
    set -a
    source "$project_root/.env"
    set +a
fi

timestamp="$(date +%Y%m%d-%H%M%S)"
destination="$project_root/backups/$timestamp"
mkdir -p "$destination"

rclone_remote="${RCLONE_REMOTE:-}"
local_retention_days="${LOCAL_RETENTION_DAYS:-7}"
cloud_retention_days="${CLOUD_RETENTION_DAYS:-30}"

# Parse optional arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -r|--remote)
            rclone_remote="$2"
            shift 2
            ;;
        --local-retention)
            local_retention_days="$2"
            shift 2
            ;;
        --cloud-retention)
            cloud_retention_days="$2"
            shift 2
            ;;
        *)
            echo "Unknown argument: $1" >&2
            echo "Usage: $0 [-r|--remote <rclone-remote>] [--local-retention <days>] [--cloud-retention <days>]" >&2
            exit 1
            ;;
    esac
done

echo "=== TBOS Automation Backup Starting ($timestamp) ==="

# 1. Verify required containers are running
postgres_id="$(docker compose ps -q postgres 2>/dev/null || true)"
n8n_id="$(docker compose ps -q n8n 2>/dev/null || true)"

if [[ -z "$postgres_id" || -z "$n8n_id" ]]; then
    echo "ERROR: PostgreSQL and n8n services must be running to create an atomic backup." >&2
    exit 1
fi

# 2. Database Backup (PostgreSQL custom format dump)
echo "-> Dumping PostgreSQL database ($APP_DB_NAME)..."
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$APP_DB_NAME" -Fc -f /tmp/tbos-app.dump'
docker cp "$postgres_id:/tmp/tbos-app.dump" "$destination/tbos-app.dump"
docker compose exec -T postgres rm -f /tmp/tbos-app.dump

# 3. n8n Configuration & Credentials Backup
echo "-> Archiving n8n workflows and user data..."
docker compose exec -T n8n sh -c 'tar -czf /tmp/n8n-data.tar.gz -C "$N8N_USER_FOLDER" .'
docker cp "$n8n_id:/tmp/n8n-data.tar.gz" "$destination/n8n-data.tar.gz"
docker compose exec -T n8n rm -f /tmp/n8n-data.tar.gz

# 4. Storage & Rendered Media Backup
if [[ -d "$project_root/storage" && "$(ls -A "$project_root/storage" 2>/dev/null)" ]]; then
    echo "-> Archiving storage assets, renders, and handoff bundles..."
    tar -czf "$destination/storage-media.tar.gz" -C "$project_root" storage
else
    echo "-> Storage directory empty or not present; skipping media tar."
fi

# 5. Integrity Verification
for required_file in "tbos-app.dump" "n8n-data.tar.gz"; do
    file_path="$destination/$required_file"
    if [[ ! -s "$file_path" ]]; then
        echo "ERROR: Backup integrity check failed: $required_file is missing or empty." >&2
        exit 1
    fi
done

echo "✓ Local backup successfully staged at: $destination"
ls -lh "$destination"

# 6. Cloud Synchronization via rclone (Google Drive / S3 / R2)
if [[ -n "$rclone_remote" ]]; then
    if command -v rclone >/dev/null 2>&1; then
        echo "-> Synchronizing backup to remote: $rclone_remote/$timestamp..."
        rclone copy "$destination" "$rclone_remote/$timestamp" \
            --transfers 4 \
            --checkers 8 \
            --stats-one-line \
            --log-level NOTICE

        echo "✓ Cloud upload completed."

        # Remote retention policy
        if [[ "$cloud_retention_days" -gt 0 ]]; then
            echo "-> Pruning cloud backups older than $cloud_retention_days days..."
            rclone delete --min-age "${cloud_retention_days}d" "$rclone_remote" 2>/dev/null || true
            rclone rmdirs --leave-root "$rclone_remote" 2>/dev/null || true
        fi
    else
        echo "WARNING: rclone is not installed or not in PATH. Skipping cloud upload."
        echo "Install rclone (https://rclone.org) and run 'rclone config' to enable Google Drive backups."
    fi
else
    echo "NOTICE: RCLONE_REMOTE not configured in .env or passed via --remote. Cloud upload skipped."
fi

# 7. Local Retention Pruning
if [[ "$local_retention_days" -gt 0 ]]; then
    echo "-> Pruning local backups older than $local_retention_days days..."
    find "$project_root/backups" -mindepth 1 -maxdepth 1 -type d -mtime "+$local_retention_days" -exec rm -rf {} + 2>/dev/null || true
fi

echo "=== TBOS Backup Finished Successfully ==="
