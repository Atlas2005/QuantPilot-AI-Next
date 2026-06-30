# Account Profile / Broker Config Preflight

R20 adds a deterministic account profile and broker config preflight layer. It makes account status, cash, positions, broker capabilities, trade permissions, fee assumptions, and risk limits explicit before any future AI action proposal, paper ledger bridge, or Market Reality Sandbox flow can use them.

## Purpose

QuantPilot is capital/account-aware. Future agents and sandbox checks should not rely on hidden defaults such as assumed cash, assumed sellable positions, assumed broker permissions, or generic fee settings.

R20 creates a typed offline boundary for those assumptions. The preflight can run on fixture-style account profiles and produce deterministic flags, normalized sellable quantities, position weights, and industry weights.

## Supported Contracts

R20 defines:

- `AccountCashProfile`
- `AccountPosition`
- `BrokerFeeProfile`
- `BrokerCapabilityProfile`
- `AccountRiskLimits`
- `AccountProfile`
- `AccountProfileRiskFlag`
- `AccountProfilePreflightResult`

Account status values are `ACTIVE`, `READ_ONLY`, `SUSPENDED`, and `KILL_SWITCHED`.

Broker capability values include A-share cash equity, ETF, STAR Market, ChiNext, margin trading, short selling, and convertible bond support.

Trade permission values are `BUY`, `SELL`, `CANCEL`, and `QUERY_ONLY`.

## Validation Rules

The preflight validates:

- non-empty account ID, broker name, market, and evidence references
- non-negative available and frozen cash
- positive total equity
- cash/equity consistency unless explicitly allowed for controlled fixtures
- non-empty position symbols
- non-negative position quantity, sellable quantity, average cost, and market value
- sellable quantity not exceeding total quantity
- duplicate position symbols
- fee and slippage bounds
- non-empty broker capabilities and permissions
- `QUERY_ONLY` not mixed with trade permissions unless explicitly allowed
- non-active account statuses not carrying buy or sell permission
- A-share market profiles carrying the A-share cash equity capability
- valid risk limits

## Concentration Checks

R20 computes:

- position weight by symbol: `market_value / total_equity`
- industry weight: summed industry market value divided by total equity
- total position weight: summed market value divided by total equity

Critical flags are emitted when single-symbol, industry, or total-position concentration exceeds configured limits.

## Sellable Quantity Normalization

`normalize_sellable_quantities()` returns a deterministic mapping of symbol to sellable quantity. Values are clamped to the valid range implied by each position so downstream dry paths can inspect the account profile without mutating it.

## Safety Boundaries

R20 does not connect to real brokers, read account APIs, generate orders, place trades, call DeepSeek, perform network calls, or run Qlib/RQAlpha.

It is only a contract and preflight layer for explicit account/broker configuration.

## Future Use

R20 can feed a future AI Action Proposal -> Paper Ledger Bridge by providing:

- account status and permission gates
- normalized sellable quantities for sell checks
- fee assumptions for paper cost modeling
- concentration flags before any sandbox dry path proceeds

It can also feed Market Reality Sandbox checks with explicit account-level constraints instead of hard-coded assumptions.

## Recommended Next Stage

The next stage should connect this account profile preflight to an AI Action Proposal -> Paper Ledger Bridge, while keeping the bridge offline, deterministic, and sandbox-only.
