# Provider-Sandbox Fixture Bridge

R3 adds a controlled bridge from provider probe/readiness output into Market Reality Sandbox fixture inputs.

This is a fixture/probe bridge only. It is not real data ingestion, not a data provider implementation, not a provider client, not a market data fetcher, and not an approval of any data source.

## Scope

R3 adds:

- `ProviderProbeSnapshot`
- `ProviderProbeStatus`
- `ProviderDataQualitySignal`
- `ProviderLatencySignal`
- `ProviderFailureSignal`
- `SandboxFixtureInput`
- `ProviderSandboxBridgeResult`
- `ProviderSandboxBridgeRejectionReason`
- `ProviderSandboxAdapterBoundary`
- local bridge validation and conversion helpers
- one static mock provider probe fixture

The bridge accepts only explicitly marked fixture/mock/probe snapshots. Approved production data is rejected.

## Why This Exists

R2 defined Market Reality Sandbox contracts. R3 defines how later controlled provider probes or mock provider outputs can be shaped into sandbox fixture inputs without crossing into live data ingestion or broker/execution work.

The bridge checks:

- provider name
- provider project/candidate name such as AkShare, Baostock, Tushare, or mock
- probe timestamp
- symbol and trading date
- OHLCV-like fixture fields
- adjustment policy marker
- symbol mapping confidence
- timestamp audit status
- latency signal
- provider failure signal
- data quality signal
- external adapter boundary
- explicit fixture/mock/probe data flag

## R1.1 Open-Source Integration Enforcement

R3 respects R1.1 by keeping mature data provider projects as adapter candidates.

AkShare, Baostock, Tushare, and similar provider projects are not replaced by QuantPilot-owned provider code in R3. QuantPilot owns only the contracts, adapter boundary, local fixture validation, and bridge glue.

## Relationship To R2

R3 produces `SandboxFixtureInput` records that can later feed R2 Market Reality Sandbox scenario construction.

The bridge preserves provider latency and provider failure assumptions so later sandbox validation can reason about data freshness, timestamp audit, and provider reliability.

## Intentional Non-Goals

R3 does not:

- install dependencies
- fetch real market data
- call provider APIs
- approve any provider
- implement a full data provider
- implement a market calendar
- implement a backtest engine
- connect brokers
- add live trading
- create order execution paths
- claim profitability or alpha

## 30-Day Capital-Test MVP Support

R3 supports the 30-day Capital-Test MVP by creating a safe path from controlled provider readiness outputs to fixture-based sandbox validation.

The next phase should move toward controlled provider probe execution or a small-sample data gate only after review.
