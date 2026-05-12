# Next Chat Handoff

## Project Goal

QuantPilot-AI 2.0 is an open-source-first, adapter-first, contract-first, A-share-first AI quant integration platform designed to evolve toward a profitable AI quantitative trading platform through evidence-gated research.

## Current Phase

Phase 6B: backtest prototype isolation plan, implemented by Codex and pending ChatGPT closure review.

## Completed Work

Step 0A through Phase 6A are completed.

Phase 6B created:

- `src/quantpilot_core/backtest_engines/prototype_plan.py`
- `src/quantpilot_core/backtest_engines/prototype_loader.py`
- `data/backtest_engine_candidates/prototype_plans.json`
- `tools/manual_backtest_prototypes/README.md`
- `tools/manual_backtest_prototypes/export_phase3_fixture_snapshot.py`
- `docs/BACKTEST_PROTOTYPE_ISOLATION_PLAN.md`
- prototype plan and fixture snapshot tests
- Phase 6B module kickoff and closure draft docs

## Current Prohibitions

- do not fetch market data
- do not call external APIs
- do not install packages
- do not import external frameworks
- do not run backtests
- do not implement strategy, alpha/factor, portfolio, model, broker, live order, or agent workflows
- do not mark anything trading-ready
- do not claim profitability

## Next Recommended Step

ChatGPT should perform Phase 6B closure review.

Do not move to Phase 6C until approved.

## Key Decisions

- Future prototypes must be isolated, manual-only, non-CI, non-production, and evidence-gated.
- First-wave prototype order is vectorbt, Backtrader, RQAlpha.
- Qlib is second-wave.
- LEAN, vn.py / VeighNa, and NautilusTrader are deferred.
- Codex is not the project architect.

## Role Split

ChatGPT is the architecture lead and strategic reviewer.

Codex creates files, organizes docs, runs safe validation commands, and produces review packets.

ChatGPT, not Codex, performs module closure review.

