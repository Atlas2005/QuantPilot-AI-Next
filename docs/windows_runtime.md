# Windows Runtime Node

Windows is the QuantPilot runtime machine; macOS remains the development and control machine. QMT/XtQuant, broker login, broker credentials, and order submission are not implemented in PR #125. The configured broker provider is always `none`.

## Prerequisites and bootstrap

Install 64-bit Windows, 64-bit Python 3.12 (the `py` launcher is preferred), Git for Windows, and a running Docker Desktop with Docker Compose. Open PowerShell in the cloned repository and run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\bootstrap_windows_runtime_v1.ps1
```

The bootstrap creates or reuses `.venv`, securely requests the required `TUSHARE_TOKEN`, and lets Enter skip the optional `DEEPSEEK_API_KEY`. DeepSeek live calls remain disabled. PostgreSQL and Grafana credentials are generated automatically and never printed.

Runtime data lives under `%LOCALAPPDATA%\QuantPilot\runtime` in `config`, `secrets`, `logs`, `state`, `cache`, and `reports`. Secret files are encrypted with current-user Windows DPAPI and contain no plaintext credentials. PostgreSQL and Grafana use persistent Docker volumes; Grafana is available to the local machine at `http://localhost:3000` with anonymous Viewer access.

## Daily operation

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_windows_runtime_v1.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\status_windows_runtime_v1.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\stop_windows_runtime_v1.ps1
```

Stop preserves every Docker volume and runtime file. Re-running bootstrap repairs safe configuration, preserves existing service credentials, and does not prompt again for an intentionally skipped optional DeepSeek key.

Refresh only the TuShare and optional DeepSeek API keys with:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\bootstrap_windows_runtime_v1.ps1 -ForceSecretRefresh
```

## Diagnosis and backup

Status performs bounded, read-only PostgreSQL and localhost Grafana probes. For JSON diagnostics:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\status_windows_runtime_v1.ps1 -Json
```

On failure, confirm Docker Desktop is running, then rerun status and follow the named `NOT_READY` check. Missing DPAPI files must be restored from the same Windows user profile; bootstrap refuses to invent replacement service credentials when matching persistent volumes already exist.

Before machine maintenance, stop the runtime, copy `%LOCALAPPDATA%\QuantPilot\runtime` to protected backup storage, and back up the Docker named volumes `control_center_pgdata` and `control_center_grafana_data` with Docker Desktop's volume backup facility. Preserve the Windows user profile/DPAPI keys with the encrypted secret files. Never remove the named volumes during normal lifecycle operations.

For CI-only validation, `-ValidateOnly -NonInteractive -SkipDocker` changes no state. Full noninteractive provisioning requires synthetic placeholder environment secrets and an isolated `QUANTPILOT_RUNTIME_HOME` under the system temporary directory; it never performs provider calls.
