# Security baseline

- Copy `.env.example` to `.env`, replace every `CHANGE_ME` value, and never commit `.env`. Generate independent random database passwords and an n8n encryption key of at least 32 random characters.
- The API and n8n publish only to `127.0.0.1`; PostgreSQL has no host port and is attached only to the private network. These controls are development boundaries, not an internet deployment design.
- The API runs as UID/GID 10001, uses read-only configuration/template/asset mounts, and writes only shared runtime storage. PostgreSQL and n8n use their upstream image users.
- Application and n8n databases have distinct owner roles. Application tables must never store raw platform access tokens.
- n8n data backups contain encrypted credentials and are sensitive. Database dumps can contain unpublished content and user comments. Encrypt backup storage, restrict access, test restores, and apply a retention policy.
- Rotate a suspected token at the provider first, update `.env` without printing it, restart the affected service, and revoke old sessions. Changing `N8N_ENCRYPTION_KEY` without an n8n-supported migration can make stored credentials unreadable.
- Do not expose n8n directly to the internet. A later deployment needs HTTPS, authenticated ingress, trusted proxy configuration, rate limits, maintained owner credentials, and a callback-specific threat review.
- Social operations must use official Telegram and Meta APIs. Browser-login bots, unofficial session cookies, and scraping are prohibited because they expose credentials and bypass platform safeguards.
- Human review is mandatory before publishing. Approval records are bound to immutable versions so later edits cannot inherit stale approval.

Before committing, run `git status --ignored` and scan staged changes. CI uses disposable credentials only; it never needs production or personal tokens.

