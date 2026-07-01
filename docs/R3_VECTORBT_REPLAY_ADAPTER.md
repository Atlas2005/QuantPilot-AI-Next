# R3 Vectorbt Replay Adapter

## Why Vectorbt First

R3 starts with vectorbt because it is a mature pandas/NumPy-based quantitative analysis and backtesting framework. This is the smallest useful step away from self-built replay logic and toward mature framework-backed profitability analysis.

`vectorbt` is optional. It is not a required runtime dependency and missing framework availability is reported as `framework_missing`, not as a project blocker.

## Replacement Direction

The adapter does not delete the existing paper/fill/replay chain in this patch. It creates a replacement path that can progressively take over replay and portfolio analysis responsibilities.

QuantPilot-owned code should remain focused on contracts, adapters, A-share constraints, account/capital constraints, orchestration, and glue around mature frameworks.

## RQAlpha And Qlib

RQAlpha and Qlib remain next-stage integrations:

- RQAlpha for A-share-style backtest and trading simulation.
- Qlib for AI quant workflow, factor research, and model-oriented research pipelines.

## Safety Boundary

Safety is fatal-only. Missing vectorbt is not a blocker for the whole project.

Fatal issues are invalid input, impossible quantities/prices, insufficient cash, invalid sellable quantity, price-limit or suspension violations in execution-facing modules, credential leakage, and unauthorized live broker/order paths.

Non-fatal framework availability and quality issues should be reported as warnings or `framework_missing` so paper replay and controlled trading progress can continue.
