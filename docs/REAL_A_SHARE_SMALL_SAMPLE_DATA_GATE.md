# Real A-share Small Sample Data Gate

R7 adds a strict gate for admitting a future real A-share small-sample dataset into sandbox replay preparation.

R7 is a data gate, manifest, and validation layer only. It does not fetch or include real market data, call provider APIs, implement provider adapters, install dependencies, connect brokers, enable live trading, execute orders, or write production data assets.

## Scope

R7 defines the metadata a future small-sample dataset must provide before it can be considered for sandbox replay preparation.

The gate validates:

- dataset classification
- provider candidate identity
- R6 provider adapter probe plan reference
- approved R4 gate decision reference
- R3 bridge compatibility
- R2 sandbox fixture compatibility
- symbol, date, row, and lookback scope
- expected schema fields
- license review
- adjustment-policy audit
- symbol-mapping audit
- timestamp audit
- storage root, allowed path, and version marker
- no-production-data, no-broker, no-live-trading, and no-order-execution safety flags

The local fixture at `data/small_sample_data_gate/mock_small_sample_data_gate_request.json` is metadata only. It contains no real OHLCV market rows.

## Gate, Not Ingestion

R7 does not read data files, download data, call a provider SDK, or convert provider output.

Its purpose is to decide whether a manifest is narrow, reviewed, and safe enough for a later review step. Passing R7 means only that the manifest is acceptable for sandbox replay preparation review. It does not approve a data source, prove alpha, or create trading readiness.

## Required Upstream Evidence

A future real small-sample dataset must pass through prior boundaries before R7 can allow it forward:

- R6 provider adapter probe plan must exist and be referenced.
- R4 gate decision must be approved and referenced.
- R3 bridge compatibility must be explicit.
- R2 sandbox fixture compatibility must be explicit.

This keeps real-data admission tied to existing safety gates instead of becoming an informal data drop.

## Small-Sample Research-Only Data

Small-sample research-only data must be narrow and explicitly non-production:

- limited symbols
- limited rows
- limited lookback window
- documented provider candidate and source marker
- reviewed schema and timestamp assumptions
- reviewed adjustment and symbol-mapping assumptions
- stored only under an allowed metadata-reviewed path
- classified as `small_sample_research_only`

Production data classification is rejected.

## Storage and Versioning

The manifest must define:

- storage root
- allowed storage path
- version marker

The gate rejects empty paths, absolute paths, parent-directory traversal, backslash paths, and paths that do not live under the declared storage root. R7 does not create directories or write data.

## R1.1 Integration Enforcement

R7 respects R1.1 open-source integration enforcement by keeping mature data provider projects such as AkShare, Baostock, and Tushare as external adapter candidates.

The project must not reinvent generic provider infrastructure. Self-built R7 code is limited to contracts, gate logic, metadata validation, A-share-specific safety constraints, and orchestration boundaries.

## Sandbox Replay Preparation

R7 prepares for later sandbox replay by validating metadata required by R2/R3/R4/R6. It does not run replay, backtests, factor analysis, risk analytics, market calendars, broker routing, live trading, or order execution.

The next phase may define sandbox replay preparation using approved fixture or small-sample manifests only after review.
