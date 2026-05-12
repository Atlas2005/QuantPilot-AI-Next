# Next Chat Handoff

## Project Goal

QuantPilot-AI 2.0 is an open-source-first, adapter-first, contract-first, A-share-first AI quant integration platform designed to evolve toward a profitable AI quantitative trading platform through evidence-gated research.

## Current Phase

Phase 6C-3A: RQAlpha license, maintenance, and isolation preflight, implemented by Codex and pending ChatGPT closure review.

## Completed Work

Step 0A through Phase 6C-2 are completed.

Phase 6C-3A created:

- `docs/modules/phase_6c_3a_rqalpha_preflight/MODULE_KICKOFF_REVIEW.md`
- `docs/modules/phase_6c_3a_rqalpha_preflight/MODULE_CLOSURE_DRAFT.md`
- `data/backtest_engine_candidates/rqalpha_preflight.json`
- `src/quantpilot_core/backtest_engines/preflight.py`
- `docs/RQALPHA_PREFLIGHT_REVIEW.md`
- `tests/backtest_engines/test_rqalpha_preflight.py`

RQAlpha has preflight metadata only. It was not installed, imported, or run.

## Current Prohibitions

- do not fetch market data
- do not call external APIs
- do not install or import RQAlpha without ChatGPT approval
- do not add RQAlpha or other prototype packages to `pyproject.toml`
- do not run RQAlpha outside isolated `.venv-prototypes/rqalpha/`
- do not move to isolated RQAlpha prototype before ChatGPT approval
- do not implement production backtest adapters
- do not implement strategy, alpha/factor, portfolio, model, broker, live order, or agent workflows
- do not mark anything trading-ready
- do not claim profitability

## Next Recommended Step

ChatGPT should perform Phase 6C-3A closure review.

Do not move to isolated RQAlpha prototype until approved.

## Key Decisions

- RQAlpha is China-market relevant but sensitive because it is a backtest/trading framework.
- RQAlpha requires license, maintenance, Windows, dependency, data bundle, A-share rule fit, and broker/live/order isolation review.
- RQAlpha is not a project dependency.
- No final backtest engine selection was made.
- Codex is not the project architect.

## Role Split

ChatGPT is the architecture lead and strategic reviewer.

Codex creates files, organizes docs, runs safe validation commands, and produces review packets.

ChatGPT, not Codex, performs module closure review.
