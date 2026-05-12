# Phase 7B Module Kickoff Review

This document records the ChatGPT-approved kickoff review for Phase 7B. Codex is not the project architect and is only implementing the scoped factor validation metrics foundation.

## Purpose

Build a minimal, evidence-gated factor validation metrics foundation.

## Upstream

- Phase 3 data contracts
- Phase 5 market rules
- Phase 6D backtest comparative review
- Phase 7A alpha/factor foundation

## Downstream

- Phase 7C factor candidate library
- Phase 7D external analytics preflight
- Phase 8 strategy tournament

## Why Metrics Come Before Factor Library Expansion

Factor validation metrics define the evidence gates and limitations that future factor candidates must satisfy. Expanding a factor library before evidence rules would encourage quantity over validation discipline.

## Language And Runtime Decision

Phase 7B uses Python standard library only. Python remains appropriate because this module defines validation contracts, local toy metrics, and pytest validation.

No pandas, NumPy, Polars, DuckDB, Parquet, Alphalens, quantstats, or empyrical are introduced.

## Scope

Allowed:

- validation metric types
- toy IC-like metric shape
- toy forward-return grouping
- sample-size and evidence-quality warnings
- documentation for future real alpha evidence requirements

Prohibited:

- no real alpha claim
- no real market data
- no external analytics packages
- no backtest
- no strategy
- no statistical significance claim
- no broker/live/order path

## Success Criteria

- Toy metric results always remain evidence-gated.
- Reports keep `alpha_claim_allowed` and `trading_ready` false.
- Policy metadata records later OOS, walk-forward, paper feedback, transaction cost, and A-share rule requirements.
- Tests prove tiny samples and fake fixtures do not become alpha evidence.
