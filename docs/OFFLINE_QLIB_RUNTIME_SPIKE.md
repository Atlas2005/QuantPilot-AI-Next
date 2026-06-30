# P32 Offline Qlib Runtime Spike

P32 defines a safe offline boundary for representing QuantPilot factor and data preflight evidence as a Qlib-compatible runtime plan.

This is not a production Qlib integration. It does not run Qlib, run qrun, call the network, connect to brokers, place orders, call DeepSeek, call OpenAI, train models, or update live strategy weights.

## Purpose

P31 validated supplied real-data samples through a fixture-first stability trial. P32 checks whether the resulting project evidence can be expressed as an offline runtime plan before any future runtime spike.

The plan keeps the project integration-first and open-source-first while preserving the Market Reality Sandbox boundary:

- dataset path must be local-only
- calendar must be explicit or fixture-backed
- benchmark must be declared
- factor metric handoff must include R28-compatible metric names
- runtime execution must remain manual and optional
- default tests must pass without Qlib installed

## Runtime Plan Contracts

P32 defines:

- `OfflineQlibRuntimePlan`
- `QlibDatasetBoundary`
- `QlibCalendarBoundary`
- `QlibBenchmarkBoundary`
- `FactorMetricHandoff`
- `OfflineRuntimeReadinessReport`

These contracts are for readiness planning only. They do not create a live runtime config and do not execute any external framework.

## Dataset Boundary

The dataset boundary requires:

- non-empty local dataset URI
- no URL-style dataset path
- explicit provider name
- explicit market
- non-empty symbol list
- strict ISO start and end dates
- `start_date <= end_date`
- `local_only=True`
- evidence references

P32 does not read provider data and does not verify filesystem existence. That remains a future fixture/runtime preparation step.

## Calendar Boundary

The calendar boundary must be explicitly provided or fixture-backed.

When trading dates are supplied, they must use strict ISO `YYYY-MM-DD` format and must be unique.

## Benchmark Boundary

The benchmark boundary requires:

- benchmark symbol or index
- supported frequency: `day`, `1d`, or `daily`
- cost model name
- evidence references

## Factor Metric Handoff

The factor metric handoff must include the R28-compatible metric names needed for a future offline evaluation:

- `ic`
- `rank_ic`
- `hit_rate`
- `turnover`
- `max_drawdown`
- `cost_aware_score`

A failed factor metric decision blocks the plan. A manual-review factor metric decision produces manual review.

## Optional Manual Runner

`run_optional_offline_qlib_runtime_spike` is guarded by explicit flags.

By default it returns manual review and does not import the optional runtime dependency. When manual runtime is explicitly enabled, the dependency check is still non-fatal: a missing package returns a structured manual-review report rather than breaking default tests.

## Decisions

P32 returns:

- `READY` when all offline checks pass
- `MANUAL_REVIEW` when warning-only checks exist
- `NOT_READY` when blockers exist

`ready` is true only for `READY`.

## Safety Boundary

P32 does not:

- call DeepSeek
- call OpenAI
- call the network
- connect to brokers
- place orders
- mutate accounts
- run Qlib or qrun by default
- run RQAlpha
- train models
- update live strategy weights
- add Qlib as a required dependency

## Path To Next Phase

P32 prepares a future offline runtime fixture spike. The next phase should only proceed after P31 data stability evidence and P32 runtime-plan evidence are both ready or explicitly manual-reviewed.
