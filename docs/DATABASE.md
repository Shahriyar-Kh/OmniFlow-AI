# Application database

PostgreSQL stores absolute timestamps as `timestamptz` in UTC. Editorial slots are interpreted in `Asia/Karachi` before conversion. UUIDs are primary keys; application and n8n data use separate databases and roles.

| Table | Purpose and principal relationships |
|---|---|
| `content_items` | Stable content identity, format, pillar, topic, lifecycle state, risk, and schedule. `external_key` is unique. |
| `content_versions` | Immutable creative snapshot belonging to one item. `(content_item_id, version_number)` is unique. Holds title, hook, CTA, caption, hashtags, structured scenes/scripts, and model/prompt lineage. |
| `assets` | Local generated artifacts for an exact version, with SHA-256, MIME data, and optional expiring public URL. |
| `approvals` | Human decision for an exact version; never an unversioned item-level approval. |
| `publish_jobs` | Per-platform state, scheduling, retries, errors, payload, and globally unique idempotency key. |
| `published_posts` | Successful external identity and permalink. `(platform, external_post_id)` is unique. |
| `metrics_snapshots` | Time-series analytics for a published post. |
| `comments` | Imported platform comments, risk class, and reviewable reply draft/state. External IDs are unique within a platform. |
| `workflow_events` | Structured audit/diagnostic events keyed by correlation ID. |
| `prompt_templates` | Versioned prompt definitions and model metadata. The Phase 01 placeholder is inactive. |
| `content_sources` | Sources used by a version, including retrieval and verification metadata. |
| `approved_facts` | Human-verified fact statements with source, reviewer, risk, and expiry. |
| `system_settings` | Non-secret structured defaults such as brand, pillars, formats, language, and targets. |

Content states are database-constrained to `IDEA`, `DRAFTED`, `QA_PASSED`, `APPROVAL_PENDING`, `CHANGES_REQUESTED`, `APPROVED`, `RENDERED`, `SCHEDULED`, `PUBLISHING`, `PUBLISHED`, `FAILED`, and `ARCHIVED`.

## Migrations and seed data

```powershell
docker compose exec renderer-api alembic -c database/alembic.ini upgrade head
docker compose exec renderer-api python -m database.seed.seed
docker compose exec renderer-api alembic -c database/alembic.ini current
```

The seed uses PostgreSQL upserts and is safe to repeat. Migration downgrades exist for development recovery, but never downgrade a populated production database without a verified backup and change review.

## Backup and restore

Run `.\scripts\backup.ps1`. It creates and verifies `tbos-app.dump` and `n8n-data.tar.gz` beneath a timestamped ignored directory. Backups can contain private content and encrypted n8n credentials; store them securely. `.env` and the n8n encryption key are deliberately excluded and must be backed up separately in a secrets manager or offline encrypted store.

Restore is a deliberate maintenance operation:

```powershell
# Stop application writers, keep PostgreSQL running.
docker compose stop renderer-api n8n
$Pg = docker compose ps -q postgres
docker cp .\backups\YYYYMMDD-HHMMSS\tbos-app.dump "${Pg}:/tmp/tbos-app.dump"
docker compose exec postgres sh -c 'dropdb -U "$POSTGRES_USER" --if-exists "$APP_DB_NAME"; createdb -U "$POSTGRES_USER" -O "$APP_DB_USER" "$APP_DB_NAME"; pg_restore -U "$POSTGRES_USER" -d "$APP_DB_NAME" --clean --if-exists /tmp/tbos-app.dump'
docker compose exec postgres rm -f /tmp/tbos-app.dump
docker compose start n8n renderer-api
```

Restoring n8n requires the matching `N8N_ENCRYPTION_KEY`. Stop n8n, inspect the archive, and restore it into its named volume from a short-lived container only after backing up the current volume. Test both database and n8n restores on disposable volumes before relying on them.

