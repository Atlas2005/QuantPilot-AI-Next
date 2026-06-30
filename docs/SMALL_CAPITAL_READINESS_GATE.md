# Small-Capital Readiness Gate

R25 adds a deterministic readiness gate before any broker sandbox adapter or closer-to-real execution workflow.

The gate consumes R23 `PaperReplayResult` and R24 `PerformanceAttributionResult` objects, computes thresholded readiness metrics, and returns `PASS`, `FAIL`, or `MANUAL_REVIEW`. It does not connect to brokers, place live orders, train models, call DeepSeek, perform network calls, or write persistence.

## Purpose

Small-capital progression should require explicit replay and attribution evidence. R25 prevents the project from moving toward broker sandbox adapters based on a single successful dry-run or vague qualitative confidence.

The gate asks:

- Did the replay cover enough days?
- Were blocked days and blocked instructions low enough?
- Were there any critical risks?
- Were estimated costs reasonable relative to simulated notional?
- Was negative feedback contained?
- Were enough instructions accepted?
- Was cash drawdown within limit?
- Is optional concentration evidence available and acceptable?

## Inputs

R25 consumes:

- R23 `PaperReplayResult`
- R24 `PerformanceAttributionResult`
- optional `SmallCapitalReadinessThresholds`

Input objects are treated as read-only.

## Default Thresholds

Default thresholds are conservative:

- `min_replay_days = 5`
- `max_blocked_day_ratio = 0.20`
- `max_blocked_instruction_ratio = 0.20`
- `max_critical_risk_flags = 0`
- `max_total_estimated_cost_ratio = 0.005`
- `max_negative_feedback_ratio = 0.35`
- `min_accepted_instruction_count = 3`
- `max_cash_drawdown_ratio = 0.05`
- `max_position_concentration_ratio = None`

The optional concentration threshold is disabled by default. If enabled and replay output lacks enough concentration data, the metric returns `WARNING` and the gate returns `MANUAL_REVIEW` unless another hard failure exists.

## Decisions

`PASS` means all hard metrics pass and no warning metrics are present.

`FAIL` means input validation failed or one or more hard metrics failed.

`MANUAL_REVIEW` means hard checks passed but at least one warning metric needs human review.

`ok` is true only for `PASS`.

## Safety Boundaries

R25 is a readiness gate only. It does not connect to brokers, mutate accounts, place live orders, call DeepSeek, train models, update strategy weights, perform network calls, write paper-ledger persistence, or run Qlib/RQAlpha.

## Future Use

R25 supports a future Broker Sandbox Adapter and Multi-Agent Orchestrator by requiring explicit replay and attribution evidence before any closer-to-real workflow is considered.
