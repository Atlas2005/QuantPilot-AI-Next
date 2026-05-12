# Next Chat Handoff

## Project Goal

QuantPilot-AI 2.0 is an open-source-first, adapter-first, contract-first, A-share-first AI quant integration platform designed to evolve toward a profitable AI quantitative trading platform through evidence-gated research.

## Current Phase

Phase 2: core contracts, implemented by Codex and pending ChatGPT closure review.

## Completed Work

Step 0A planning package was completed.

Step 0B clean skeleton and minimal CI was completed.

Phase 1 candidate registry was completed and pushed.

Phase 2 created:

- `src/quantpilot_core/contracts/types.py`
- updated `src/quantpilot_core/contracts/base.py`
- `src/quantpilot_core/contracts/data_source.py`
- `src/quantpilot_core/contracts/data_validator.py`
- `src/quantpilot_core/contracts/market_rule.py`
- `src/quantpilot_core/contracts/backtest_engine.py`
- `src/quantpilot_core/contracts/factor_engine.py`
- `src/quantpilot_core/contracts/portfolio_engine.py`
- `src/quantpilot_core/contracts/agent_skill.py`
- updated `src/quantpilot_core/contracts/__init__.py`
- `tests/contracts/test_core_contracts.py`
- updated contract and smoke tests
- `docs/CORE_CONTRACTS.md`
- Phase 2 module kickoff and closure draft docs

## Current Prohibitions

- do not implement trading logic
- do not fetch market data
- do not call external APIs
- do not install or import quant, data-source, broker, ML, or agent frameworks
- do not implement data adapters
- do not run backtests
- do not implement strategy logic
- do not calculate factors
- do not optimize portfolios
- do not train models
- do not implement agent orchestration
- do not connect brokers
- do not create broker/live trading/order paths
- do not mark anything trading-ready
- do not claim profitability
- do not copy old v2 source code

## Next Recommended Step

ChatGPT should perform Phase 2 closure review.

Do not move to Phase 3 data contracts and local fixtures until ChatGPT approves.

## Key Decisions

- Core contracts are boundaries, not implementations.
- External frameworks must later enter through adapters and contract tests.
- No final engine or framework selection has been made.
- Agent skill contract is a late-stage boundary only.
- Market rule contract is a boundary before the actual A-share rule engine phase.
- Codex is not the project architect.

## Role Split

ChatGPT is the architecture lead and strategic reviewer.

Codex creates files, organizes docs, runs safe validation commands, and produces review packets.

ChatGPT, not Codex, performs module closure review.

## What Not To Do

Do not install candidate frameworks, fetch data, add trading logic, add broker paths, create backtest/model/agent implementations, or make trading-readiness/profitability claims.

