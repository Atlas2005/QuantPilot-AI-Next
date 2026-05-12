# Next Chat Handoff

## Project Goal

QuantPilot-AI 2.0 is an open-source-first, adapter-first, contract-first, A-share-first AI quant integration platform designed to evolve toward a profitable AI quantitative trading platform through evidence-gated research.

## Current Phase

Phase 6A: backtest engine evaluation foundation, implemented by Codex and pending ChatGPT closure review.

## Completed Work

Step 0A through Phase 5 are completed.

Phase 6A created:

- `src/quantpilot_core/backtest_engines/types.py`
- `src/quantpilot_core/backtest_engines/evaluation.py`
- `data/backtest_engine_candidates/backtest_engines.json`
- metadata-level tests for backtest candidates
- `docs/BACKTEST_ENGINE_EVALUATION.md`
- `docs/BACKTEST_ENGINE_CANDIDATES.md`
- Phase 6A module kickoff and closure draft docs

## Current Prohibitions

- do not fetch market data
- do not call external APIs
- do not install packages
- do not import external frameworks
- do not implement backtesting
- do not implement strategy, alpha/factor, portfolio, model, broker, live order, or agent workflows
- do not mark anything trading-ready
- do not claim profitability

## Next Recommended Step

ChatGPT should perform Phase 6A closure review.

Do not move to Phase 6B until approved.

## Key Decisions

- Backtest engine selection remains open-source-first, adapter-first, contract-first, A-share-first, and evidence-gated.
- No framework was installed or selected.
- Live-trading-capable engines are high-risk and must remain isolated from early core.
- Future integration must happen through adapters and contract tests.
- Codex is not the project architect.

## Role Split

ChatGPT is the architecture lead and strategic reviewer.

Codex creates files, organizes docs, runs safe validation commands, and produces review packets.

ChatGPT, not Codex, performs module closure review.

