# Current Project State

## Project

QuantPilot-AI-Next / QuantPilot-AI 2.0.

## Current Phase

Phase 0B: clean skeleton and minimal CI, completed by Codex and pending ChatGPT closure review.

## Current Contents

Step 0A planning package is completed and pushed.

Step 0B adds a minimal Python `src` layout package, placeholder base contract, placeholder in-memory registry, safety defaults, minimal tests, and GitHub Actions CI.

The repository is still not trading-ready.

## Current Prohibitions

- do not implement trading logic
- do not fetch market data
- do not call external APIs
- do not install packages except the project with pytest dev dependency when needed for validation
- do not import quant, data-source, broker, ML, or agent frameworks
- do not run backtests
- do not train models
- do not connect brokers
- do not create broker/live trading/order paths
- do not mark anything trading-ready
- do not claim profitability
- do not create automatic dependency merge logic
- do not blindly integrate open-source frameworks

## Next Expected Action

ChatGPT should perform Step 0B module closure review and decide whether Phase 1 candidate registry work may begin.

