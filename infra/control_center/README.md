# QuantPilot Control Center

The Windows runtime lifecycle scripts inject the DPAPI-protected PostgreSQL and Grafana credentials into child processes and manage this existing Compose stack. Do not create a repository `.env` containing real credentials.

Use `scripts/start_windows_runtime_v1.ps1`, `scripts/status_windows_runtime_v1.ps1`, and `scripts/stop_windows_runtime_v1.ps1` from the repository root. Stop preserves the `pgdata` and `grafana_data` named volumes; never use `docker compose down -v` for this runtime.
