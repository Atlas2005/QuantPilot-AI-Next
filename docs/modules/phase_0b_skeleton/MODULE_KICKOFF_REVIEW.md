# Module Kickoff Review: Phase 0B Skeleton

This document records the ChatGPT-approved Step 0B kickoff. It is not Codex's independent strategic judgment.

## Approval Status

ChatGPT approved Step 0B before Codex implementation.

## Purpose

Create a clean, minimal, testable Python project skeleton and minimal CI for QuantPilot-AI 2.0.

## Upstream

Step 0A planning package.

## Downstream

- open-source candidate registry
- core contracts
- data contracts

## Open-Source Decision

No quant, data-source, broker, ML, or agent frameworks are integrated in Step 0B.

## Allowed Scope

- pytest as dev/test dependency only
- `compileall`
- `src` layout
- minimal Python package skeleton
- minimal GitHub Actions CI
- safety defaults
- review packet workflow

## Prohibited Scope

- market data
- external APIs
- brokers
- order submission
- live trading
- backtesting
- strategy logic
- factor logic
- model training
- agent orchestration
- old v2 source-code copying
- trading-readiness claims
- profitability claims

## Success Criteria

- package imports successfully
- safety flags default to false
- minimal contract placeholder works
- minimal registry placeholder works
- static forbidden-scope check passes over `src/`
- `python -m compileall src` passes
- `python -m pytest` passes
- CI runs compile and tests on GitHub Actions

