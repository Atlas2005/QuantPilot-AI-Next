# Performance Attribution Flywheel Preflight

R24 adds a deterministic attribution layer over R23 multi-day paper replay outputs.

It summarizes replay behavior by proposal, symbol, source, and day, derives estimated costs and cash deltas, records blocked-rule feedback, and emits structured feedback records for future agent evaluation. It does not train models, update strategy weights, call DeepSeek, write persistence, or connect to brokers.

## Purpose

The project needs a feedback flywheel before any small-capital readiness gate or multi-agent orchestrator can safely learn from paper behavior. R24 creates the preflight surface for that flywheel:

- what proposals simulated
- what proposals were blocked or skipped
- which symbols accumulated cash and position effects
- which sources produced accepted or blocked ideas
- which days were clean, partial, or blocked
- which risk rules created negative feedback

## Inputs

R24 consumes an R23 `PaperReplayResult`. The replay result must include day results, finite final cash, recognized day statuses, recognized instruction statuses, and evidence references on instruction-level records.

## Proposal Attribution

Each instruction result becomes a `ProposalAttributionRecord` with:

- proposal ID
- symbol
- trading date
- side, quantity, estimated price, and notional
- instruction status and reason
- cash delta, position delta, estimated cost, and outcome
- evidence references

Outcomes are deterministic: simulated positive cash delta is `SIMULATED_GAIN`, simulated negative cash delta is `SIMULATED_LOSS`, rejected instructions are `BLOCKED`, skipped instructions are `SKIPPED`, and zero-effect records are `FLAT`.

## Cost Attribution

Estimated cost is derived from instruction cash delta and notional:

- buy-like negative cash delta: `abs(cash_delta) - estimated_notional`
- sell-like positive cash delta: `estimated_notional - cash_delta`
- blocked or skipped instructions: zero cost

Tiny negative floating noise is clamped to zero.

## Aggregation

R24 aggregates:

- by symbol: accepted/blocked counts, net cash delta, net position delta, total estimated cost
- by source: source mapping if supplied, otherwise source inferred from `source:` evidence refs
- by day: accepted/blocked counts, cash start/end, net cash delta, total estimated cost

## Feedback Records

Feedback records target proposals, symbols, days, and risk rules. Scores are deterministic and clamped to `[-1.0, 1.0]`.

Blocked critical risk flags produce negative feedback. Simulated cash gains/losses produce positive or negative feedback based on cash-delta sign. This is evaluation data only, not a model update.

## Safety Boundaries

R24 is preflight only. It does not train models, update live strategy weights, call DeepSeek, perform network calls, write ledger persistence, connect to brokers, place live orders, run Qlib, or run RQAlpha.

## Future Use

R24 supports future Small-Capital Readiness Gate and Multi-Agent Orchestrator work by providing structured, auditable attribution and feedback records over sandbox replay behavior.
