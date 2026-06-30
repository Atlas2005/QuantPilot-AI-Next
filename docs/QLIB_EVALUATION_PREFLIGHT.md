# R29 Qlib Evaluation Preflight

R29 adds a deterministic preflight layer for future Qlib evaluation work.

It does not install, import, or run Qlib. It does not call `qrun`, call DeepSeek, use the network, connect to brokers, place orders, mutate accounts, train models, or update live strategy weights. It is a configuration, evidence, and safety gate before any later Qlib runtime phase.

## Purpose

QuantPilot-AI-Next is open-source-first and integration-first, so Qlib remains a serious candidate for future factor and workflow evaluation. R29 keeps that path explicit without pretending the project is already running Qlib.

The preflight validates whether a future Qlib evaluation configuration is coherent enough to prepare:

- dataset shape
- calendar readiness metadata
- benchmark and cost settings
- PIT/no-lookahead requirement
- R28 factor metric handoff
- runtime-disabled sandbox safety

## Supported Modes

R29 supports these preflight modes:

- `factor_analysis`
- `signal_analysis`
- `backtest_readiness`
- `full_workflow_preflight`

These are mode labels only. No runtime workflow is executed.

## Dataset Checks

Dataset config must include:

- explicit non-placeholder `provider_uri`
- non-empty region and market
- A-share / CN-oriented market metadata
- non-empty instrument universe
- strict ISO `YYYY-MM-DD` start and end dates
- `start_date <= end_date`
- non-empty calendar name
- dataset evidence references
- no duplicate instruments

R29 does not check filesystem existence and does not access provider paths. That is intentional: the preflight is offline and deterministic.

## Benchmark Checks

Benchmark config must include:

- non-empty benchmark symbol
- supported frequency: `day`, `1d`, or `daily`
- non-empty cost model
- slippage in `[0, 100]` basis points
- commission rate in `[0, 0.01]`
- stamp tax rate in `[0, 0.01]`
- benchmark evidence references

If the configured market is A-share / CN but the benchmark symbol does not look compatible, R29 emits a manual-review warning rather than silently passing it.

## PIT And No-Lookahead

`pit_required` must be true. If it is false, the preflight blocks.

R29 also refuses runtime execution with `allow_runtime_execution=True`. Any request to treat R29 as a Qlib runtime, qrun, or backtest execution path is a critical safety violation.

## R28 Factor Metric Handoff

R29 expects a factor metric result from R28 or an equivalent object with a deterministic `decision`.

- R28 `pass` allows the Qlib preflight to proceed.
- R28 `manual_review` propagates manual review.
- R28 `fail` blocks.
- Failed metric records block.
- Warning metric records trigger manual review.

This keeps factor evidence validation upstream of future Qlib evaluation work.

## Optional Qlib Boundary

Qlib remains optional in R29. The new code does not import `qlib`, does not require it in project dependencies, and does not run a Qlib workflow.

The project-specific code added here is limited to contracts, configuration validation, PIT and sandbox safety checks, and adapter-ready preflight records.

## Future Path

R29 prepares the project for R30 final readiness and release hardening by making Qlib evaluation readiness explicit before any runtime integration.

Future phases can add:

- Qlib fixture format preflight
- Qlib dependency detection
- qrun dry-run fixture preparation
- richer integration with R28 Stats Agent / Factor Metrics and R27 Multi-Agent Orchestrator

Those future phases must remain behind explicit preflight gates and continue avoiding live execution, broker paths, and unreviewed model updates.
