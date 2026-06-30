# Paper Ledger Fed By Gated Provider Samples

R14 connects gated provider samples to a deterministic paper ledger dry path.

## Why R14 Exists

R13 can select an optional provider, fetch fake/offline normalized sample bars, and pass those bars through the small-sample gate. R14 adds the next dry-path step: a gated sample can now authorize a minimal paper ledger order and position update.

This is still not trading. It is a local accounting exercise for reviewed samples.

## Flow

The intended path is:

provider selector -> sample fetch -> small sample gate -> paper ledger dry path

The ledger requires `gate_passed=True` before accepting any paper order. If the gate did not pass, the ledger rejects the order and leaves cash and positions unchanged.

## Capital / Account Awareness

R14 adds minimal capital/account checks:

- account cash must be non-negative
- buy orders require enough paper cash
- sell orders require enough paper position
- invalid symbol, quantity, or price is rejected
- input account snapshots are not mutated in place

This supports profit-first and capital/account-aware validation without creating live execution.

## Market Reality Sandbox Fit

R14 is a Market Reality Sandbox dry path. It uses deterministic limit-price fills only so the project can verify cash and position updates before adding more realistic constraints.

## Limitations

- No commission.
- No slippage.
- No T+1 rule.
- No partial fills.
- No live orders.
- No broker integration.
- No strategy engine.
- No RQAlpha run.

## Future Path

- R15: RQAlpha dry-run fixture once dependency and data format are ready.
- R16: A-share lot-size/T+1/capital constraints in paper ledger.
- R17: multi-day paper ledger replay from gated samples.
