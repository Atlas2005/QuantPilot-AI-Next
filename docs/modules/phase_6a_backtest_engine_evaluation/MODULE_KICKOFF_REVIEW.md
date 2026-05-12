# Module Kickoff Review: Phase 6A Backtest Engine Evaluation

This document records the ChatGPT-approved Phase 6A kickoff. It is not Codex's independent strategic judgment.

## Purpose

Create a structured evaluation foundation for future backtest engine selection.

Phase 6A evaluates candidates at metadata, capability, risk, and fit-assessment level only.

## Upstream

- data contracts
- market rules
- candidate registry
- provider probes

## Downstream

- Phase 6B manual prototype comparison
- Phase 7 alpha/factor validation
- Phase 8 strategy tournament

## Scope

- no framework installation
- no real backtesting
- no final engine selection
- no broker/live trading path
- local JSON candidate metadata
- standard-library validators and summaries

## Success Criteria

- candidate metadata loads
- required fields and enum values are validated
- no candidate is approved for adapter in Phase 6A
- no candidate is marked trading-ready
- live-trading-capable engines are flagged with non-low live trading risk
- validation passes with `python -m compileall src`
- validation passes with `python -m pytest`

