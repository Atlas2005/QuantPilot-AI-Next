# Market Reality Sandbox Architecture

The Market Reality Sandbox is the R1 target for evaluating whether a trade candidate can survive A-share market reality before any paper or capital test.

R1 defines the architecture only. It does not run real backtests, submit orders, fetch real data, connect brokers, or produce trading-ready output.

## Required Market Reality Coverage

The sandbox target must model or explicitly block on:

- T+1 for ordinary A-shares
- possible T+0 eligible instruments where applicable
- 100-share lot rules where applicable
- price limits
- ST, suspension, and delisting risk flags
- transaction costs
- slippage
- liquidity and capacity
- partial fills
- rejected orders
- data latency and timestamp audit
- provider failure

## Sandbox Inputs

The sandbox should eventually consume:

- approved historical market data
- approved market rule profiles
- current capital and account permission snapshots
- signal candidates
- portfolio exposure
- cost and slippage assumptions
- timestamped data provenance

## Sandbox Outputs

The sandbox should produce:

- feasible trade candidates
- rejected trade candidates with reasons
- sandbox order drafts
- cost and slippage estimates
- fill-risk and liquidity warnings
- market-rule violations
- timestamp audit records

## Relationship To External Engines

RQAlpha, vectorbt, Backtrader, Hikyuu, and Qlib may be used as prototypes or benchmarks later. They cannot substitute for QuantPilot-specific A-share feasibility gates.

The sandbox should wrap or benchmark external engines only after isolated prototype review, dependency review, and contract tests.

## Safety Boundary

Sandbox order drafts are not real orders. They must not be routed to brokers or execution APIs in R1.
