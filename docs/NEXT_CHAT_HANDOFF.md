# Next Chat Handoff

## Project Goal

QuantPilot-AI 2.0 is an open-source-first, adapter-first, contract-first, A-share-first AI quant integration platform designed to evolve toward a profitable AI quantitative trading platform through evidence-gated research.

## Current Phase

Phase 7F: controlled provider retry readiness probe, implemented by Codex and pending ChatGPT closure review.

## Completed Work

Step 0A through Phase 7E are completed.

Phase 7F created:

- `src/quantpilot_core/data/provider_probe_readiness.py`
- `data/provider_probe_readiness/provider_probe_policy_v0_1.json`
- `tools/manual_provider_probes/run_akshare_retry_probe.py`
- `tools/manual_provider_probes/run_baostock_retry_probe.py`
- `docs/CONTROLLED_PROVIDER_RETRY_PROBE.md`
- `tests/data/test_provider_probe_readiness.py`
- Phase 7F module kickoff and closure draft docs

Manual probes were not run during implementation. No provider package was installed, no real data was fetched, no provider was approved, and no adapter was created.

## Current Prohibitions

- do not fetch market data without a later approved manual probe instruction
- do not call external APIs during automated validation
- do not install packages
- do not create provider API clients or token handling in `src/`
- do not commit raw provider data
- do not run real factor validation
- do not claim alpha, profitability, or statistical significance
- do not run real backtests
- do not implement strategy tournament
- do not implement production adapters
- do not implement broker/live/order or agent workflows
- do not mark anything trading-ready

## Next Recommended Step

ChatGPT should perform Phase 7F closure review.

Do not move to larger real-data validation, external analytics install, strategy tournament, or real alpha claims until approved.

## Key Decisions

- Phase 7F is a controlled readiness probe layer, not provider approval.
- Manual probe scripts are not test dependencies and are not run in CI.
- Raw provider data must not be committed.
- Successful provider probes do not prove alpha.
- Codex is not the project architect.

## Role Split

ChatGPT is the architecture lead and strategic reviewer.

Codex creates files, organizes docs, runs safe validation commands, and produces review packets.

ChatGPT, not Codex, performs module closure review.
