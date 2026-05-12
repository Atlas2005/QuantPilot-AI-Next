# Next Chat Handoff

## Project Goal

QuantPilot-AI 2.0 is an open-source-first, adapter-first, contract-first, A-share-first AI quant integration platform designed to evolve toward a profitable AI quantitative trading platform through evidence-gated research.

## Current Phase

Phase 7C: factor candidate library foundation, implemented by Codex and pending ChatGPT closure review.

## Completed Work

Step 0A through Phase 7B are completed.

Phase 7C created:

- `src/quantpilot_core/factors/candidate_library.py`
- `src/quantpilot_core/factors/toy_candidate_factors.py`
- `data/factor_definitions/factor_candidates.json`
- `docs/FACTOR_CANDIDATE_LIBRARY.md`
- candidate library and toy candidate factor tests

The implementation uses only Python standard library and fake Phase 3 local fixtures.

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

ChatGPT should perform Phase 7C closure review.

Do not move to external analytics integration, larger real-data validation, strategy tournament, or real alpha claims until approved.

## Key Decisions

- Phase 7C is fake-fixture-only.
- Factor candidates are not alpha evidence.
- No factor is validated or trading-ready.
- Python standard library is sufficient for this module.
- Codex is not the project architect.

## Role Split

ChatGPT is the architecture lead and strategic reviewer.

Codex creates files, organizes docs, runs safe validation commands, and produces review packets.

ChatGPT, not Codex, performs module closure review.
