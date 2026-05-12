# Current Project State

## Project

QuantPilot-AI-Next / QuantPilot-AI 2.0.

## Current Phase

Phase 1: open-source candidate registry, implemented by Codex and pending ChatGPT closure review.

## Current Contents

Step 0A planning package is completed.

Step 0B clean skeleton and minimal CI is completed and pushed.

Phase 1 adds a structured candidate registry foundation:

- standard-library candidate metadata dataclass
- standard-library JSON loader and validation
- static candidate registry at `data/open_source_candidates/candidates.json`
- registry documentation
- candidate registry tests

The repository is still not trading-ready.

No external framework integration exists.

## Current Prohibitions

- do not implement trading logic
- do not fetch market data
- do not call external APIs
- do not install quant, data-source, broker, ML, or agent frameworks
- do not import quant, data-source, broker, ML, or agent frameworks
- do not run backtests
- do not train models
- do not implement data adapters
- do not implement agent orchestration
- do not connect brokers
- do not create broker/live trading/order paths
- do not mark anything trading-ready
- do not claim profitability
- do not make final technical selections

## Next Expected Action

ChatGPT should perform Phase 1 module closure review and decide whether Phase 2 core contracts work may begin.

