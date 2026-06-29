# Provider Fallback Selector Preflight

R12 adds a deterministic selector/preflight layer for optional A-share data provider candidates.

## Why R12 Exists

R8 introduced the real data provider contract and AkShare adapter spike. R11 added BaoStock as a fallback provider candidate. R12 connects those candidates at the selection layer without fetching live data or requiring either package to be installed.

The selector answers one small question: given provider availability, explicit preference, and health/preflight status, which provider should be attempted first?

## AkShare And BaoStock

AkShare and BaoStock complement each other. Either may have different coverage, availability, data semantics, or operational reliability. R12 keeps both visible as optional candidates and lets the project prefer one while falling back to the other when appropriate.

Neither provider is approved as a production source by R12.

## Optional Providers

Both providers remain optional. R12 does not import AkShare or BaoStock at module import time and does not make tests depend on either package.

Dependency detection and health checks can be reported into the selector as status objects. Missing, disabled, and unhealthy providers are skipped.

## Integration-First Design

R12 supports the open-source-first and integration-first design by adding selection glue around mature external provider candidates instead of building a new data framework.

The intended path is:

provider selector -> small sample data gate -> paper ledger / sandbox

## Limitations

- No live fetch is performed in tests.
- No provider SLA is claimed.
- No strategy, backtest, live trading, broker connection, or order execution is added.
- R12 does not replace `small_sample_data_gate` or `real_provider_gate_bridge`.

## Future Path

- R13: small sample provider fetch command/preflight using selected provider and fake/offline fixture.
- R14: paper ledger fed by gated provider samples.
- R15: RQAlpha dry-run fixture once dependency and data format are ready.
