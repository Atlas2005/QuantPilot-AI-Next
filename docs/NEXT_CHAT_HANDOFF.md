# Next Chat Handoff

## Project Goal

QuantPilot-AI 2.0 is an open-source-first, adapter-first, contract-first, A-share-first AI quant integration platform designed to evolve toward a profitable AI quantitative trading platform through evidence-gated research.

## Current Phase

Phase 1: open-source candidate registry, implemented by Codex and pending ChatGPT closure review.

## Completed Work

Step 0A planning package was completed.

Step 0B clean skeleton and minimal CI was completed and pushed.

Phase 1 created:

- `src/quantpilot_core/registry/candidate.py`
- `src/quantpilot_core/registry/candidate_loader.py`
- updated `src/quantpilot_core/registry/__init__.py`
- `data/open_source_candidates/candidates.json`
- `docs/OPEN_SOURCE_CANDIDATE_REGISTRY.md`
- updated `docs/OPEN_SOURCE_CANDIDATE_UNIVERSE.md`
- `docs/modules/phase_1_candidate_registry/MODULE_KICKOFF_REVIEW.md`
- `docs/modules/phase_1_candidate_registry/MODULE_CLOSURE_DRAFT.md`
- `tests/registry/test_candidate_registry.py`
- updated project state, decisions, handoff, and review packet

## Current Prohibitions

- do not implement trading logic
- do not fetch market data
- do not call external APIs
- do not install or import quant, data-source, broker, ML, or agent frameworks
- do not run backtests
- do not train models
- do not implement data adapters
- do not implement agent orchestration
- do not connect brokers
- do not create broker/live trading/order paths
- do not mark anything trading-ready
- do not claim profitability
- do not make final technical selections

## Next Recommended Step

ChatGPT should perform Phase 1 closure review.

Do not move to Phase 2 core contracts until ChatGPT approves.

## Key Decisions

- Candidate registry is static metadata only.
- No candidate is approved for implementation.
- No candidate is `approved_for_adapter`.
- External frameworks must later enter through adapters and contract tests.
- Open-source refresh is ChatGPT-led at module boundaries.
- Codex is not the project architect.

## Role Split

ChatGPT is the architecture lead and strategic reviewer.

Codex creates files, organizes docs, runs safe validation commands, and produces review packets.

ChatGPT, not Codex, performs module closure review.

## What Not To Do

Do not install candidate frameworks, fetch data, add trading logic, add broker paths, create backtest/model/agent implementations, or make trading-readiness/profitability claims.

