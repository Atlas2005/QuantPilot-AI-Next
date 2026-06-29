# Real Data Provider Adapter Spike

R8 adds the first real-data-provider abstraction for A-share daily bars.

This is an adapter spike, not data ingestion. It adds provider-independent daily-bar contracts and an optional AkShare adapter that can normalize daily OHLCV-like rows into QuantPilot contracts.

## Objective

R8 creates a narrow provider boundary for future real A-share daily bar work:

- define a `DailyBarRequest`
- define normalized daily-bar output
- define provider exceptions
- keep provider implementations behind a `DailyBarProvider` protocol
- add an AkShare adapter as the first spike provider
- keep unit tests offline with fake clients and fake DataFrame-like objects

## AkShare Is First, Not Final

AkShare is the first spike provider because it is a practical A-share research data candidate and has already appeared in earlier provider planning.

It is not the final single source of truth. R8 does not approve AkShare as the canonical data source, does not fetch data during tests, and does not make any profitability or trading-readiness claim.

Future provider comparison and fallback logic still needs evidence, license review, timestamp review, schema review, and sandbox replay review.

## Optional Dependency Principle

AkShare remains optional.

The core package does not require AkShare to import the provider contracts. `AkShareDailyBarProvider` accepts an injected client for tests and other controlled use. If no client is injected, it lazily imports AkShare only when `fetch_daily_bars()` is called.

Missing AkShare raises a clear `ProviderDependencyError`.

## No-Network Unit Test Principle

R8 unit tests do not require:

- network access
- the real AkShare package
- real provider credentials
- live provider calls
- market data downloads

Tests use fake clients and fake pandas-like objects to verify call parameters, Chinese-column normalization, sorting, and error handling.

## What R8 Does Not Do

R8 does not:

- fetch real market data during validation
- install dependencies
- add AkShare as a required dependency
- add a full data provider implementation
- approve a data source
- write production data assets
- connect brokers
- enable live trading
- execute orders
- implement a backtest, risk, factor, market-calendar, or portfolio-accounting engine

## Future Provider Roadmap

Future phases should compare and harden provider coverage through adapter boundaries:

- BaoStock fallback for A-share historical data coverage
- Tushare Pro as a possible canonical research provider after token, license, and permission review
- miniQMT / XtQuant as a future live-paper or broker bridge candidate, isolated from research ingestion and never treated as an early core dependency

Any future provider addition should preserve optional dependencies, offline unit tests, explicit schema normalization, timestamp audit, license review, and sandbox replay compatibility.
