# P50A A-Share Market Reality Sandbox V1 Report

## Summary

P50A adds minimal executable candidate evaluation for A-share stock and ETF signals.

The new layer bridges factor or signal output toward tradable candidate decisions by applying lot sizing, cash capacity, sellable position, suspension, price-limit, liquidity participation, commission, stamp duty, and slippage checks.

## Market Reality Alignment

P50A reuses existing Market Reality Sandbox concepts:

- A-share 100-share lot handling
- suspension and price-limit awareness
- cash and sellable-position constraints
- explicit cost and slippage assumptions
- candidate-only evaluation with no live execution claim

It does not rewrite or replace `market_reality`.

## Scope Boundaries

P50A does not execute broker orders.

P50A does not create live orders, call broker APIs, fetch market data, or modify provider adapters.

P50A does not claim profitability.

P50A does not replace mature engines such as RQAlpha, vectorbt, or Backtrader. Those remain open-source integration candidates for future engine-backed workflows.

## Next Integration Path

P50A prepares later paper ledger and fill simulation integration by producing deterministic executable candidate decisions with explicit quantities, estimated notional, cost components, issues, warnings, and decision notes.
