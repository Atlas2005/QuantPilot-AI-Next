# Current Project State

## Project

QuantPilot-AI-Next / QuantPilot-AI 2.0.

## Current Phase

Phase 6C-2: manual Backtrader local-fixture prototype, implemented by Codex and pending ChatGPT closure review.

## Current Contents

Step 0A through Phase 6C-1.1 are completed.

Phase 6C-1.1 prototype environment isolation policy is completed and pushed.

Phase 6C-2 adds a manual Backtrader probe, module review records, and a documented prototype result using the fake Phase 3 local fixture inside `.venv-prototypes/backtrader/`.

The repository is still not trading-ready.

No final backtest engine is selected.

No production adapter exists.

No real market data was used.

No broker/order/live path exists.

## Current Prohibitions

- do not fetch market data
- do not call external APIs
- do not install prototype packages outside isolated prototype environments
- do not add prototype framework dependencies to `pyproject.toml`
- do not run RQAlpha, Qlib, or deeper Backtrader/vectorbt prototypes without ChatGPT approval
- do not implement production backtest adapters
- do not implement strategy, alpha/factor, portfolio, model, broker, live order, or agent workflows
- do not mark anything trading-ready
- do not claim profitability
- do not copy old v2 source code

## Next Expected Action

ChatGPT should perform Phase 6C-2 module closure review. Do not start RQAlpha prototype or adapter implementation until approved.
