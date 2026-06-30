# News / Event Agent Preflight

R19 adds an offline contract and preflight layer for future news, announcement, policy, macro, industry, earnings, regulatory, and rumor-aware agents.

The module converts fixture-style structured event findings into point-in-time feature records that are validated through the R18 PIT feature-store preflight. It does not crawl news, call a model, fetch provider data, place orders, or materialize a real feature store.

## Why R18 Comes First

News and event signals are especially vulnerable to lookahead leakage. A finding is not usable just because its summary exists. The system must know:

- when the event happened
- when the event became known
- when the event was available for trading review
- which symbols were affected
- which evidence supports the structured output

R18 supplies the PIT boundary. R19 maps structured event findings into `PITFeatureRecord` objects so future sandbox consumers can reject unavailable or backfilled signals before they influence research.

## Supported Event Types

- `COMPANY_ANNOUNCEMENT`
- `POLICY_EVENT`
- `MACRO_EVENT`
- `INDUSTRY_EVENT`
- `EARNINGS_EVENT`
- `REGULATORY_EVENT`
- `MARKET_RUMOR`
- `UNKNOWN`

Risk levels are `LOW`, `MEDIUM`, `HIGH`, and `CRITICAL`.

## Structured Output Requirements

R19 requires typed structured findings. Natural-language-only output is rejected. A valid finding includes:

- event classification
- sentiment score in `[-1.0, 1.0]`
- confidence in `[0.0, 1.0]`
- affected symbol impacts with impact scores in `[-1.0, 1.0]`
- risk flags where required
- evidence references

Non-`UNKNOWN` event types must include affected symbols. `MARKET_RUMOR` and `CRITICAL` classifications must include at least one risk flag. `UNKNOWN` with high confidence is rejected because confident unknowns are a contradiction that should be reviewed before downstream use.

## Temporal Safety Rules

Event records must provide `event_time`, `known_time`, and `available_for_trading_time`.

By default, `known_time` earlier than `event_time` is rejected. Backfilled historical records can be allowed only by explicitly passing `allow_backfilled_event_time=True` to validation or preflight.

`available_for_trading_time` earlier than `known_time` is always rejected.

## PIT Bridge Behavior

For each affected symbol, the bridge emits deterministic in-memory feature records:

- `news.sentiment`
- `news.risk_level_numeric`
- `news.impact_score`
- `news.event_type_numeric`
- `news.confidence`

The bridge uses the event date as observation date, the trading-availability date as available date, and the preflight `as_of_time` date as the PIT as-of date. R18 PIT preflight then decides whether the records are visible at that as-of date.

No database, object store, feature-store engine, or materialization job is created in R19.

## DeepSeek News Agent Path

R19 prepares the contract boundary for a future DeepSeek News Agent without calling DeepSeek or any other model provider. Future model output must be converted into these structured contracts before it can become a PIT-visible feature candidate.

## Not In Scope

- no network calls
- no news crawling
- no model provider calls
- no real data provider calls
- no broker, account, live trading, or order path
- no Qlib or RQAlpha execution
- no feature-store engine materialization

## Recommended Next Stage

The next stage should be either Account Profile / Broker Config preflight or a Stats Agent preflight, depending on whether the project wants to harden account constraints first or add another offline AI-agent validation boundary.
