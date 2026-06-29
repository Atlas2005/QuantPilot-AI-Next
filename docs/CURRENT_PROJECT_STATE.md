# Current Project State

## Project

QuantPilot-AI-Next / QuantPilot-AI 2.0.

## Current Phase

R1.1: Open-source Integration Enforcement Patch, implemented by Codex and pending ChatGPT closure review.

## Current Contents

Step 0A through Phase 7F are completed.

R1 adds profit-first integration architecture docs, a multi-agent target architecture, Market Reality Sandbox architecture, Capital-Aware Fast Compounding Mode, an open-source replacement strategy, upstream dependency intelligence target, a 30-day Capital-Test MVP plan, a machine-readable integration reset matrix, and standard-library validation helpers.

R1.1 adds enforceable open-source integration guardrails through a machine-readable decision table, standard-library loader/validator, tests, and documentation.

R1 was architecture reset, not full external integration.

The repository is still not trading-ready.

No data source is approved.

No manual provider probe was run during implementation.

No real data was fetched.

No real alpha is proven.

No external analytics package is installed.

No final backtest engine is selected.

No production adapter exists.

No broker/order/live path exists.

No R1 candidate is approved for installation, raw data fetching, broker connection, live trading, or real order execution.

Future modules must check mature open-source candidates before self-building generic infrastructure. R2 must stay contract/adapter-boundary focused, especially for Market Reality Sandbox contracts.

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
- do not claim profitability
- do not copy old v2 source code

## Next Expected Action

ChatGPT should perform R1.1 module closure review. The next recommended phase is R2 Market Reality Sandbox Contracts, with strict adapter boundaries to external engines/libraries and no self-built backtest, factor, risk, calendar, or portfolio accounting core. Do not move to real data validation, dependency installation, broker connectivity, live trading, or profitability claims until explicitly approved.
