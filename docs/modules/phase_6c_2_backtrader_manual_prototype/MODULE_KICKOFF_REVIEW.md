# Phase 6C-2 Module Kickoff Review

This document records the ChatGPT-approved kickoff review for Phase 6C-2. Codex is not the project architect and is only implementing the scoped manual Backtrader prototype.

## Purpose

Run one controlled, manual-only Backtrader prototype using the fake Phase 3 local fixture.

## Upstream

- Phase 3 data contracts
- Phase 5 market rules
- Phase 6A engine evaluation
- Phase 6B prototype isolation plan
- Phase 6C-1 vectorbt manual prototype
- Phase 6C-1.1 environment isolation policy

## Downstream

- Backtrader closure review
- possible RQAlpha prototype later
- future adapter decision

## Scope

Allowed:

- install Backtrader only inside `.venv-prototypes/backtrader/`
- run one manual probe against `data/fixtures/a_share_daily_sample_valid.csv`
- write local artifacts only under `local_artifacts/backtest_prototypes/backtrader/`
- summarize results in docs

Prohibited:

- no real market data
- no provider/API use
- no production adapter
- no final engine selection
- no broker/live trading path
- no strategy tournament
- no model or agent work

## Success Criteria

- Backtrader runs only from the isolated prototype environment.
- The fake fixture is converted to a local Backtrader-compatible CSV.
- The toy strategy runs or fails safely with errors captured.
- Review packet records environment path, install location, validation, risks, and next step.
