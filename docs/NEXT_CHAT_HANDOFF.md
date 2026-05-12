# Next Chat Handoff

## Project Goal

QuantPilot-AI 2.0 is an open-source-first, adapter-first, contract-first, A-share-first AI quant integration platform designed to evolve toward a profitable AI quantitative trading platform through evidence-gated research.

## Current Phase

Phase 7B: factor validation metrics foundation, implemented by Codex and pending ChatGPT closure review.

## Completed Work

Step 0A through Phase 7A are completed.

Phase 7B created:

- `src/quantpilot_core/factors/validation_metrics.py`
- `data/factor_validation/validation_metric_policy.json`
- `docs/FACTOR_VALIDATION_METRICS.md`
- validation metric and policy tests

The implementation uses only Python standard library, fake fixture assumptions, and Phase 7A toy factor shapes.

## Current Prohibitions

- do not fetch market data
- do not call external APIs
- do not install packages
- do not add pandas, NumPy, Alphalens, quantstats, empyrical, Qlib, or backtest engines
- do not claim alpha, profitability, or statistical significance
- do not run real backtests
- do not implement strategy tournament
- do not implement production adapters
- do not implement broker/live/order or agent workflows
- do not mark anything trading-ready

## Next Recommended Step

ChatGPT should perform Phase 7B closure review.

Do not move to factor library, external analytics integration, strategy tournament, or real alpha claims until approved.

## Key Decisions

- Phase 7B is fake-fixture-only.
- Toy IC-like metrics are not alpha evidence.
- Python standard library is sufficient for this module.
- OOS, walk-forward, transaction costs, A-share rules, turnover, capacity, and paper feedback are required before real alpha claims.
- Codex is not the project architect.

## Role Split

ChatGPT is the architecture lead and strategic reviewer.

Codex creates files, organizes docs, runs safe validation commands, and produces review packets.

ChatGPT, not Codex, performs module closure review.
