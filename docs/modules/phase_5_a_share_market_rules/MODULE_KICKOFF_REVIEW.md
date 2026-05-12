# Module Kickoff Review: Phase 5 A-Share Market Rule Foundation

This document records the ChatGPT-approved Phase 5 kickoff. It is not Codex's independent strategic judgment.

## Purpose

Create a source-versioned, configurable A-share market rule foundation that can validate local order-intent shapes against basic A-share constraints.

Phase 5 is a rule-validation foundation only. It is not a broker, execution engine, backtest engine, or trading-ready system.

## Upstream

- Phase 3 data contracts
- Phase 4A prototype harness
- Phase 4B manual provider probes

Phase 4B provider probes were inconclusive, so Phase 5 must not depend on real provider data.

## Downstream

- backtest engine evaluation
- strategy tournament
- paper feedback

## Core Requirement

Rules must be source-versioned and configurable. Current profile values are provisional and must not be treated as permanent truth.

## Prohibited Scope

- broker integration
- live trading
- real order submission
- backtesting
- strategy logic
- alpha/factor calculation
- portfolio optimization
- model training
- agent orchestration
- market data fetching
- external API calls
- external framework imports
- trading-readiness claims
- profitability claims

## Success Criteria

- market rule profile includes required metadata and rule sections
- profile validation requires manual review metadata
- local `OrderIntent` validation checks lot size, T+1, price sanity, configurable price limits, suspension, liquidity, and cost placeholders
- fee/slippage/special cases remain explicitly deferred
- no broker/execution/live order path exists
- `python -m compileall src` passes
- `python -m pytest` passes

