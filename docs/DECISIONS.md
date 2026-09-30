# Decisions and assumptions

## Pinned versions

- PostgreSQL image: `postgres:17.11-alpine3.24`
- n8n Community Edition image: `n8nio/n8n:2.39.8` (stable release selected 2026-09-22)
- Python image: `python:3.13.15-slim-bookworm`
- FastAPI 0.116.1, SQLAlchemy 2.0.43, Psycopg 3.2.10, Alembic 1.16.5, Pydantic Settings 2.10.1
- Ruff 0.12.11, mypy 1.17.1, pytest 8.4.2

All container tags are explicit. A controlled dependency-update task must review release notes, rebuild, migrate a disposable database, and rerun verification before changing them.

## Architecture choices

- PostgreSQL is not exposed to the host. Direct host database access was omitted because containerized Alembic, tests, backups, and `psql` cover Phase 01 without increasing exposure.
- PostgreSQL lives only on an internal network. n8n and the API also join a normal edge network so optional host Ollama and future official APIs remain reachable.
- The API starts by applying Alembic and repeatable seeds. PostgreSQL health gates startup, while Ollama is optional.
- FFmpeg is deferred to Phase 03. Adding it now would increase the image and OS package surface without any Phase 01 renderer behavior to verify.
- Runtime configuration is environment-backed; editable brand, policy, and schedules are YAML. Database `system_settings` holds only non-secret canonical defaults.
- The inactive seed prompt is a lineage placeholder, not a content generator.

## Editable assumptions

- Logo files, licensed fonts, and official brand colors were not provided. YAML palette and typography values are conspicuously marked placeholders.
- The initial audience, tone, CTA examples, and weekly times are reasonable editable defaults, not a claim of final brand approval.
- `Asia/Karachi` is the editorial timezone; UTC remains the database timestamp standard.
- n8n owner creation is manual on first local visit. No credentials are fabricated.
- The Git repository was initialized because the workspace was empty and not already versioned.

