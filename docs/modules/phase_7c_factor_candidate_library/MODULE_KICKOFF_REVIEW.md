# Phase 7C Module Kickoff Review

This document records the ChatGPT-approved kickoff review for Phase 7C. Codex is not the project architect and is only implementing the scoped factor candidate library foundation.

## Purpose

Create a conservative factor candidate library foundation.

## Upstream

- Phase 3 data contracts
- Phase 5 market rules
- Phase 7A factor foundation
- Phase 7B validation metrics

## Downstream

- Phase 7D external analytics preflight
- Phase 7E larger fixture / real-data readiness
- Phase 8 strategy tournament later

## Why Factor Library Comes After Validation Policy

Phase 7B established evidence gates before candidate expansion. Phase 7C can now add toy candidates without implying that more factors are better or validated.

## Language And Runtime Decision

Phase 7C uses Python standard library only. Python remains appropriate because this module defines factor candidates, metadata, and local toy computations.

No pandas, NumPy, Polars, DuckDB, Parquet, Alphalens, quantstats, empyrical, or Qlib are introduced.

## Scope

Allowed:

- static factor candidate metadata
- toy factor computation functions
- candidate evidence status and risk notes
- tests proving no alpha or trading-readiness claims

Prohibited:

- no real alpha claim
- no real market data
- no external factor analytics packages
- no backtest
- no strategy tournament
- no optimization
- no broker/live/order path

## Success Criteria

- Factor candidates load and validate conservatively.
- Toy candidate functions compute observations over fake fixtures only.
- Every candidate has `alpha_claim_allowed: false` and `trading_ready: false`.
- No candidate is marked validated or production-ready.
