# Open-Source Integration Enforcement

R1.1 makes the R1 open-source-first requirement enforceable through a machine-readable decision table, loader code, and tests.

R1 was an architecture reset. It identified integration candidates and reset the project direction, but it did not complete external integration, approve dependencies, or select final engines. R1.1 adds guardrails so future phases cannot quietly reinvent generic infrastructure without reviewing mature external projects first.

## Why Integration Is Mandatory Where Practical

QuantPilot-AI-Next is profit-first and integration-first. The 30-day Capital-Test MVP should spend project effort on A-share market reality, capital/account constraints, safety gates, validation, adapters, and auditability rather than rebuilding common quant infrastructure from scratch.

Mature external projects should be reviewed first for:

- data provider access
- market calendars
- backtest engines
- factor analytics
- risk and performance metrics
- portfolio/accounting models
- agent orchestration
- order simulation benchmarks

## What Can Be Self-Built

Self-built code remains appropriate for:

- contracts
- adapters
- glue code
- A-share specific market reality constraints
- account and capital constraints
- safety gates
- orchestration boundaries
- validation layers
- audit records

These layers are where QuantPilot's project-specific value lives.

## What Must Not Be Reinvented

Generic infrastructure must not be rebuilt as QuantPilot-owned core unless a future review explicitly rejects mature alternatives with evidence.

The R1.1 decision table marks these generic areas as `must_not_reinvent`:

- `market_calendar`
- `backtest_engine`
- `factor_analysis`
- `risk_metrics`
- `portfolio_accounting`

The table lives at:

```text
data/integration_reset/open_source_integration_decision_table.json
```

## Future Phase Rule

Before building a new module, future phases must check the decision table and answer:

- which mature external projects were reviewed
- whether the module is generic infrastructure or project-specific glue
- where the adapter boundary sits
- why direct integration is not yet allowed
- what the next required action is

If a module is generic infrastructure, it must not become a pure self-build module.

## Capital-Test MVP Impact

This enforcement keeps the 30-day MVP focused on the shortest practical path to controlled capital-test readiness:

- wrap or benchmark proven tools where possible
- keep QuantPilot contracts stable
- add A-share market reality and capital/account constraints where external tools are incomplete
- preserve no-live-trading and no-broker boundaries
- produce auditable candidate and sandbox outputs

## R2 Market Reality Sandbox Requirement

R2 Market Reality Sandbox Contracts must stay contract/adapter-boundary focused.

R2 must not become a fully self-built backtest engine, risk engine, factor engine, market calendar, or portfolio accounting system. It should define the project-specific A-share and capital-aware contracts, then route generic infrastructure work through adapters, prototypes, or benchmarks against mature external libraries.
