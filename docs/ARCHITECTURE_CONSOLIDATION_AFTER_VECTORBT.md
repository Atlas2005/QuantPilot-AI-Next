# Architecture Consolidation After Vectorbt

## Default Paper Backtest Backend

`vectorbt_integration` and the provider-facing `provider_vectorbt_replay` path are the default paper backtest/replay direction.

Legacy self-built paper replay modules are retained only for reference compatibility, migration audits, and historical metric comparisons. They are not the default runtime path.

## Legacy Engine Flag

`USE_LEGACY_ENGINE=false` by default.

Legacy paper execution requires an explicit opt-in:

- pass `use_legacy_engine=True` to the legacy entry point, or
- set `USE_LEGACY_ENGINE=true` in the process environment.

Without that opt-in, legacy execution raises a routing error that points callers back to the vectorbt path.

## C1/C2/C3 Modules In The Old Execution Path

### C1: Legacy Provider Paper Replay

- `real_provider_mixed_etf_paper_replay`

Status: legacy-only.

Default replacement: `provider_vectorbt_replay`, backed by vectorbt replay/integration.

### C2: Legacy Daily Replay And Fill Simulation

- `daily_paper_trading_loop_tradability_metrics`
- `gate_pruning_tradability_fill_loop`
- `mixed_stock_etf_daily_paper_evaluation`
- `qlib_offline_tradability_evaluation_fixture`

Status: legacy-only for paper execution.

Default replacement: vectorbt-backed replay for portfolio metrics and framework-owned signal simulation. QuantPilot-owned code should only provide validation, A-share/account glue, and adapters.

### C3: Legacy Paper Ledger Dry-Run Replay

- `paper_ledger_dry_run`
- `multi_day_paper_replay`
- `executable_candidate_paper_bridge`

Status: legacy-only for paper backtest/replay execution.

Default replacement: vectorbt-backed paper backtest/replay for research metrics. Ledger dry-run logic remains reference compatibility until a future broker/paper ledger boundary explicitly re-scopes it.

## Non-Goals

- No code is deleted in this consolidation.
- Broker/live modules are not changed.
- Qlib remains the mature research/signal framework path.
- RQAlpha remains the optional event-driven A-share semantics/prototype path.
- Neither is the default paper portfolio simulation backend in this consolidation.
