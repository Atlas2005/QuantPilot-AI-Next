# AI Action Proposal -> Paper Ledger Bridge

R21 adds a deterministic bridge between structured AI action proposals and paper-ledger-compatible candidate instructions.

The bridge is intentionally not an execution path. It validates proposals, checks the R20 account profile / broker config preflight, estimates conservative paper costs, and emits in-memory candidate instructions only when a proposal is safe enough for the next sandbox dry step.

## Purpose

DeepSeek-backed and multi-agent proposal layers must not be able to jump directly into paper or broker-like flows. R21 creates the guardrail between agent output and the paper ledger:

- proposals must be structured
- proposals must carry evidence and rationale
- account and broker constraints must pass first
- cash, sellable quantity, permissions, and A-share lot rules are checked before any candidate instruction is emitted

## Accepted Proposal Contract

`AIActionProposal` includes:

- proposal ID
- source
- symbol
- side: `BUY`, `SELL`, or `HOLD`
- quantity
- optional limit price
- estimated price
- confidence
- rationale
- evidence references

Supported sources are supervisor, news/event agent, factor agent, risk agent, and manual review.

## Account / Broker Preflight Reuse

R21 reuses R20 `run_account_profile_preflight()` before inspecting proposal-specific constraints. If the account profile is invalid, all proposals are blocked.

For executable proposals:

- `BUY` requires buy permission
- `SELL` requires sell permission
- read-only, suspended, and kill-switched accounts block buy/sell proposals
- buy notional plus estimated fees must fit available cash
- sell quantity must not exceed normalized sellable quantity
- configured max order value must not be exceeded

## A-share Quantity Rules

By default, A-share buy and sell quantities must be positive 100-share lots. Odd lots can be allowed only through the explicit `allow_odd_lot=True` parameter for controlled cases.

`HOLD` proposals must have quantity zero and do not emit candidate instructions.

## Fee / Cost Estimate

The bridge estimates conservative costs using the R20 broker fee profile:

- commission uses `max(notional * commission_rate, min_commission)`
- stamp tax applies to sells
- transfer fee applies when configured
- slippage bps is added as a conservative cost estimate

These are paper-review estimates, not execution evidence.

## Decisions

The bridge can return:

- `ACCEPTED_FOR_PAPER`: proposals are valid for candidate paper review
- `BLOCKED`: critical proposal or account risk was found
- `REQUIRES_MANUAL_REVIEW`: proposal is structurally valid but confidence is below threshold

If all proposals are `HOLD`, the bridge returns accepted with zero candidate instructions.

## Safety Boundaries

R21 does not connect to brokers, write to the paper ledger, place trades, generate live orders, read account APIs, call DeepSeek, perform network calls, or run Qlib/RQAlpha.

The output is an in-memory `PaperLedgerCandidateInstruction`, not an order and not a ledger update.

## Future Use

R21 can feed a future Market Reality Sandbox and multi-day replay stage by providing a reviewed candidate-instruction layer. The next phase can decide whether to connect accepted candidates to the existing paper ledger dry path under additional sandbox gates.
