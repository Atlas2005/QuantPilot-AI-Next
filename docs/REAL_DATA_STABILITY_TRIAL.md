# P31 Real Data Stability Trial

P31 starts the post-R30 phase by validating real-data stability before any Qlib runtime spike, broker workflow, or real-capital path.

The default path is offline and deterministic. Tests use fixture rows only. Provider-specific network trials are optional/manual and must be explicitly enabled by an operator.

## Purpose

R7-R30 closed the preflight/sandbox MVP. P31 adds the first stability layer for real A-share provider output:

- fixed A-share sample universe contracts
- provider trial config contracts
- provider row shape validation
- required field coverage checks
- date, duplicate, and missing-row checks
- numeric OHLCV sanity checks
- multi-provider fallback compatibility warnings
- structured provider stability reports

P31 does not approve production data use. It records whether supplied provider rows are stable enough for the next offline validation step.

## Supported Providers

P31 recognizes:

- AkShare
- BaoStock
- fixture

AkShare and BaoStock remain optional. The package does not add either provider as a required dependency.

## Sample Universe

The trial uses an explicit A-share sample universe:

- non-empty universe id
- unique A-share-shaped symbols
- strict ISO `YYYY-MM-DD` start and end dates
- `start_date <= end_date`
- optional positive expected trading day count
- evidence references

Symbols are expected to be six digits, optionally with an exchange suffix such as `.SH`, `.SZ`, or `.BJ`.

## Required Field Checks

Provider trial configs define required and optional fields. For daily bars, typical required fields are:

- `open`
- `high`
- `low`
- `close`
- `volume`

Rows missing required fields fail the provider report.

## Date, Duplicate, Missing, And Numeric Checks

P31 validates that provider rows:

- match the configured provider
- use symbols from the sample universe
- use strict ISO trading dates
- stay within the universe date range
- include evidence references
- do not duplicate provider + symbol + date
- have finite numeric OHLCV values where present
- satisfy `high >= low`
- keep open and close within high/low when all fields exist
- keep volume non-negative

Missing symbol/date coverage is treated as a warning when core rows are otherwise sane.

## Provider Fallback Compatibility

When multiple provider reports are present, P31 compares the observed symbols and dates. Differences create a manual-review warning rather than pretending providers are interchangeable.

This prepares the path for provider fallback stability work without making a final production data-source selection.

## Optional Manual Network Trial

`run_optional_manual_provider_trial` is an explicit manual boundary:

- default `allow_network=False`
- no provider package is imported when network is disabled
- unavailable provider packages produce structured manual-review results
- callers must supply a row loader when network is explicitly enabled

Default tests do not call provider APIs and do not require AkShare or BaoStock.

## Safety Boundary

P31 does not:

- call DeepSeek
- run Qlib or qrun
- run RQAlpha
- connect to brokers
- place orders
- mutate accounts
- train models
- update live strategy weights
- add provider packages as required dependencies

## Path To P32

P31 prepares P32 Offline Qlib Runtime Spike by producing structured data-stability evidence first. P32 should consume only provider samples that have passed or been manually reviewed through this trial boundary.
