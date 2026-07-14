# Windows Runtime Node

Windows is the QuantPilot runtime machine; macOS remains the development and control machine. QuantPilot uses 64-bit Python 3.12. The broker-supported QMT built-in strategy environment uses 64-bit Python 3.6.8.

Guojin Securities QMT does not expose the external XtQuant Python API in the regulated test environment, and MiniQMT is disabled. The supported integration is therefore a QMT built-in Python strategy plus an atomic local JSON bridge. QuantPilot does not import `xtquant`, load private QMT DLLs, require `userdata_mini`, modify the QMT installation, or start QMT.

This bridge is read-only. It does not submit or cancel orders. Its snapshots must state `order_submission_enabled=false`, `cancel_enabled=false`, `passorder_invoked=false`, and `cancel_invoked=false`; Runtime Doctor rejects a snapshot that cannot prove those properties.

## Prerequisites and bootstrap

Install 64-bit Windows, 64-bit Python 3.12 (the `py` launcher is preferred), Git for Windows, and a running Docker Desktop with Docker Compose. Open Windows PowerShell 5.1 in the cloned repository and run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\bootstrap_windows_runtime_v1.ps1
```

For a fresh runtime, the default broker provider is `none`. Once schema-v2 configuration exists, an ordinary bootstrap with no QMT arguments preserves the provider and every QMT setting. Only parameters explicitly supplied on that invocation override their corresponding fields; in particular, explicit `-BrokerProvider none` intentionally disables an existing bridge without erasing its saved QMT settings. The bootstrap creates or reuses `.venv`, securely requests the required `TUSHARE_TOKEN`, and lets Enter skip the optional `DEEPSEEK_API_KEY`. DeepSeek live calls remain disabled. PostgreSQL and Grafana credentials are generated automatically and never printed.

Runtime data lives under `%LOCALAPPDATA%\QuantPilot\runtime` in `config`, `secrets`, `logs`, `state`, `cache`, and `reports`. Secret files are encrypted with current-user Windows DPAPI and contain no plaintext credentials. PostgreSQL and Grafana use persistent Docker volumes; Grafana is available locally at `http://localhost:3000` with anonymous Viewer access.

## Configure the QMT built-in bridge

Choose one bridge root outside the Git repository and use the same path in QMT and QuantPilot. The exporter default is `D:\QuantPilotQMTBridge`. A directory under `%LOCALAPPDATA%\QuantPilot\runtime` is also supported. Do not place snapshots in the repository.

Configure the runtime for the default external bridge root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\bootstrap_windows_runtime_v1.ps1 `
  -BrokerProvider qmt_builtin_bridge `
  -QmtBridgeRoot 'D:\QuantPilotQMTBridge' `
  -QmtMaxSnapshotAgeSeconds 120 `
  -QmtExpectedAccountType STOCK `
  -QmtPollingIntervalSeconds 5 `
  -QmtHeartbeatIntervalSeconds 30 `
  -QmtProviderMode simulation_signal
```

The persisted schema-v2 runtime configuration supports these environment equivalents:

- `QUANTPILOT_BROKER_PROVIDER=none|qmt_builtin_bridge`
- `QUANTPILOT_QMT_BRIDGE_ROOT`
- `QUANTPILOT_QMT_MAX_SNAPSHOT_AGE_SECONDS`
- `QUANTPILOT_QMT_EXPECTED_ACCOUNT_TYPE`
- `QUANTPILOT_QMT_EXPECTED_REDACTED_ACCOUNT_ID` (optional)
- `QUANTPILOT_QMT_POLL_INTERVAL_SECONDS`
- `QUANTPILOT_QMT_HEARTBEAT_INTERVAL_SECONDS`
- `QUANTPILOT_QMT_PROVIDER_MODE=simulation_signal`

Bootstrap also creates or reuses a cryptographically random 32-byte account-binding key at `<bridge-root>\state\account_binding_key_v1.hex`. The file is outside Git and snapshots, contains exactly 64 lowercase hexadecimal bytes, and is restricted to the current Windows user as far as Windows PowerShell 5.1 permits. The exporter reads it locally; neither the key nor the raw account identifier is logged or serialized. A missing, unreadable, empty, malformed, or oversized key stops exporter initialization.

Never put a complete account number in runtime configuration. After the first snapshot is available, an optional account binding may use only the exported value shaped like `qmtacct-v1-` followed by 24 lowercase hexadecimal characters. This is a domain-separated HMAC-SHA256 keyed pseudonymous account binding, not an account credential. Re-run bootstrap with `-QmtExpectedRedactedAccountId` set to that token. Runtime errors never echo the configured or observed binding.

## Create and run the QMT exporter strategy

The tracked strategy source is `scripts/qmt_builtin_readonly_exporter_v1.py`. In the QMT strategy editor:

1. Create a new Python strategy and copy the entire source without changing its first line, `#coding:gbk`.
2. Keep `DEFAULT_BRIDGE_ROOT` at `D:\QuantPilotQMTBridge`, or change it to exactly the bridge root configured above. The strategy has no third-party dependency.
3. Select the broker's test stock account in the QMT UI so QMT injects `account` and `accountType=STOCK`. Do not paste the account number, account key, shareholder identifier, or password into the strategy or repository.
4. Select simulation-signal mode. Do not select a live-trading mode. Start the strategy only while signed in to the intended broker test environment.
5. Confirm that the initial heartbeat appears, followed by bounded periodic snapshots. The strategy uses QMT `run_time` when available and a bounded `handlebar` fallback.

The exporter calls `get_trade_detail_data` for `account`, `position`, `order`, and `deal`. It never calls an order-submission or cancellation function. A failed section query is recorded in the heartbeat instead of stopping the other read-only queries.

To stop exporting, stop this strategy in the QMT UI. Its `stop` lifecycle handler releases the single-writer lock and clears the in-memory raw account value. QuantPilot never starts or stops QMT automatically.

Broker simulation matching is available only during the broker's stated test-window availability. Outside that window, a heartbeat may still prove that the local exporter is alive, but broker-side simulation matching may be unavailable.

## Bridge directory layout

```text
<bridge-root>\
  snapshots\
    latest_snapshot_v1.json
    latest_snapshot_v1.json.tmp   # transient; readers always ignore it
  state\
    account_binding_key_v1.hex    # local current-user key; never serialized
    qmt_builtin_exporter_v1.lock
```

The exporter writes the temporary file in the same directory, flushes it, and replaces `latest_snapshot_v1.json` atomically. QuantPilot reads only the completed JSON file. A temp-only directory is reported as an incomplete atomic write. Runtime copies, snapshots, lock files, and generated inspection reports remain outside Git.

Snapshots use schema version `1`, bridge version `qmt_builtin_readonly_bridge_v1`, provider `qmt_builtin_bridge`, and environment `simulation_signal`. They include an independent QMT trading date, UTC timestamp, normalized account/position/order/trade data, per-section query status, bounded provenance, and the four read-only safety flags.

With no completed snapshot, the first successful export uses sequence `1`. On restart, a valid completed snapshot at sequence `N` is retained and the next successful export uses `N+1`; a stale temporary file is ignored. If the completed file is malformed, unsupported, or has an invalid sequence or snapshot identifier, initialization fails closed, releases the writer lock, and leaves both completed and temporary files untouched. Sequence continuity therefore depends on retaining a valid completed snapshot.

## Inspect and operate

The dedicated inspection command validates a completed snapshot and writes a bounded local report to `%LOCALAPPDATA%\QuantPilot\runtime\reports\qmt_builtin_bridge_inspection_v1.json`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\inspect_qmt_builtin_bridge_v1.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\inspect_qmt_builtin_bridge_v1.ps1 -Json
```

It prints the snapshot timestamp and age, provider and mode, account status, QMT trading date, total assets, available cash, position/order/trade counts, validation result, report path, and every read-only safety flag. It never prints a complete account identifier and never contacts QMT.

Normal runtime lifecycle commands remain:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_windows_runtime_v1.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\status_windows_runtime_v1.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\stop_windows_runtime_v1.ps1
```

Runtime Doctor preserves the existing `provider=none` result. For `provider=qmt_builtin_bridge`, status checks the configured directory and one completed snapshot, then reports snapshot age, account status, trading date, record counts, and read-only flags. Missing, temp-only, malformed, unsupported, stale, and identity-mismatched snapshots are narrow `NOT_READY` results. Doctor is stateless across separate invocations and does not detect historical rollback; callers that deliberately retain one reader's optional in-process `SequenceTracker` can reject duplicate or regressing observations within that process. Doctor is side-effect free and performs no QMT or broker call.

Stop preserves every Docker volume and runtime file. Re-running bootstrap migrates a valid schema-v1 configuration to schema v2 with `broker_provider=none` and a default QMT block, while preserving its runtime home, safe service settings, DPAPI secret files, PostgreSQL/Grafana credentials, and Docker volumes. Re-running against schema v2 preserves existing provider and QMT fields except for explicit command-line overrides, preserves the account-binding key, and does not prompt again for an intentionally skipped optional DeepSeek key. Malformed existing configuration is rejected instead of replaced. Refresh only TuShare and the optional DeepSeek API key with `-ForceSecretRefresh`.

## Diagnosis and backup

Status performs bounded, read-only PostgreSQL and localhost Grafana probes in addition to the local bridge check. On failure, rerun status or the dedicated bridge inspector and follow the named `NOT_READY` result. Missing DPAPI files must be restored from the same Windows user profile; bootstrap refuses to invent replacement service credentials when matching persistent volumes already exist.

Before machine maintenance, stop the runtime and QMT exporter, copy `%LOCALAPPDATA%\QuantPilot\runtime` to protected backup storage, and back up the Docker named volumes `control_center_pgdata` and `control_center_grafana_data`. Also preserve the configured bridge root's `state\account_binding_key_v1.hex` in protected storage outside Git and snapshots; restoring that same key preserves stable pseudonymous account bindings. Preserve the Windows user profile/DPAPI keys with the encrypted secret files. Never remove named volumes during normal lifecycle operations.

For CI-only validation, `-ValidateOnly -NonInteractive -SkipDocker` changes no state. Full noninteractive provisioning requires synthetic placeholder environment secrets and an isolated `QUANTPILOT_RUNTIME_HOME` under the system temporary directory; it never performs provider calls.

PR #126 implements only the read-only snapshot bridge. PR #127 may add a separate, explicitly enabled simulation-order intent and acknowledgement protocol. That future boundary is not present here: there is no intent consumption, `passorder`, cancellation, broker mutation, automated execution, or QMT order/fill persistence in this bridge.
