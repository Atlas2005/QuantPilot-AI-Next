# Next Chat Handoff

## Project Goal

QuantPilot-AI 2.0 is an open-source-first, adapter-first, contract-first, A-share-first AI quant integration platform designed to evolve toward a profitable AI quantitative trading platform through evidence-gated research.

## Current Phase

Phase 4B: manual provider probes, implemented and run by Codex pending ChatGPT closure review.

## Completed Work

Step 0A through Phase 4A are completed.

Phase 4B created manual-only probe scripts for AkShare and Baostock under `tools/manual_provider_probes/`.

Both probes were run. Provider packages were already available locally, so no package install was performed in this phase. Both probes failed safely because provider/network access was unavailable, produced zero rows, and wrote only ignored local summaries under `local_artifacts/`.

## Current Prohibitions

- do not commit raw market data
- do not add provider packages to `pyproject.toml`
- do not implement production data-source adapters
- do not create token or secrets handling
- do not run backtests
- do not implement strategy, factor, portfolio, model, broker, live order, or agent workflows
- do not mark anything trading-ready
- do not claim profitability

## Next Recommended Step

ChatGPT should perform Phase 4B closure review.

Do not move to provider adapter implementation until approved.

## Key Decisions

- AkShare and Baostock were the only providers probed.
- Tushare, OpenBB, SimTradeData, and other tools remain deferred for this phase.
- Probe failure is acceptable if safely captured.
- Raw provider outputs stay in ignored `local_artifacts/`.
- Codex is not the project architect.

## Role Split

ChatGPT is the architecture lead and strategic reviewer.

Codex creates files, organizes docs, runs safe validation commands, and produces review packets.

ChatGPT, not Codex, performs module closure review.

