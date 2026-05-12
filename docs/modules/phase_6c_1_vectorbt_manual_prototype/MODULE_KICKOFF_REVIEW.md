# Module Kickoff Review: Phase 6C-1 Manual vectorbt Prototype

This document records the ChatGPT-approved Phase 6C-1 kickoff. It is not Codex's independent strategic judgment.

## Purpose

Run one controlled manual vectorbt prototype using the fake Phase 3 local fixture to evaluate whether vectorbt can consume the local daily OHLCV shape and produce a minimal non-production research result.

## Upstream

- Phase 3 data contracts
- Phase 5 market rules
- Phase 6A engine evaluation
- Phase 6B isolation plan

## Downstream

- vectorbt closure review
- possible Backtrader/RQAlpha later prototypes
- future adapter decision review

## Scope

- vectorbt manual prototype only
- fake Phase 3 fixture only
- no real market data
- no production adapter
- no final engine selection
- no broker/live trading path

## Success Criteria

- script fails cleanly if vectorbt is missing
- script uses only `data/fixtures/a_share_daily_sample_valid.csv`
- summary is written under ignored `local_artifacts/`
- docs summarize result without raw rows
- no `pyproject.toml` dependency change
- validation passes with `python -m compileall src`
- validation passes with `python -m pytest`

