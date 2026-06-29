# Next Chat Handoff

## Project Goal

QuantPilot-AI 2.0 is a profit-first, integration-first, adapter-first, contract-first, A-share-first AI quant research and trading decision platform designed to move toward controlled capital testing through evidence-gated research.

## Current Phase

R2: Market Reality Sandbox Contracts, implemented by Codex and pending ChatGPT closure review.

## Completed Work

Step 0A through Phase 7F are completed.

R1 created:

- `docs/PROFIT_FIRST_INTEGRATION_ARCHITECTURE.md`
- `docs/MULTI_AGENT_TARGET_ARCHITECTURE.md`
- `docs/MARKET_REALITY_SANDBOX_ARCHITECTURE.md`
- `docs/CAPITAL_AWARE_FAST_COMPOUNDING_MODE.md`
- `docs/OPEN_SOURCE_REPLACEMENT_STRATEGY.md`
- `docs/UPSTREAM_DEPENDENCY_INTELLIGENCE_LAYER.md`
- `docs/THIRTY_DAY_CAPITAL_TEST_MVP_PLAN.md`
- `data/integration_reset/r1_integration_replacement_matrix.json`
- `src/quantpilot_core/integration_reset/`
- `tests/integration_reset/test_integration_matrix.py`
- R1 module kickoff and closure draft docs

R1.1 created:

- `docs/OPEN_SOURCE_INTEGRATION_ENFORCEMENT.md`
- `data/integration_reset/open_source_integration_decision_table.json`
- `src/quantpilot_core/integration_reset/open_source_decision_table.py`
- `tests/integration_reset/test_open_source_decision_table.py`
- exports from `src/quantpilot_core/integration_reset/__init__.py`

R2 created:

- `docs/MARKET_REALITY_SANDBOX_CONTRACTS.md`
- `src/quantpilot_core/market_reality/__init__.py`
- `src/quantpilot_core/market_reality/contracts.py`
- `src/quantpilot_core/market_reality/validation.py`
- `tests/market_reality/test_market_reality_contracts.py`
- `tests/market_reality/test_market_reality_validation.py`

No provider package was installed, no real data was fetched, no provider was approved, no adapter was created, no broker connection was created, and no order execution path was added.

R2 does not implement full backtest, risk, factor, calendar, or portfolio accounting engines.

## Current Prohibitions

- do not fetch market data without a later approved manual probe instruction
- do not call external APIs during automated validation
- do not install packages
- do not create provider API clients or token handling in `src/`
- do not commit raw provider data
- do not run real factor validation
- do not claim alpha, profitability, or statistical significance
- do not run real backtests
- do not implement strategy tournament
- do not implement production adapters
- do not implement broker/live/order or agent workflows
- do not mark anything trading-ready
- do not claim profitability

## Next Recommended Step

ChatGPT should perform R2 closure review.

The next recommended phase should move toward controlled adapter/probe integration or sandbox validation using fixtures.

Future work must stay contract/adapter-boundary focused. It must use mature open-source candidates through adapters, prototypes, or benchmarks where practical instead of becoming a fully self-built backtest, risk, factor, calendar, or portfolio accounting engine.

Do not move to larger real-data validation, external analytics install, broker connectivity, live trading, strategy tournament, or real alpha claims until approved.

## Key Decisions

- R1 is architecture reset only, not implementation approval.
- Capital-Aware Fast Compounding Mode replaces the old small-capital framing.
- Market Reality Sandbox is now a formal architecture target.
- External candidates are recorded in a machine-readable matrix with all R1 safety permissions false.
- R1.1 makes open-source integration review enforceable with a decision table and validator.
- R1 was architecture reset, not full external integration.
- Future modules must check mature open-source candidates before self-building.
- R2 adds Market Reality Sandbox contracts and validation helpers only.
- R2 represents mature open-source projects as adapter boundaries, not replaced self-built engines.
- Codex is not the project architect.

## Role Split

ChatGPT is the architecture lead and strategic reviewer.

Codex creates files, organizes docs, runs safe validation commands, and produces review packets.

ChatGPT, not Codex, performs module closure review.
