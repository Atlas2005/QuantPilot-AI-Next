# Module Kickoff Review: Phase 3 Data Contracts and Local Fixtures

This document records the ChatGPT-approved Phase 3 kickoff. It is not Codex's independent strategic judgment.

## Purpose

Create the first local data contract layer for A-share daily OHLCV research data and verify it using static local fixtures only.

Phase 3 defines data shape and local validation only. It does not connect to real data sources.

## Upstream

- Step 0A planning
- Step 0B skeleton
- Phase 1 candidate registry
- Phase 1.1 candidate registry refresh
- Phase 2 core contracts

## Downstream

- controlled data-source prototypes
- A-share market rules
- backtest engine evaluation

## Allowed Scope

- Python standard library only
- existing pytest dev dependency
- local CSV fixtures
- provisional A-share daily OHLCV schema
- minimal standard-library validation

## Prohibited Scope

- real data source integration
- market data fetching
- external API calls
- external validation frameworks
- external storage frameworks
- data-source adapters
- backtesting
- strategy logic
- factor calculation
- portfolio optimization
- model training
- agent orchestration
- broker connection
- live trading or order execution paths
- trading-readiness claims
- profitability claims
- old v2 source-code copying

## Success Criteria

- local valid fixture loads and validates with no errors
- local invalid fixture produces validation errors
- schema constants and enums are tested
- CSV loader uses standard library only
- no external frameworks are imported or installed
- `python -m compileall src` passes
- `python -m pytest` passes

