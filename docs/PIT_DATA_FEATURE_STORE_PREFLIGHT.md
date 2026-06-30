# PIT Data & Feature Store Preflight

R18 adds a point-in-time data and feature-store preflight layer. It checks whether offline feature records are safe to pass toward sandbox-only research without adding a production feature store, storage engine, provider fetch, backtest, or model runtime.

## Objective

QuantPilot needs feature data that can be inspected as of a specific date without leaking future information. R18 makes that requirement explicit through small contracts and deterministic validation:

- every feature set has an ID, version, source reference, and offline preflight build mode
- every record has a symbol, feature name, finite numeric value, observation date, available date, as-of date, and evidence reference
- observation and availability dates must not exceed the as-of date
- availability cannot precede observation
- the result must remain sandbox-only with live trading and order paths disabled

## What This Is Not

R18 is not a new feature-store engine. It does not choose DuckDB, Parquet, Feast, Qlib, pandas, or any external storage/runtime dependency. It also does not compute factors, fetch data, run RQAlpha, run Qlib, place orders, or connect to a broker.

The module is only the preflight contract that future adapters must satisfy before feature data can feed the Market Reality Sandbox dry path.

## Fit With The Current Chain

The current dry chain is:

provider selector -> sample fetch -> small sample gate -> paper ledger dry path -> A-share constraints -> AI runtime routing preflight -> PIT feature-store preflight

R18 adds the missing temporal safety check between validated samples and future feature use. A feature row is not accepted just because its value is present; it must also prove when the source observation happened, when the value became available, and what as-of date it is allowed to serve.

## Open-Source-First Boundary

The project remains integration-first. A mature feature-store or analytics engine may be evaluated later, but this phase only defines the adapter-facing contract:

- self-built code is limited to PIT contracts, validation, and sandbox guardrails
- generic feature storage, materialization, factor computation, and analytics should be delegated to mature open-source tools where practical
- future adapters must map their records into `PITFeatureRecord` before sandbox use

## Future Path

- R19: feature materialization adapter candidate review.
- R20: gated PIT feature samples feeding paper-ledger/sandbox dry reviews.
- R21: optional external feature-store prototype in an isolated environment if the project chooses one.
