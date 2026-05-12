# Current Project State

## Project

QuantPilot-AI-Next / QuantPilot-AI 2.0.

## Current Phase

Phase 6C-1: manual vectorbt local-fixture prototype, implemented by Codex and pending ChatGPT closure review.

## Current Contents

Step 0A through Phase 6B are completed.

Phase 6B backtest prototype isolation plan is completed and pushed.

Phase 6C-1 adds manual-only vectorbt probe scripts, module review records, and a documented prototype result using the fake Phase 3 local fixture.

The repository is still not trading-ready.

No final backtest engine is selected.

No production vectorbt adapter exists.

No real market data was used.

No broker/order/live path exists.

## Current Prohibitions

- do not fetch market data
- do not call external APIs
- do not add vectorbt or other prototype frameworks to project dependencies
- do not implement production backtest adapters
- do not implement strategy, alpha/factor, portfolio, model, broker, live order, or agent workflows
- do not mark anything trading-ready
- do not claim profitability
- do not copy old v2 source code

## Next Expected Action

ChatGPT should perform Phase 6C-1 module closure review. Do not move to Backtrader, RQAlpha, or adapter implementation until approved.
