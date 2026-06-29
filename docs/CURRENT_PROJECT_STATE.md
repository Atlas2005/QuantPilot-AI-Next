# Current Project State

## Project

QuantPilot-AI-Next / QuantPilot-AI 2.0.

## Current Phase

R6: Controlled Provider Adapter Probe Plan, implemented by Codex and pending ChatGPT closure review.

## Current Contents

Step 0A through Phase 7F are completed.

R1 adds profit-first integration architecture docs, a multi-agent target architecture, Market Reality Sandbox architecture, Capital-Aware Fast Compounding Mode, an open-source replacement strategy, upstream dependency intelligence target, a 30-day Capital-Test MVP plan, a machine-readable integration reset matrix, and standard-library validation helpers.

R1.1 adds enforceable open-source integration guardrails through a machine-readable decision table, standard-library loader/validator, tests, and documentation.

R1 was architecture reset, not full external integration.

R2 adds a Market Reality Sandbox contract and validation layer for A-share trading reality, capital/account constraints, sandbox order drafts, fill assumptions, costs, slippage, provider failure, data latency, and timestamp audit assumptions.

R3 adds a Provider-Sandbox Fixture Bridge that converts explicitly local mock/fixture/probe provider snapshots into sandbox fixture inputs after validation.

R4 adds a Controlled Provider Probe Execution Gate that decides whether mock, dry-run, or controlled provider probe requests are allowed and whether their output can later be considered for R3 bridge conversion.

R5 adds a local mock-only run that connects R4 gate request, R4 gate decision, R3 provider probe snapshot, R3 bridge conversion, and R2 `SandboxFixtureInput`.

R6 adds a controlled provider adapter probe plan and validator that define the review evidence required before any future provider adapter probe can be submitted to the R4 gate.

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

R2 does not add real data, broker integration, live trading, order execution, or full backtest/risk/factor/calendar/accounting engines.

R3 uses local mock/fixture/probe data only. It does not add real market data ingestion, broker integration, live trading, order execution, or a self-built data provider.

R4 does not fetch real market data, call provider APIs, add broker integration, live trading, order execution, or reinvent data providers.

R5 uses local mock fixtures only. It does not fetch real market data, call provider APIs, add broker integration, live trading, order execution, write production data assets, or reinvent data providers.

R6 uses a local mock plan fixture only. It does not fetch real market data, call provider APIs, implement a provider adapter, add broker integration, live trading, order execution, write production data assets, or reinvent data providers.

Future modules must check mature open-source candidates before self-building generic infrastructure. R6 stays plan/validation focused and keeps AkShare, Baostock, Tushare, and similar projects as adapter candidates.

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

ChatGPT should perform R6 module closure review. The next phase may define a real small-sample data gate only after review. Do not move to real data ingestion, dependency installation, provider API calls, broker connectivity, live trading, order execution, production data assets, or profitability claims until explicitly approved.
