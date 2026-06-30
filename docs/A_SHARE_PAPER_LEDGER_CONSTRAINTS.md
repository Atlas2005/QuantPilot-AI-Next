# A-share Paper Ledger Constraints

R15 hardens the paper ledger dry path with minimal A-share market reality constraints.

## Why R15 Exists

R14 introduced a deterministic paper ledger that can update cash and positions after a gated provider sample. R15 adds the first A-share-specific constraints so the dry path becomes more capital/account-aware and closer to the Market Reality Sandbox target.

This remains a sandbox dry path. It is not live trading and does not place real orders.

## Modeled Constraints

R15 models:

- 100-share board lot for buy and sell orders.
- T+1 sellable quantity through an explicit `sellable_positions` input.
- Commission using a configurable commission rate.
- Minimum commission.
- Stamp tax on sells.
- Deterministic slippage.

Slippage and cost calculations use a deterministic 4-decimal rounding policy.

## Market Reality Sandbox Fit

The constrained ledger fits the project path:

provider selector -> sample fetch -> small sample gate -> paper ledger dry path -> A-share constraints

The helper rejects orders before execution if the gate did not pass, if board-lot rules fail, if cash is insufficient after fees and slippage, or if sellable quantity is insufficient under the simplified T+1 rule.

## Limitations

- Simplified fee model.
- No exchange-specific exceptions.
- No corporate actions.
- No partial fills.
- No live orders.
- No broker integration.
- No strategy engine.
- No RQAlpha execution.

## Future Path

- R16: multi-day paper ledger replay from gated samples.
- R17: RQAlpha dry-run fixture once dependency and format are ready.
- R18: small-capital validation readiness gate.
