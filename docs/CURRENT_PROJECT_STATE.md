# Current Project State

## Project

QuantPilot-AI-Next / QuantPilot-AI 2.0.

## Current Phase

Phase 2: core contracts, implemented by Codex and pending ChatGPT closure review.

## Current Contents

Step 0A planning package is completed.

Step 0B clean skeleton and minimal CI is completed.

Phase 1 open-source candidate registry is completed and pushed.

Phase 2 adds core contract skeletons:

- contract metadata and enums
- base contract boundary
- data source contract boundary
- data validator contract boundary
- market rule contract boundary
- backtest engine contract boundary
- factor engine contract boundary
- portfolio engine contract boundary
- agent skill contract boundary
- contract shape tests

The repository is still not trading-ready.

No external framework integration exists.

## Current Prohibitions

- do not implement trading logic
- do not fetch market data
- do not call external APIs
- do not install new packages
- do not import quant, data-source, broker, ML, or agent frameworks
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

## Next Expected Action

ChatGPT should perform Phase 2 module closure review and decide whether Phase 3 data contracts and local fixtures work may begin.

