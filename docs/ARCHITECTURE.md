# Architecture

Phase 01 is a Windows 11 and Docker Desktop foundation. The host publishes only two loopback ports: n8n on `127.0.0.1:5678` and FastAPI on `127.0.0.1:8080`. PostgreSQL has no host port.

```mermaid
flowchart LR
    Browser[Local browser] -->|127.0.0.1:5678| N8N[n8n CE]
    Browser -->|127.0.0.1:8080| API[FastAPI renderer-api]
    N8N -->|private Docker network| PG[(PostgreSQL 17)]
    API -->|private Docker network| PG
    API -. future optional .->|host.docker.internal:11434| Ollama[Native Windows Ollama]
    N8N <--> Shared[storage/ shared files]
    API <--> Shared
    N8N -. future official APIs .-> Telegram[Telegram]
    N8N -. future temporary objects .-> R2[Cloudflare R2]
    N8N -. future official APIs .-> Meta[Meta Graph API]
    N8N -. manual package only .-> TikTok[TikTok handoff]
```

## Components and trust boundaries

- **Host:** VS Code, Git, Docker Desktop/WSL2, local browser, and eventually native Ollama. Ollama is deliberately not a required container and its absence is degraded/optional.
- **`tbos_private` network:** internal bridge shared by PostgreSQL and its two clients. PostgreSQL holds two owner-isolated databases: `tbos_content` for application data and `n8n` for n8n internals.
- **`tbos_edge` network:** gives n8n and the API controlled outbound/host reachability without attaching PostgreSQL to that boundary.
- **Shared files:** `config`, `templates`, and `assets` are read-only in the API; `storage` is writable and shared with n8n. Runtime media is ignored by Git.
- **Public boundary:** there is no public service in Phase 01. Local published ports bind to loopback only. Future public callbacks need a reviewed HTTPS ingress, authentication, and narrow routing.
- **External platforms:** future Telegram, Cloudflare R2, and Meta access must use official APIs and separately scoped secrets. Tokens never belong in content tables.

TikTok publishing is intentionally a manual handoff package until an officially compliant API route is available. Browser login bots and scraping are outside the design because they are fragile, unsafe for credentials, and can violate platform rules.

