# R4 RQAlpha A-Share Backtest Adapter

R4A introduces an optional RQAlpha adapter skeleton for A-share backtest workflows.
RQAlpha is the mature-framework target for A-share event-driven backtest and
trading semantics.

This is not a production or live trading integration. QuantPilot does not add
RQAlpha as a required dependency, does not run fake backtests, does not invent
metrics, and does not create a self-built backtest engine, fill simulator,
portfolio accounting engine, or safety-gate layer.

The adapter returns structured status for missing runtime prerequisites:

- `framework_missing` when RQAlpha is not installed.
- `config_required` when the optional runtime is present but no explicit config
  is supplied.
- `data_bundle_required` when config is present but no local data bundle hint is
  supplied.
- `not_executed` when no caller-owned runner executes a real workflow.

These statuses are local to the adapter and must not globally block vectorbt,
Qlib, or multi-agent workflows. vectorbt remains preferred for signal replay and
portfolio metrics. Qlib remains preferred for AI and factor research.

QuantPilot keeps only A-share, provider, account, broker, and agent-facing glue
plus normalized contracts. Runtime execution remains explicit and caller-owned.
