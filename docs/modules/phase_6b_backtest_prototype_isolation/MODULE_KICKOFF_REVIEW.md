# Module Kickoff Review: Phase 6B Backtest Prototype Isolation

This document records the ChatGPT-approved Phase 6B kickoff. It is not Codex's independent strategic judgment.

## Purpose

Create a safe, manual-only prototype isolation plan for future backtest engine experiments.

Phase 6B prepares how future manual prototypes should be run. It does not run prototypes, install frameworks, implement a backtest engine, or select an engine.

## Upstream

- Phase 3 data contracts
- Phase 5 market rules
- Phase 6A backtest engine candidate evaluation

## Downstream

- Phase 6C manual prototype runs
- Phase 7 alpha/factor validation
- Phase 8 strategy tournament

## Scope

- no framework installation
- no real backtesting
- no final engine selection
- no broker/live trading path
- static prototype plans
- manual-only tool documentation
- fake fixture snapshot helper

## Success Criteria

- prototype plans validate
- first-wave order is vectorbt, Backtrader, RQAlpha
- live-trading-capable engines require isolation
- no plan allows CI execution
- no plan claims trading readiness or final selection
- validation passes with `python -m compileall src`
- validation passes with `python -m pytest`

