# Current Project State

## Project

QuantPilot-AI-Next / QuantPilot-AI 2.0.

## Current Phase

Phase 3: data contracts and local fixtures, implemented by Codex and pending ChatGPT closure review.

## Current Contents

Step 0A planning package is completed.

Step 0B clean skeleton and minimal CI is completed.

Phase 1 open-source candidate registry is completed.

Phase 1.1 candidate registry refresh is completed.

Phase 2 core contracts is completed.

Phase 3 adds a provisional A-share daily OHLCV data contract, standard-library CSV loader, local fixture helper, fake local CSV fixtures, and local validation tests.

The repository is still not trading-ready.

No real data source integration exists.

## Current Prohibitions

- do not implement trading logic
- do not fetch market data
- do not call external APIs
- do not install new packages
- do not import external data, quant, validation, storage, or agent frameworks
- do not implement data-source adapters
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

ChatGPT should perform Phase 3 module closure review. Do not move to Phase 4 until approved.

