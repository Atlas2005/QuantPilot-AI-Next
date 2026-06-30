# Paper Ledger Dry-Run Integration

R22 connects R21 paper-ledger candidate instructions to a deterministic in-memory dry-run path.

The dry-run validates candidate instructions, applies account and A-share constraints, estimates cash and position deltas, and returns a structured result. It does not write to the paper ledger, connect to a broker, place live orders, read account APIs, call DeepSeek, or perform network calls.

## Purpose

R21 stops at `PaperLedgerCandidateInstruction`. R22 is the next dry step: it answers whether those candidate instructions would pass a paper-ledger-style simulation under explicit account configuration.

This keeps the path layered:

AI action proposal -> R21 candidate instruction -> R22 dry-run simulation -> future sandbox replay

## Inputs

R22 consumes R21 `PaperLedgerCandidateInstruction` objects. A valid dry-run instruction must include:

- non-empty proposal ID
- non-empty symbol
- side of `BUY` or `SELL`
- positive quantity
- positive estimated price
- estimated notional matching `quantity * estimated_price`
- evidence references

`HOLD` should not reach R22. If it does, it is rejected.

## Account And A-share Constraints

R22 reuses R20 account profile preflight before simulating instructions. If account preflight fails, the whole dry-run is blocked.

The dry-run enforces:

- read-only, suspended, and kill-switched accounts block buy/sell dry-runs
- buy instructions must not make simulated cash negative
- sell instructions must not exceed normalized sellable quantity
- buy/sell quantities must be 100-share lots by default
- duplicate proposal IDs are rejected

Odd lots can be allowed only through the explicit `allow_odd_lot=True` parameter for controlled tests or review cases.

## Simulation Logic

Simulation starts with `account_profile.cash.available_cash` and current account position quantities.

For `BUY`:

- cash delta is `-(estimated_notional + estimated_cost)`
- position delta is `+quantity`

For `SELL`:

- cash delta is `estimated_notional - estimated_cost`
- position delta is `-quantity`

Instructions are processed deterministically in input order.

## Fee Estimate

R22 derives conservative paper costs from the account broker fee profile:

- commission uses `max(notional * commission_rate, min_commission)`
- stamp tax applies to sells
- transfer fee applies when configured
- slippage bps is included as conservative cost

These estimates are for sandbox review only and are not broker-confirmed charges.

## Decisions

The dry-run result can be:

- `ACCEPTED`: every instruction simulated
- `PARTIAL`: at least one instruction simulated and at least one instruction was rejected
- `BLOCKED`: account preflight failed, all instructions were rejected, or `fail_fast=True` stopped the run after the first critical block

With `fail_fast=True`, the first critical rejection blocks the run and later instructions are marked as skipped.

## Safety Boundaries

R22 is simulation-only. It does not mutate `AccountProfile`, does not write ledger persistence, does not connect to brokers, does not place live orders, does not call DeepSeek, does not perform network calls, and does not run Qlib or RQAlpha.

## Future Use

R22 provides the dry-run surface needed for future Market Reality Sandbox and multi-day paper replay work. A future phase can decide whether accepted dry-run results should feed a multi-day replay ledger under additional sandbox gates.
