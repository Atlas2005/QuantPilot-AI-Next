# Next Chat Handoff

## Project Goal

QuantPilot-AI 2.0 is an open-source-first, adapter-first, contract-first, A-share-first AI quant integration platform designed to evolve toward a profitable AI quantitative trading platform through evidence-gated research.

## Current Phase

Phase 7A: alpha/factor foundation, implemented by Codex and pending ChatGPT closure review.

## Completed Work

Step 0A through Phase 6D are completed.

Phase 7A created:

- `src/quantpilot_core/factors/types.py`
- `src/quantpilot_core/factors/toy_factors.py`
- `src/quantpilot_core/factors/evaluation.py`
- `data/factor_definitions/toy_factors.json`
- `docs/ALPHA_FACTOR_FOUNDATION.md`
- factor tests for toy computation, toy evaluation, and metadata safety

The implementation uses only Python standard library and the fake Phase 3 local fixture.

## Current Prohibitions

- do not fetch market data
- do not call external APIs
- do not install packages
- do not add pandas, NumPy, Alphalens, quantstats, empyrical, Qlib, or backtest engines
- do not claim alpha or profitability
- do not run real backtests
- do not implement strategy tournament
- do not implement production adapters
- do not implement broker/live/order or agent workflows
- do not mark anything trading-ready

## Next Recommended Step

ChatGPT should perform Phase 7A closure review.

Do not move to factor validation metrics, factor library, strategy tournament, or external analytics integration until approved.

## Key Decisions

- Phase 7A is fake-fixture-only.
- Toy factor output is not alpha evidence.
- Python standard library is sufficient for this module.
- Final backtest engine selection is not required before factor contract foundation.
- Codex is not the project architect.

## Role Split

ChatGPT is the architecture lead and strategic reviewer.

Codex creates files, organizes docs, runs safe validation commands, and produces review packets.

ChatGPT, not Codex, performs module closure review.
