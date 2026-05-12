# Next Chat Handoff

## Project Goal

QuantPilot-AI 2.0 is an open-source-first, adapter-first, contract-first, A-share-first AI quant integration platform designed to evolve toward a profitable AI quantitative trading platform through evidence-gated research.

## Current Phase

Phase 6C-2: manual Backtrader local-fixture prototype, implemented by Codex and pending ChatGPT closure review.

## Completed Work

Step 0A through Phase 6C-1.1 are completed.

Phase 6C-2 created:

- `docs/modules/phase_6c_2_backtrader_manual_prototype/MODULE_KICKOFF_REVIEW.md`
- `docs/modules/phase_6c_2_backtrader_manual_prototype/MODULE_CLOSURE_DRAFT.md`
- `tools/manual_backtest_prototypes/backtrader_local_fixture_probe.py`
- `tools/manual_backtest_prototypes/summarize_backtrader_probe.py`

The manual Backtrader probe used only the fake Phase 3 fixture, converted it to a local Backtrader-compatible CSV under `local_artifacts/`, and ran only inside `.venv-prototypes/backtrader/`. It showed Backtrader can consume the converted local fixture shape and produce a toy event-driven result, but it did not prove A-share realism or production readiness.

## Current Prohibitions

- do not fetch market data
- do not call external APIs
- do not add Backtrader or other prototype packages to `pyproject.toml`
- do not run prototype packages outside isolated `.venv-prototypes/<tool-name>/` environments
- do not move to RQAlpha prototype without ChatGPT approval
- do not implement production backtest adapters
- do not implement strategy, alpha/factor, portfolio, model, broker, live order, or agent workflows
- do not mark anything trading-ready
- do not claim profitability

## Next Recommended Step

ChatGPT should perform Phase 6C-2 closure review.

Do not move to RQAlpha prototype or adapter implementation until approved.

## Key Decisions

- Phase 6C-2 tested Backtrader only.
- Backtrader is not a project dependency.
- No final backtest engine selection was made.
- No production Backtrader adapter exists.
- Codex is not the project architect.

## Role Split

ChatGPT is the architecture lead and strategic reviewer.

Codex creates files, organizes docs, runs safe validation commands, and produces review packets.

ChatGPT, not Codex, performs module closure review.
