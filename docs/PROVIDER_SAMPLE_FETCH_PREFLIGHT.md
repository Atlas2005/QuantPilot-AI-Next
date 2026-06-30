# Provider Sample Fetch Preflight

R13 connects provider fallback selection to an offline sample fetch and the existing small-sample data gate path.

## Why R13 Exists

R12 decides which optional provider candidate should be attempted first. R13 takes that decision one step further by using an injected fake/offline provider object to produce normalized sample daily bars, then passing those bars into the existing small-sample gate path.

This keeps the chain explicit:

provider selector -> normalized sample bars -> small sample gate -> paper ledger / Market Reality Sandbox

## Offline Provider Clients

R13 tests use fake/offline provider clients only. The preflight accepts provider objects with either:

- `fetch_daily_bars(symbol, start_date, end_date)`
- `get_daily_bars(symbol, start_date, end_date)`

The module does not import AkShare or BaoStock, does not require either package, and does not perform network calls.

## Gate Reuse

R13 reuses the existing small-sample gate path through the real provider gate bridge. It does not duplicate gate logic and does not replace `small_sample_data_gate`.

The result reports:

- selected provider
- fetched bar count
- gate outcome
- reasons
- warnings
- suggested next action

## Limitations

- No live fetch in tests.
- No production provider SLA.
- No strategy, backtest, live trading, broker connection, or order execution.
- No RQAlpha run.
- No production data asset is written.

## Future Path

- R14: paper ledger fed by gated provider samples.
- R15: RQAlpha dry-run fixture once dependency and data format are ready.
- R16: capital/account-aware paper execution constraints.
