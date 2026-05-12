# Module Kickoff Review: Phase 2 Core Contracts

This document records the ChatGPT-approved Phase 2 kickoff. It is not Codex's independent strategic judgment.

## Purpose

Create the core contract layer that defines how future data sources, validators, market rules, backtest engines, factor engines, portfolio engines, and agent skills will connect to QuantPilot-AI 2.0.

Phase 2 defines interfaces and metadata only. It does not implement real adapters or trading logic.

## Upstream

- Step 0A planning package
- Step 0B clean skeleton and minimal CI
- Phase 1 open-source candidate registry

## Downstream

- data contracts
- local fixtures
- data-source prototypes
- market rules
- backtest engine evaluation

## Open-Source Decision

No external quant, data, broker, ML, or agent framework is installed, imported, selected, or integrated in this phase.

## Allowed Scope

- Python standard library only
- existing pytest dev dependency
- dataclasses
- abc
- typing
- enum
- minimal interface and metadata definitions
- tests for contract shape and safety boundaries

## Prohibited Scope

- market data fetching
- external API calls
- new package installation
- external framework imports
- data adapters
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
- old v2 source-code copying

## Success Criteria

- contract metadata is serializable
- base contract describes metadata and scope warnings
- each scoped contract class can be instantiated
- categories match their intended boundaries
- contract methods are descriptive only
- no contract marks anything trading-ready
- `python -m compileall src` passes
- `python -m pytest` passes

