# Next Chat Handoff

## Project Goal

QuantPilot-AI 2.0 is an open-source-first, adapter-first, contract-first, A-share-first AI quant integration platform designed to evolve toward a profitable AI quantitative trading platform through evidence-gated research.

## Current Phase

Phase 4A: controlled data-source prototype harness, implemented by Codex and pending ChatGPT closure review.

## Completed Work

Step 0A planning package was completed.

Step 0B clean skeleton and minimal CI was completed.

Phase 1 candidate registry was completed.

Phase 1.1 candidate registry refresh was completed.

Phase 2 core contracts was completed.

Phase 3 data contracts and local fixtures was completed and pushed.

Phase 4A created:

- manual-only prototype plan structures
- field-mapping validation helpers
- provisional mapping templates under `data/source_mapping_templates/`
- SimTradeData registry/reference metadata
- data-source prototype policy docs
- tests for prototype plan and field-mapping safety

## Current Prohibitions

- do not fetch market data
- do not call external APIs
- do not install or import external frameworks
- do not clone or copy external projects
- do not implement data-source adapters
- do not create token or secrets handling
- do not create broker/live/order paths
- do not implement backtesting, model training, or agent orchestration
- do not mark anything trading-ready
- do not claim profitability

## Next Recommended Step

ChatGPT should perform Phase 4A closure review.

Do not move to Phase 4B until approved.

## Key Decisions

- Data-source prototypes are manual-only until approved.
- Real data fetching is disabled in CI.
- Field mappings are provisional until manual verification.
- SimTradeData is registry/reference only until license review.
- Codex is not the project architect.

## Role Split

ChatGPT is the architecture lead and strategic reviewer.

Codex creates files, organizes docs, runs safe validation commands, and produces review packets.

ChatGPT, not Codex, performs module closure review.

