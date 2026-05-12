# Factor Candidate Library

Phase 7C creates a conservative factor candidate library foundation. It is metadata and toy computation only.

This library does not prove alpha, profitability, statistical significance, or trading readiness.

## Included Categories

- price momentum
- mean reversion
- volatility
- volume / liquidity

## Toy Factors

- `close_to_close_momentum_1d`
- `close_to_close_reversal_1d`
- `toy_range_volatility_1d`
- `toy_volume_change_1d`

Every candidate is scoped to fake fixtures only. Every candidate remains toy or not evaluated. No candidate is validated. No candidate is trading-ready.

## Why This Does Not Prove Alpha

The current fixture is tiny and fake. The computations are shape checks for factor interfaces and validation workflows. They do not include real data, OOS validation, walk-forward validation, transaction costs, A-share execution rules, capacity checks, liquidity proof, or paper feedback.

## Future Relationship

Future phases may evaluate:

- larger historical datasets
- Alphalens Reloaded
- quantstats
- empyrical / empyrical-reloaded
- Qlib
- OOS / walk-forward validation
- strategy tournament

Any future integration must pass ChatGPT review, dependency review, license/commercial review, adapter boundaries, and evidence gates.

## Phase 7D External Analytics Preflight

Factor candidates must pass validation policy before external analytics can be meaningful.

External analytics preflight does not validate candidates. It only records tool roles, risks, and future prototype boundaries.

## Phase 7E Real Data Readiness

No factor candidate may move beyond toy or not-evaluated status until the real-data readiness gate is satisfied.

## Next Likely Phases

- Phase 7D external analytics preflight
- Phase 7E factor validation on larger local fixture or controlled real data
- Phase 8 strategy tournament later
