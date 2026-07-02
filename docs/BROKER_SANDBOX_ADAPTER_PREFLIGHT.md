# Broker Sandbox Adapter Preflight

R26 adds a deterministic broker sandbox adapter preflight after the R25 small-capital readiness gate.

This layer validates broker-sandbox handoff records without connecting to a broker, importing a broker SDK, placing orders, mutating accounts, calling DeepSeek, performing network calls, or writing to an external system.

## Purpose

R25 decides whether replay and attribution evidence is ready for small-capital progression. R26 is the next boundary: it checks whether readiness-gated candidate instructions are safe and well-formed enough to be handed to a future broker sandbox adapter.

R26 is not the adapter implementation. It is a contract and preflight layer before any future adapter work.

## Instruction Contract

`BrokerSandboxInstruction` includes:

- instruction ID
- proposal ID
- symbol
- side
- quantity
- estimated price
- optional limit price
- estimated notional
- adapter mode
- evidence references

Supported modes are `PAPER_ONLY`, `BROKER_SANDBOX`, and `READ_ONLY_CHECK`.

## Readiness Gate Checks

`BROKER_SANDBOX` instructions record R25 readiness as adapter context.

Readiness `FAIL` and `MANUAL_REVIEW` produce warnings or manual-review context; they do not blanket-block structurally valid sandbox instructions.

## Account And Broker Checks

R26 reuses R20 account profile preflight. It blocks broker sandbox acceptance when:

- account status is read-only, suspended, or kill-switched
- BUY lacks BUY permission
- SELL lacks SELL permission
- A-share market lacks `A_SHARE_CASH_EQUITY`
- QUERY_ONLY permission is used outside `READ_ONLY_CHECK`
- BUY estimated notional plus conservative fees exceeds available cash
- SELL quantity exceeds sellable quantity

## Mode Semantics

`BROKER_SANDBOX` is the only executable-ready mode.

`PAPER_ONLY` remains non-broker and cannot claim broker readiness.

`READ_ONLY_CHECK` is non-executable and can be used with query-only permission. It does not produce executable broker acceptance.

`HOLD` instructions are skipped and never executable.

## Safety Boundaries

R26 does not connect to real brokers, place live orders, write order objects to external systems, import vendor broker SDKs, call DeepSeek, train models, perform network calls, run Qlib, or run RQAlpha.

## Future Use

R26 prepares a safe, explicit contract for a future broker sandbox adapter implementation and manual small-capital trial workflow. Any future adapter must remain behind this readiness and preflight boundary.
