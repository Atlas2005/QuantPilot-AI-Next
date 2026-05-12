# Module Kickoff Review: Phase 1 Candidate Registry

This document records the ChatGPT-approved Phase 1 kickoff. It is not Codex's independent strategic judgment.

## Purpose

Create a structured open-source candidate registry so QuantPilot-AI 2.0 can evaluate external projects before building major modules from scratch.

Phase 1 is registry-only. It does not integrate external frameworks.

## Upstream

- Step 0A planning package
- Step 0B clean skeleton and minimal CI

## Downstream

- core contracts
- data contracts
- data-source prototypes
- backtest engine evaluation

## Open-Source Decision

No quant, data-source, broker, ML, or agent framework is installed, imported, selected, or integrated in this phase.

## Allowed Scope

- Python standard library only
- existing pytest dev dependency
- static candidate metadata file
- lightweight schema validation
- tests for registry loading and metadata completeness

## Prohibited Scope

- market data fetching
- external API calls
- framework installation
- framework imports
- data adapters
- backtests
- model training
- agent orchestration
- broker connection
- live trading or order execution paths
- trading-readiness claims
- profitability claims
- final technical selections

## Success Criteria

- candidate JSON loads successfully
- required fields are validated
- enum values are validated
- candidate names are unique
- no candidate is marked `approved_for_adapter`
- all candidates remain conservative for Phase 1
- validation passes with `python -m compileall src`
- validation passes with `python -m pytest`

