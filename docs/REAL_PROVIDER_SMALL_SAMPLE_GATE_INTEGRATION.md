# Real Provider Small Sample Gate Integration

R9 connects the R8 real-data-provider contracts to the R7 small-sample data gate.

This is the first real-data-chain integration in QuantPilot-AI-Next: a `DailyBarProvider` can return normalized daily bars, and the bridge converts that output into a small-sample gate request for validation before sandbox replay preparation.

## Objective

R9 keeps the implementation small:

- accept a `DailyBarProvider`
- accept a `DailyBarRequest`
- call `provider.fetch_daily_bars(request)`
- convert returned `NormalizedDailyBar` records into R7 small-sample manifest metadata
- invoke `validate_small_sample_data_gate_request`
- return a compact result with provider, symbol, date range, bar count, gate status, and gate reasons

## Boundaries

R9 is integration glue only. It does not:

- call real AkShare in tests
- require network access
- make AkShare a required dependency
- add another provider
- implement a trading strategy
- implement a backtest engine
- write production data assets
- add broker integration, live trading, or order execution

## AkShare Remains Optional

AkShare remains only one optional provider behind the R8 provider interface. R9 tests use fake providers that return `NormalizedDailyBar` records, so the test suite does not import the real AkShare package and does not call any provider network endpoint.

## Small Sample Gate Reuse

R9 reuses the R7 small-sample gate contracts instead of creating a second gate. Provider records are represented as manifest metadata with:

- R6 adapter plan reference
- R4 gate decision reference
- R3 bridge compatibility
- R2 sandbox fixture compatibility
- reviewed schema, license, adjustment, symbol mapping, timestamp, and storage policy metadata

The bridge result is intentionally compact. The R7 gate remains the source of truth for admission decisions.

## Roadmap

- R10: RQAlpha adapter/preflight spike.
- R11: BaoStock fallback provider.
- R12: paper ledger fed by gated real-provider samples.
