# TechBuilt Open School Automation

Phase 01 provides the local, self-hosted foundation for a human-approved educational social-media workflow. It includes PostgreSQL 17, n8n Community Edition, a typed FastAPI service, Alembic migrations, repeatable seed data, local-only ports, operational scripts, and automated checks. Content generation, rendering, approvals, and publishing are intentionally deferred to later phases.

## Quick start (Windows PowerShell)

```powershell
.\scripts\bootstrap.ps1
# Edit .env and replace every CHANGE_ME value, then:
.\scripts\up.ps1
.\scripts\verify.ps1
```

Local services:

- FastAPI: <http://localhost:8080>
- API docs in development: <http://localhost:8080/docs>
- n8n: <http://localhost:5678>

See [Windows setup](docs/SETUP_WINDOWS.md), [architecture](docs/ARCHITECTURE.md), and [security](docs/SECURITY.md). PostgreSQL is not published to the host.

