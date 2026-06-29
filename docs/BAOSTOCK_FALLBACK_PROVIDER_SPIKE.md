# BaoStock Fallback Provider Spike

R11 adds BaoStock as a second optional A-share daily-bar provider candidate.

## Why BaoStock

BaoStock is a mature Python package for historical China stock market data. It is useful as a fallback candidate beside AkShare because provider coverage, field semantics, data availability, and operational stability may differ across sources.

R11 does not approve BaoStock as a production data source. It only adds a small optional adapter spike that can normalize BaoStock-like daily-bar rows into the existing `NormalizedDailyBar` contract.

## Optional Dependency

BaoStock remains optional. The core package can import without BaoStock installed, and tests use fake clients and fake DataFrame-like outputs.

If no client is injected and BaoStock is missing, the adapter fails clearly instead of silently pretending data is available.

## Relationship To AkShare

BaoStock complements AkShare rather than replacing it. AkShare remains the first provider spike, while BaoStock gives the project a fallback candidate for future provider selection, data comparison, and resilience review.

Both providers stay behind adapter boundaries and normalized contracts.

## Open-Source-First Path

R11 supports the integration-first, open-source-first A-share data path by evaluating a mature external provider before building custom provider infrastructure.

The implementation stays limited to adapter and normalization glue. It does not create a new data framework.

## Limitations

- No live fetch is performed in tests.
- No network access is required by tests.
- BaoStock is not a required dependency.
- No production data SLA is claimed.
- No strategy, backtest execution, RQAlpha execution, broker path, live trading, or order execution is added.

## Next Path

- R12: provider fallback selector/preflight.
- R13: paper ledger fed by gated provider samples.
- R14: RQAlpha dry-run fixture once dependency and format are ready.
