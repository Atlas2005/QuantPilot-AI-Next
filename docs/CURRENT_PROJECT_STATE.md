# Current Project State

## Project

QuantPilot-AI-Next / QuantPilot-AI 2.0.

## Current Phase

Phase 6C-3A: RQAlpha license, maintenance, and isolation preflight, implemented by Codex and pending ChatGPT closure review.

## Current Contents

Step 0A through Phase 6C-2 are completed.

Phase 6C-2 manual Backtrader prototype is completed and pushed.

Phase 6C-3A adds RQAlpha preflight metadata, review documentation, and validation tests. It does not install, import, or run RQAlpha.

The repository is still not trading-ready.

No final backtest engine is selected.

No RQAlpha install was performed.

No RQAlpha prototype was run.

No production adapter exists.

No real market data was used.

No broker/order/live path exists.

## Current Prohibitions

- do not fetch market data
- do not call external APIs
- do not install or import RQAlpha without ChatGPT approval
- do not install prototype packages outside isolated prototype environments
- do not add prototype framework dependencies to `pyproject.toml`
- do not run RQAlpha prototype before Phase 6C-3B approval
- do not implement production backtest adapters
- do not implement strategy, alpha/factor, portfolio, model, broker, live order, or agent workflows
- do not mark anything trading-ready
- do not claim profitability
- do not copy old v2 source code

## Next Expected Action

ChatGPT should perform Phase 6C-3A module closure review. Do not move to isolated RQAlpha prototype until approved.
