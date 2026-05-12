# Module Kickoff Review: Phase 4A Data-Source Prototype Harness

This document records the ChatGPT-approved Phase 4A kickoff. It is not Codex's independent strategic judgment.

## Purpose

Create a safe, manual-only framework for future controlled data-source prototypes.

Phase 4A prepares the harness and evaluation structure for future data-source experiments. It does not run those experiments.

## Upstream

- Step 0A planning
- Step 0B skeleton
- Phase 1 candidate registry
- Phase 1.1 candidate registry refresh
- Phase 2 core contracts
- Phase 3 data contracts and local fixtures

## Downstream

- Phase 4B manual data-source prototype runs
- Phase 5 A-share market rule engine
- Phase 6 backtest engine evaluation

## Scope

- manual-only prototype preparation
- adapter boundary placeholders only
- source field-mapping templates
- static evaluation checklist files and docs
- conservative candidate registry metadata update

## Prohibited Scope

- real data fetching
- external framework installation
- data-source adapter implementation
- external API calls
- package installation
- token or secrets handling
- external project cloning or source-code copying
- backtesting
- strategy logic
- factor calculation
- portfolio optimization
- model training
- agent orchestration
- broker connection
- live trading or order execution paths
- trading-readiness claims
- profitability claims

## Success Criteria

- prototype planning dataclasses exist and are manual/CI safe
- field-mapping templates exist and are provisional
- mapping validation checks template shape only
- SimTradeData is registry/reference only pending license review
- no external framework is imported or installed
- no real data fetching exists
- `python -m compileall src` passes
- `python -m pytest` passes

