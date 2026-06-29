# Controlled Provider Probe Gate

R4 adds the Controlled Provider Probe Execution Gate.

The gate decides whether a provider probe request is allowed to run in a controlled environment and whether its output may later be considered for R3 Provider-Sandbox Fixture Bridge conversion into R2 Market Reality Sandbox fixture input.

R4 is a gate, not a provider adapter.

## Scope

R4 adds:

- `ProviderProbeGateRequest`
- `ProviderProbeGateDecision`
- `ProviderProbeGateStatus`
- `ProviderProbeGateRejectionReason`
- `ProviderProbeExecutionMode`
- `ProviderProbeScope`
- `ProviderProbeSafetyPolicy`
- `ProviderProbeEvidenceRequirement`
- `ProviderProbeAllowedProvider`
- `ProviderProbeAuditRecord`
- local decision helpers
- one static mock gate request fixture

## Why R4 Is A Gate

Provider probes are risky because uncontrolled data access can blur the line between fixture review, real data ingestion, provider approval, and premature alpha validation.

R4 requires every request to prove:

- provider candidate is allowed
- execution mode is controlled
- scope is small
- license review status exists
- adapter boundary is acknowledged
- broker, live trading, and order execution are disabled
- storage remains local artifact or fixture-only
- timestamp audit is required
- latency review is required
- provider failure handling is required
- R3 sandbox bridge compatibility is required
- output remains probe/fixture data, not approved production data

## R1.1 Open-Source Integration Enforcement

R4 respects R1.1 by keeping mature data provider projects as adapter candidates.

AkShare, Baostock, Tushare, and similar projects are not replaced by QuantPilot-owned provider code. R4 only decides whether a controlled request is safe enough to run later after review.

## Relationship To R3 And R2

R4 gates future controlled provider probe requests.

If a future request passes R4 and is run under approved conditions, its output may later be reviewed for R3 Provider-Sandbox Fixture Bridge conversion.

R3 output may later feed R2 Market Reality Sandbox fixture inputs.

## Intentional Non-Goals

R4 does not:

- install dependencies
- fetch real market data
- call provider APIs
- create provider adapters
- approve any provider
- implement a data provider
- write market data files
- connect brokers
- add live trading
- create order execution paths
- claim profitability or alpha

## 30-Day Capital-Test MVP Support

R4 supports the 30-day Capital-Test MVP by preventing uncontrolled provider access while creating a reviewable path toward controlled mock, dry-run, or approved adapter probes.

The next phase may run a controlled mock/dry-run probe or define approved adapter probes only after review.
