# Manual Backtest Prototypes

This folder is for future manual backtest engine prototypes only.

These tools are not run in CI. No backtest framework is installed by the project, and no framework is selected in Phase 6B.

Early prototypes may use only the fake local Phase 3 fixture. Provider data is not fetched.

Raw outputs must stay under `local_artifacts/`.

Live-trading-capable frameworks must never be allowed to create broker, live trading, or real order submission paths.

Phase 6B does not run prototypes.

## R4D RQAlpha Local Run Attempt

`rqalpha_local_run_attempt.py` is a manual prototype tool only. It must be run
from the isolated RQAlpha environment:

```bash
.venv-prototypes/rqalpha/bin/python tools/manual_backtest_prototypes/rqalpha_local_run_attempt.py
```

The tool writes a structured result artifact to:

```text
local_artifacts/backtest_prototypes/rqalpha/rqalpha_local_run_result.json
```

It does not install packages, does not modify the main `.venv`, does not call
the network directly, and records bundle/config/data failures as structured
local evidence. `explicit_metrics` only copies explicit allowed metric keys from
RQAlpha output mappings; missing metrics must not be calculated or inferred.
`observed_trade_rows`, if present, is evidence metadata rather than a performance
metric.

For R4F, the tool checks an authorized local bundle before attempting `run_func`.
It uses `~/.rqalpha/bundle` by default, or `RQALPHA_BUNDLE_PATH` for an explicit
local path outside tracked source. If no bundle is present, it writes
`data_bundle_required_or_missing` with `download_required=true` and exits cleanly
without attempting the run.
