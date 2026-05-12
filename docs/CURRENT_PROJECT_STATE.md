# Current Project State

## Project

QuantPilot-AI-Next / QuantPilot-AI 2.0.

## Current Phase

Phase 6C-1.1: prototype environment isolation policy, implemented by Codex and pending ChatGPT closure review.

## Current Contents

Step 0A through Phase 6C-1 are completed.

Phase 6C-1 manual vectorbt prototype is completed and pushed.

Phase 6C-1.1 adds policy, helper scripts, and tests requiring future external-framework prototypes to run in isolated `.venv-prototypes/<tool-name>/` environments.

The repository is still not trading-ready.

No final backtest engine is selected.

No production adapter exists.

No new framework test was run in this patch.

No broker/order/live path exists.

## Current Prohibitions

- do not fetch market data
- do not call external APIs
- do not install or uninstall packages without explicit approval
- do not add prototype framework dependencies to `pyproject.toml`
- do not run Backtrader, RQAlpha, Qlib, or deeper vectorbt prototypes in the main project environment
- do not implement production backtest adapters
- do not implement strategy, alpha/factor, portfolio, model, broker, live order, or agent workflows
- do not mark anything trading-ready
- do not claim profitability
- do not copy old v2 source code

## Next Expected Action

ChatGPT should perform Phase 6C-1.1 module closure review. Do not start Backtrader/RQAlpha/Qlib prototype work until approved.
