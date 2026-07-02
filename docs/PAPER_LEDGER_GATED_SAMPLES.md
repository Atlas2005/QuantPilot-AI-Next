# Paper Ledger Fed By Provider Samples

R14 connects provider samples to a deterministic paper ledger dry path.

## Why R14 Exists

R13 can select an optional provider, fetch fake/offline normalized sample bars, and report small-sample quality warnings. R14 adds the next dry-path step: a sample can provide context for a minimal paper ledger order and position update.

This is still not trading. It is a local accounting exercise for reviewed samples.

## Flow

The intended path is:

provider selector -> sample fetch -> sample quality warnings -> paper ledger dry path

The ledger no longer requires `gate_passed=True` before accepting a coherent paper order. A failed quality gate is reported as `sample_quality_gate_not_passed`; malformed orders, insufficient paper cash, and insufficient paper position still reject the paper fill.

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
