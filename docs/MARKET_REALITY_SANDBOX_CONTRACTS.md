# Market Reality Sandbox Contracts

R2 adds the Market Reality Sandbox contract layer.

This phase defines standard-library Python dataclasses, enums, and validation helpers for A-share trading reality, capital/account constraints, cost assumptions, slippage assumptions, data latency, provider failure, timestamp audit, and sandbox order-draft feasibility.

R2 does not implement a full simulator, backtest engine, risk engine, factor analysis engine, market calendar system, portfolio accounting engine, broker integration, live trading, or order execution path.

## Added Contracts

The R2 contract layer lives under:

```text
src/quantpilot_core/market_reality/
```

It defines:

- `SandboxScenario`
- `InstrumentTradingProfile`
- `ExecutionConstraint`
- `TradingCalendarAssumption`
- `CostModel`
- `SlippageModel`
- `OrderDraft`
- `FillSimulation`
- `SandboxResult`
- `SandboxRejectionReason`
- `DataLatencyAssumption`
- `ProviderFailureAssumption`
- `AccountConstraint`
- `CapitalConstraint`

## Covered Reality Assumptions

The contracts and validation helpers require explicit fields for:

- A-share T+1 constraints
- T+0 eligibility markers where applicable
- 100-share lot constraints
- price limit up/down assumptions
- suspension
- ST and delisting risk flags
- cash availability
- account permission constraints
- commission
- stamp duty
- transfer fee
- slippage
- partial fills
- rejected orders
- provider failure
- data latency
- timestamp audit assumptions

## R1.1 Integration Enforcement

R2 respects the R1.1 open-source integration enforcement rule.

Generic infrastructure must not be reinvented. Data providers, market calendars, backtest engines, factor analytics, risk metrics, and portfolio accounting should continue to be reviewed through mature open-source candidates before custom implementation.

R2 self-built code is limited to contracts, validation helpers, A-share specific market reality constraints, account/capital constraints, safety gates, and adapter boundaries.

## External Adapter Boundaries

External mature projects remain adapters, benchmarks, or future integration candidates, including:

- RQAlpha
- vectorbt
- Backtrader
- Hikyuu
- Qlib
- exchange_calendars
- empyrical
- quantstats

R2 does not select, install, import, or approve these packages. It only records where later adapters or benchmarks may connect.

## 30-Day Capital-Test MVP Support

The contract layer supports the 30-day Capital-Test MVP by creating auditable shapes for:

- sandbox scenarios
- instrument tradability assumptions
- capital/account feasibility
- sandbox order drafts
- simulated fill assumptions
- rejection reasons
- cost and slippage assumptions
- provider failure and timestamp audit assumptions

These shapes make later fixture-based sandbox validation possible without creating live trading or broker execution paths.

## Next Phase Direction

The next phase should move toward controlled adapter/probe integration or sandbox validation using fixtures.

It should not move to live trading, broker connectivity, real order execution, or full custom backtest/risk/factor/calendar/accounting engines.
