# Current Project State

## Project

QuantPilot-AI-Next / QuantPilot-AI 2.0.

## Current Phase

Phase 6C-3B: isolated RQAlpha prototype probe, implemented by Codex and pending ChatGPT closure review.

## Current Contents

Step 0A through Phase 6C-3A are completed.

Phase 6C-3A RQAlpha preflight is completed and pushed.

Phase 6C-3B adds an isolated RQAlpha probe, module review records, and a documented prototype result. RQAlpha was installed and imported only inside `.venv-prototypes/rqalpha/`.

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
- do not commercialize, vendor, copy, or integrate RQAlpha before license review
- do not run deeper RQAlpha work without ChatGPT approval
- do not implement production backtest adapters
- do not implement strategy, alpha/factor, portfolio, model, broker, live order, or agent workflows
- do not mark anything trading-ready
- do not claim profitability
- do not copy old v2 source code

## Next Expected Action

ChatGPT should perform Phase 6C-3B module closure review. Do not move to adapter implementation or final engine selection until approved.
