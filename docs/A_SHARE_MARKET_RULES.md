# A-Share Market Rules

Phase 5 introduces a configurable A-share market rule validation foundation.

## Purpose

The market rule layer validates local `OrderIntent` objects against a source-versioned rule profile. It is intended to help future research and backtest evaluation reason about basic A-share constraints before any broker or execution path exists.

## Source-Versioned and Configurable

Rule profiles must include metadata:

- `profile_name`
- `profile_version`
- `market`
- `source_status`
- `source_notes`
- `effective_date`
- `last_reviewed`
- `manual_review_required`

Current profile values are provisional. They must be refreshed against official SSE, SZSE, and BSE sources before any real use.

## Covered in Phase 5

- buy lot size and increment checks
- positive quantity checks
- local T+1 same-day acquired sell warning/error
- price and previous close sanity checks
- configurable board price-limit percentages
- suspension blocking
- simple placeholder liquidity participation warning
- fee and slippage placeholder warnings

## Explicitly Deferred

- exact odd-lot sell handling
- IPO first trading days
- relisting
- no price-limit days
- temporary suspension details
- risk-warning rule changes
- current ST/delisting price-limit truth
- transaction cost accuracy
- slippage modeling
- corporate actions
- exchange calendar validation

## Not a Broker, Execution Engine, or Backtest Engine

Phase 5 does not submit orders, connect brokers, route execution, simulate fills, or run backtests.

## Not Trading-Ready

This layer is not trading-ready and does not provide financial advice. It is a local validation foundation only.

## Future Relationship

Future backtest engine evaluation may use these rules as a contract requirement, but only after ChatGPT closure review and future module kickoff approval.

