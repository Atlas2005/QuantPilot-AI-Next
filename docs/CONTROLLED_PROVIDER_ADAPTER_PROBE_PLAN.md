# Controlled Provider Adapter Probe Plan

R6 adds a controlled provider adapter probe plan layer.

This phase is planning and validation only. It does not install provider packages, fetch real market data, call provider APIs, implement a provider adapter, create production data assets, connect brokers, add live trading, or execute orders.

## Purpose

The R6 plan defines the minimum evidence required before any future provider adapter probe can be submitted to the R4 gate.

It keeps mature provider projects such as AkShare, Baostock, and Tushare as external candidates. QuantPilot may later connect them through narrow adapters after license, endpoint, schema, adjustment-policy, symbol-mapping, timestamp, and safety review.

R6 does not select, approve, or integrate any provider.

## Controlled Plan Contract

An adapter probe plan must describe:

- provider candidate identity
- endpoint category
- expected schema fields and notes
- symbol and date scope limits
- adjustment-policy review
- symbol-mapping review
- timestamp-audit review
- license/commercial-use review
- adapter boundary
- safety flags proving no real data fetch, no provider API call, no broker, no live trading, and no order execution
- output classification as `adapter_probe_plan_only`
- compatibility with the R4 gate, R3 bridge, and R2 sandbox fixture path

The local fixture at `data/provider_adapter_probe_plan/mock_provider_adapter_probe_plan.json` is a mock plan only. It is not real market data and is not a provider approval.

## Validation Rules

The validator rejects plans that:

- name an unknown provider, unless the provider is explicitly marked mock
- omit license review
- omit endpoint category
- omit schema requirements
- omit adjustment-policy review
- omit symbol-mapping review
- omit timestamp-audit review
- omit adapter-boundary acknowledgement
- allow real data fetches
- allow provider API calls
- allow broker, live trading, or order execution behavior
- exceed narrow symbol, row, or lookback limits
- classify output as production data
- fail to state compatibility with R4, R3, and R2

Accepted R6 output means only that the plan is acceptable for review and possible future gate submission. It does not mean provider data is approved.

## R1.1 Open-Source Enforcement Alignment

R6 supports R1.1 by requiring mature external provider candidates to remain visible before any self-built provider path is considered.

The project must not reinvent generic provider infrastructure where practical. Self-built code remains limited to contracts, adapters, glue, A-share market-reality constraints, capital/account constraints, safety gates, orchestration boundaries, and validation layers.

## Future Phase Boundary

Any future real small-sample provider probe must remain separate from R6 and must receive explicit review before it can:

- install a provider package
- call a provider API
- fetch real market data
- write any non-production or production data artifact
- claim data-source approval

R6 is the plan gate before that work. It is not the work itself.
