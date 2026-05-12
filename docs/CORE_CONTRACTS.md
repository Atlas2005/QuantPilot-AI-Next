# Core Contracts

Core contracts define the boundaries future modules must respect before QuantPilot-AI 2.0 integrates external tools or implements domain logic.

## Purpose

The contract layer describes metadata, categories, status, scope warnings, and minimal descriptive methods for future integration points:

- data sources
- data validators
- market rules
- backtest engines
- factor engines
- portfolio engines
- agent skills
- reporting
- safety

## Why Contracts Come Before Adapters

Contracts make external integrations replaceable. Future frameworks should connect through adapters that satisfy these contracts rather than directly shaping the core system.

## External Framework Integration Rule

External projects from the candidate registry may later enter through adapters and contract tests after ChatGPT-led review.

Phase 2 does not install, import, select, or integrate any framework.

## Not Implementations

These contracts do not:

- fetch data
- validate real datasets
- implement A-share market rules
- run backtests
- calculate factors
- optimize portfolios
- train models
- orchestrate agents
- connect brokers
- submit orders

## Current Limitations

The contracts are intentionally minimal and draft-status. They define shape and metadata only.

## Next Phase Relationship

Phase 3 may define data contracts and local fixtures after ChatGPT closure review approves moving forward.

