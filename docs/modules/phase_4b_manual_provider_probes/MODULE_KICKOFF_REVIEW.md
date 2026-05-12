# Module Kickoff Review: Phase 4B Manual Provider Probes

This document records the ChatGPT-approved Phase 4B kickoff. It is not Codex's independent strategic judgment.

## Purpose

Run controlled manual probes for AkShare and Baostock only to evaluate whether tiny A-share daily OHLCV outputs can be mapped into the Phase 3 data contract.

## Upstream

- Phase 3 data contracts and local fixtures
- Phase 4A prototype harness

## Downstream

- provider comparison
- future data-source selection review
- future adapter review

## Scope

- manual probe scripts only
- raw output under ignored `local_artifacts/`
- docs summary without raw rows
- no production adapter
- no CI data fetching
- no raw data commit
- no final provider selection

## Prohibited Scope

- production adapter implementation
- CI market data fetching
- full-history downloads
- raw data commits
- token or secrets handling
- broker/live/order paths
- backtesting
- model training
- agent orchestration
- trading-readiness claims
- profitability claims

## Success Criteria

- scripts fail cleanly when provider packages are missing
- scripts can write local summaries under `local_artifacts/`
- raw outputs remain gitignored
- docs summarize provider probe outcomes without raw data rows
- validation passes with `python -m compileall src`
- validation passes with `python -m pytest`

