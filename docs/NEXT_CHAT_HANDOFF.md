# Next Chat Handoff

## Project Goal

QuantPilot-AI 2.0 is an open-source-first, adapter-first, contract-first, A-share-first AI quant integration platform designed to evolve toward a profitable AI quantitative trading platform through evidence-gated research.

## Current Phase

Phase 6D: backtest prototype comparative review, implemented by Codex and pending ChatGPT closure review.

## Completed Work

Step 0A through Phase 6C-3B are completed.

Phase 6D created:

- `docs/modules/phase_6d_backtest_comparative_review/MODULE_KICKOFF_REVIEW.md`
- `docs/modules/phase_6d_backtest_comparative_review/MODULE_CLOSURE_DRAFT.md`
- `data/backtest_engine_candidates/prototype_comparison.json`
- `src/quantpilot_core/backtest_engines/comparison.py`
- `docs/BACKTEST_ENGINE_COMPARATIVE_REVIEW.md`
- `tests/backtest_engines/test_backtest_comparison.py`

The comparison records vectorbt and Backtrader as toy fake-fixture successes, RQAlpha as isolated install/import evidence only, and Qlib as metadata-only.

## Current Prohibitions

- do not fetch market data
- do not call external APIs
- do not install packages
- do not add prototype packages to `pyproject.toml`
- do not start Qlib install without ChatGPT approval
- do not implement production backtest adapters
- do not implement strategy, alpha/factor, portfolio, model, broker, live order, or agent workflows
- do not mark anything trading-ready
- do not claim profitability

## Next Recommended Step

ChatGPT should perform Phase 6D closure review.

Do not start Qlib install, adapter work, or Phase 7 until approved.

## Key Decisions

- No final backtest engine selection was made.
- No engine is approved for adapter work.
- No engine is trading-ready.
- Python remains appropriate for current research/runtime work, with language/runtime review at each major module.
- Codex is not the project architect.

## Role Split

ChatGPT is the architecture lead and strategic reviewer.

Codex creates files, organizes docs, runs safe validation commands, and produces review packets.

ChatGPT, not Codex, performs module closure review.
