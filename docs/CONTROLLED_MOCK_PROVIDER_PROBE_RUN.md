# Controlled Mock Provider Probe Run

R5 adds a local mock-only end-to-end probe path:

```text
R4 gate request -> gate decision -> R3 provider probe snapshot -> R3 bridge -> R2 SandboxFixtureInput
```

R5 proves the project can move from a mock provider probe request to a sandbox fixture input without touching real market data, provider APIs, broker systems, live trading, or order execution.

## Scope

R5 adds:

- `MockProbeRunRequest`
- `MockProbeRunStatus`
- `MockProbeRunResult`
- `MockProbeRunRejectionReason`
- `MockProbeRunAuditRecord`
- `MockProbeRunArtifactManifest`
- a local run helper
- one static mock run request fixture

The run is limited to `mock_only` or `dry_run`.

## Why Mock-Only / Dry-Run Only

R5 is designed to verify orchestration and safety boundaries before any controlled provider adapter probe.

The run requires:

- local fixture paths under `data/`
- no real data
- no provider API
- no broker
- no live trading
- no order execution
- output classification `mock_fixture_only`
- no production data asset writes

## End-To-End Path

1. Load local R5 mock run request.
2. Load local R4 gate request fixture.
3. Evaluate the R4 provider probe gate.
4. Load local R3 provider probe snapshot fixture.
5. Convert the snapshot through the R3 Provider-Sandbox Fixture Bridge.
6. Return a `SandboxFixtureInput` for later R2 Market Reality Sandbox scenario construction.

## R1.1 Open-Source Integration Enforcement

R5 respects R1.1 by staying orchestration/glue only.

AkShare, Baostock, Tushare, and similar mature provider projects remain future adapter candidates. R5 does not replace them with QuantPilot-owned provider code.

## Intentional Non-Goals

R5 does not:

- install dependencies
- fetch real market data
- call provider APIs
- write production data assets
- approve any provider
- implement a data provider
- implement a sandbox simulator
- implement a backtest engine
- connect brokers
- add live trading
- create order execution paths
- claim profitability or alpha

## Next Phase Direction

R5 supports R6 controlled provider adapter probe or R7 real small-sample data gate by proving the local safety path first.

The next phase may define a controlled provider adapter probe or real small-sample data gate only after review.

## Capital-Test MVP Support

The 30-day Capital-Test MVP needs evidence-gated movement from provider readiness to sandbox validation.

R5 provides the first safe local orchestration proof without crossing into live trading or real provider access.
