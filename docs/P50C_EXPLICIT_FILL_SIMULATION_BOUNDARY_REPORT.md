# P50C Explicit Fill Simulation Boundary Report

## Summary

P50C adds an explicit fill simulation boundary after paper ledger dry-run.

It separates executable quantity from simulated filled quantity so later evaluation can distinguish a candidate that was tradable from a candidate that was actually fillable under deterministic volume and slippage assumptions.

## Boundary

P50C does not execute live broker orders.

P50C does not create live orders.

P50C does not mutate the paper ledger.

P50C does not fetch market data.

P50C does not modify provider adapters.

P50C does not claim profitability.

## Simulation Model

The boundary accepts a dry-run accepted instruction context and computes:

- full, partial, none, or rejected fill status
- simulated filled quantity
- unfilled quantity
- slippage-adjusted fill price
- gross notional
- commission, stamp duty, and slippage cost
- net cash impact

It remains deterministic and offline.

## Alignment

P50C aligns with earlier fill concepts from the historical gate-pruning/tradability work, but it does not expose that old module as the new public interface.

This prepares later cost-after-fill profitability evaluation while preserving the existing paper ledger dry-run and executable candidate modules.
