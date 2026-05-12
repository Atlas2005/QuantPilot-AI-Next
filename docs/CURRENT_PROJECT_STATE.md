# Current Project State

## Project

QuantPilot-AI-Next / QuantPilot-AI 2.0.

## Current Phase

Phase 4B: manual AkShare and Baostock provider probes, implemented and run by Codex pending ChatGPT closure review.

## Current Contents

Step 0A planning package is completed.

Step 0B clean skeleton and minimal CI is completed.

Phase 1 open-source candidate registry is completed.

Phase 1.1 candidate registry refresh is completed.

Phase 2 core contracts is completed.

Phase 3 data contracts and local fixtures is completed.

Phase 4A controlled data-source prototype harness is completed and pushed.

Phase 4B adds manual provider probe scripts and docs-only probe summaries for AkShare and Baostock.

The repository is still not trading-ready.

Provider probes are manual-only. No production data-source adapter exists.

## Current Prohibitions

- do not commit raw market data
- do not add provider packages to project dependencies
- do not fetch large datasets or full market history
- do not implement data-source adapters
- do not create token or secrets handling
- do not run backtests
- do not implement trading, strategy, factor, portfolio, model, broker, live order, or agent workflows
- do not mark anything trading-ready
- do not claim profitability
- do not copy old v2 source code

## Next Expected Action

ChatGPT should perform Phase 4B module closure review. Do not move to provider adapter implementation until approved.

