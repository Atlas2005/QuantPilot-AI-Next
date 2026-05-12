# Real Data Readiness Gate

Phase 7E defines the minimum gate before QuantPilot-AI 2.0 may use real historical market data for alpha/factor validation.

This phase does not fetch data, integrate providers, install packages, or prove alpha.

## Why Real Data Is Dangerous Too Early

Real data can create false confidence when provider terms, adjustment policy, missing data, symbol mapping, market rules, transaction costs, storage, and reproducibility are not ready. Fake fixtures cannot prove alpha, but uncontrolled real data can create even more convincing wrong answers.

## Provider Readiness Requirements

- license and commercial use review
- endpoint reliability
- returned field mapping
- qfq/hfq/raw adjustment policy
- missing data policy
- suspension and corporate action policy
- provider failure handling

## Dataset Readiness Requirements

- enough symbols
- enough date range
- clean train/validation/test split
- OOS validation
- walk-forward validation
- reproducibility manifest

## A-share Realism Requirements

- T+1
- 100-share lot size
- limit-up/limit-down
- suspension
- ST/delisting
- transaction costs
- slippage
- liquidity/capacity

## Storage Requirements

Raw data must not be committed. Raw data must go to `local_artifacts/` or a later approved data lake.

DuckDB, Parquet / PyArrow, and Polars may be evaluated later, but they are not introduced in Phase 7E.

## Why No Data Fetch In Phase 7E

Phase 7E is the gate definition. Fetching real data before the gate is reviewed would invert the order and weaken the project discipline.

## Possible Next Phases

- Phase 7F controlled provider retry/readiness probe
- Phase 7G larger local fixture preparation
- Phase 7H isolated external analytics prototype
- Phase 8 strategy tournament later
