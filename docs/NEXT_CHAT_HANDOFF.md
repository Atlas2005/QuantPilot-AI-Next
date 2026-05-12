# Next Chat Handoff

## Project Goal

QuantPilot-AI 2.0 is an open-source-first, adapter-first, contract-first, A-share-first AI quant integration platform designed to evolve toward a profitable AI quantitative trading platform through evidence-gated research.

## Current Phase

Phase 6C-1: manual vectorbt local-fixture prototype, implemented by Codex and pending ChatGPT closure review.

## Completed Work

Step 0A through Phase 6B are completed.

Phase 6C-1 created:

- `docs/modules/phase_6c_1_vectorbt_manual_prototype/MODULE_KICKOFF_REVIEW.md`
- `docs/modules/phase_6c_1_vectorbt_manual_prototype/MODULE_CLOSURE_DRAFT.md`
- `tools/manual_backtest_prototypes/vectorbt_local_fixture_probe.py`
- `tools/manual_backtest_prototypes/summarize_vectorbt_probe.py`
- `docs/BACKTEST_PROTOTYPE_RESULTS.md`

The manual vectorbt probe used only the fake Phase 3 fixture. It showed vectorbt can consume the local fixture shape and produce toy metrics, but it did not prove A-share realism or production readiness.

## Current Prohibitions

- do not fetch market data
- do not call external APIs
- do not add vectorbt or other prototype frameworks to `pyproject.toml`
- do not implement production backtest adapters
- do not move to Backtrader or RQAlpha prototype without ChatGPT approval
- do not implement strategy, alpha/factor, portfolio, model, broker, live order, or agent workflows
- do not mark anything trading-ready
- do not claim profitability

## Next Recommended Step

ChatGPT should perform Phase 6C-1 closure review.

Do not move to Backtrader/RQAlpha prototype or adapter implementation until approved.

## Key Decisions

- Phase 6C-1 tested vectorbt only.
- vectorbt is not a project dependency.
- No final backtest engine selection was made.
- No production vectorbt adapter exists.
- Codex is not the project architect.

## Role Split

ChatGPT is the architecture lead and strategic reviewer.

Codex creates files, organizes docs, runs safe validation commands, and produces review packets.

ChatGPT, not Codex, performs module closure review.
