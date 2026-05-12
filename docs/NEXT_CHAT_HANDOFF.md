# Next Chat Handoff

## Project Goal

QuantPilot-AI 2.0 is an open-source-first, adapter-first, contract-first, A-share-first AI quant integration platform designed to evolve toward a profitable AI quantitative trading platform through evidence-gated research.

## Current Phase

Phase 3: data contracts and local fixtures, implemented by Codex and pending ChatGPT closure review.

## Completed Work

Step 0A planning package was completed.

Step 0B clean skeleton and minimal CI was completed.

Phase 1 candidate registry was completed.

Phase 1.1 candidate registry refresh was completed.

Phase 2 core contracts was completed.

Phase 3 created:

- `src/quantpilot_core/data/types.py`
- `src/quantpilot_core/data/schema.py`
- `src/quantpilot_core/data/validation.py`
- `src/quantpilot_core/data/csv_loader.py`
- `src/quantpilot_core/data/fixtures.py`
- fake local CSV fixtures under `data/fixtures/`
- tests under `tests/data/`
- `docs/DATA_CONTRACTS.md`
- Phase 3 module kickoff and closure draft docs

## Current Prohibitions

- do not fetch market data
- do not call external APIs
- do not install new packages
- do not import external data, quant, validation, storage, or agent frameworks
- do not implement data-source adapters
- do not run backtests
- do not implement trading, strategy, factor, portfolio, model, broker, live order, or agent workflows
- do not mark anything trading-ready
- do not claim profitability
- do not copy old v2 source code

## Next Recommended Step

ChatGPT should perform Phase 3 closure review.

Do not move to Phase 4 until approved.

## Key Decisions

- Local fixtures come before real data sources.
- The daily OHLCV schema is provisional.
- Validation is shape-only and does not check real market truth.
- No external validation/storage/data framework is integrated.
- Codex is not the project architect.

## Role Split

ChatGPT is the architecture lead and strategic reviewer.

Codex creates files, organizes docs, runs safe validation commands, and produces review packets.

ChatGPT, not Codex, performs module closure review.

