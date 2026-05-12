# Current Project State

## Project

QuantPilot-AI-Next / QuantPilot-AI 2.0.

## Current Phase

Phase 7F: controlled provider retry readiness probe, implemented by Codex and pending ChatGPT closure review.

## Current Contents

Step 0A through Phase 7E are completed.

Phase 7E real-data readiness gate is completed and pushed.

Phase 7F adds controlled provider retry readiness policy metadata, standard-library summary validation helpers, manual-only AkShare and Baostock retry probe scripts, docs, and tests.

The repository is still not trading-ready.

No data source is approved.

No manual provider probe was run during implementation.

No real data was fetched.

No real alpha is proven.

No external analytics package is installed.

No final backtest engine is selected.

No production adapter exists.

No broker/order/live path exists.

## Current Prohibitions

- do not fetch market data unless a later approved manual probe explicitly allows it
- do not call external APIs during automated validation
- do not install or uninstall packages
- do not add external dependencies to `pyproject.toml`
- do not create provider clients or API token handling in `src/`
- do not write real data files under tracked paths
- do not commit raw provider data
- do not run real factor validation
- do not claim alpha, profitability, or statistical significance
- do not run real backtests
- do not implement strategy tournament
- do not implement production adapters
- do not implement model, broker, live order, or agent workflows
- do not mark anything trading-ready
- do not copy old v2 source code

## Next Expected Action

ChatGPT should perform Phase 7F module closure review. Do not move to larger real-data validation, external analytics install, strategy tournament, or real alpha claims until approved.
