# Phase 7D Module Kickoff Review

This document records the ChatGPT-approved kickoff review for Phase 7D. Codex is not the project architect and is only implementing the scoped external analytics preflight package.

## Purpose

Evaluate external analytics candidates before any package installation or integration.

## Upstream

- Phase 7A factor foundation
- Phase 7B validation metrics
- Phase 7C factor candidate library

## Downstream

- possible Phase 7E larger data readiness
- possible Phase 7F external analytics isolated prototypes
- Phase 8 strategy tournament later

## Why Preflight Comes Before Installation

External analytics tools often impose data shape, dependency, runtime, and maintenance assumptions. Preflight records intended role, risk, and integration boundaries before any package can enter an isolated prototype or adapter path.

## Language And Runtime Decision

Phase 7D uses Python standard library only. Python is appropriate because this module creates preflight metadata, validation helpers, policy documents, and tests.

No pandas, NumPy, Polars, DuckDB, Parquet, Alphalens, quantstats, empyrical, Qlib, or external framework is introduced.

## Scope

Allowed:

- static preflight metadata
- standard-library loaders and validators
- docs and tests

Prohibited:

- no external package installation
- no real alpha claim
- no real market data
- no tear sheets
- no portfolio reports
- no strategy tournament
- no broker/live/order path

## Success Criteria

- All external analytics candidates remain unapproved for install and adapter work.
- Every candidate has conservative risk metadata and notes.
- Tests prove no alpha, trading-ready, install, adapter, or final-selection claims exist.
- Review packet records no package, data, analytics, backtest, or strategy work occurred.
