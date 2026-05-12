# Phase 7A Module Kickoff Review

This document records the ChatGPT-approved kickoff review for Phase 7A. Codex is not the project architect and is only implementing the scoped alpha/factor foundation.

## Purpose

Build the first local alpha/factor foundation using fake fixtures and standard-library Python.

## Upstream

- Phase 3 data contracts
- Phase 5 market rules
- Phase 6D backtest comparative review

## Downstream

- Phase 7B factor validation metrics
- Phase 7C factor library
- Phase 8 strategy tournament

## Why Backtest Engine Selection Is Not Required

Phase 7A defines factor metadata, toy computation, and evaluation shape checks. These are research contracts and local calculations, not a backtest engine integration. Final backtest engine selection can remain deferred while factor interfaces and evidence rules are established.

## Language And Runtime Decision

Phase 7A uses Python standard library only. Python is appropriate because this module defines research contracts, local toy computation, and pytest validation.

No pandas, NumPy, Polars, DuckDB, Parquet, Alphalens, quantstats, or empyrical are introduced.

## Scope

Allowed:

- factor metadata contracts
- toy factor definitions
- local fake-fixture factor computation
- minimal factor evaluation shape checks
- evidence-gated documentation

Prohibited:

- no real alpha claim
- no real market data
- no external factor analytics packages
- no backtest
- no strategy
- no model training
- no broker/live/order path

## Success Criteria

- Factor type definitions exist.
- A toy close-to-close momentum factor computes over the fake fixture.
- Toy evaluation summary reports limitations clearly.
- Tests prove no trading readiness or alpha claim is introduced.
- Review packet records no dependencies, no real data, no backtest, and no profitability claim.
