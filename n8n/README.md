# n8n local operations

The official n8n Community Edition image uses its own PostgreSQL database and a named state volume. `workflows/` is reserved for reviewed JSON exports; never export credentials into Git. `backups/` is ignored.

On first visit to <http://localhost:5678>, create the owner account manually. Keep the service local-only. Run `.\scripts\backup.ps1` before upgrades and follow [database restore guidance](../docs/DATABASE.md).

