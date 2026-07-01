# P48 BaoStock Broader Real Provider Sample Factor Comparison Report

## Status

P48 completed the broader real-provider sample trial using BaoStock.

This phase expands the previous P45/P47 real-sample scope from a small 2-stock + 2-ETF sample to a broader 10-stock + 5-ETF sample. The goal is not to prove profitability, but to verify that the P47 factor-comparison framework can run on a broader real provider dataset and produce a P44-compatible artifact.

## Branch

`p48-broader-real-provider-sample-factor-comparison`

## Input Data

Provider: BaoStock

Normalized CSV:

`.external/qlib_trial/approved_exports/p48_baostock_stock10_etf5_broader_sample_normalized.csv`

Metadata artifact:

`.external/qlib_trial/artifacts/p48_baostock_stock10_etf5_broader_sample_metadata.json`

Observed coverage:

| Field | Value |
|---|---:|
| rows | 4170 |
| instrument_count | 15 |
| stock_count | 10 |
| etf_count | 5 |
| date_min | 2025-01-02 |
| date_max | 2026-06-30 |
| failures | [] |

## Factor Comparison

P48 reused the P47 factor comparison framework.

Candidates:

- `momentum_5d`
- `reversal_1d`
- `volatility_adjusted_momentum_5d`
- `ensemble_mean_rank`

Selection rule:

`max_cost_aware_return_proxy`

Selected candidate:

`ensemble_mean_rank`

Selected metrics:

| Metric | Value |
|---|---:|
| ic | 0.023788554571256105 |
| rank_ic | 0.026659757536809492 |
| cost_aware_return_proxy | 0.00028543188837752226 |
| cost_adjusted_score | 1.0 |

Output artifact:

`.external/qlib_trial/artifacts/p48_baostock_broader_factor_comparison_artifact.json`

Artifact identity:

| Field | Value |
|---|---|
| dataset_id | `p48_baostock_stock10_etf5_broader_sample_20250101_20260701` |
| workflow_config_id | `p48_best_baostock_broader_cost_aware_factor_comparison` |
| profitability_claim | `False` |
| execution_mode | `import_result_only` |
| benchmark | `000300.SH` |

## P44 Loader Validation

P44 artifact loader result:

| Field | Value |
|---|---|
| ok | `True` |
| status | `artifact_loaded` |
| blockers | `()` |

Warnings preserved:

- `baostock_single_provider_only`
- `broader_sample_but_not_production_validation`
- `external_isolated_metric_artifact`
- `no_backtest`
- `no_model_training`
- `no_profitability_claim`
- `no_qrun_workflow`
- `p48_baostock_broader_factor_comparison`

## Interpretation

P48 confirms that the P47 factor-comparison framework can run on a broader BaoStock real-provider sample and produce a P44-loadable artifact.

The selected candidate has a positive cost-aware proxy on this broader sample, but the IC and Rank IC values are weak. This result must not be interpreted as profitability evidence.

## Known Limitation

The current signal construction maps a candidate factor to long/short using a positive-threshold rule:

`signal = 1.0 if factor > 0 else -1.0`

For `ensemble_mean_rank`, this is structurally weak because percentile ranks are usually positive. This can create an almost always-long signal and understate turnover. Therefore, the current `cost_adjusted_score` and turnover proxy should not be treated as production-grade trading evidence.

This limitation should be addressed in the next market-reality phase rather than patched inside P48, because P48's objective is framework reuse and broader-sample artifact generation, not strategy redesign.

## No Profitability Claim

P48 does not claim profitability.

Reasons:

- no qrun workflow
- no model training
- no full backtest
- no fill simulation
- no broker execution
- no A-share T+1 tradability model
- no limit-up/limit-down handling
- no suspension handling
- no capital/account-aware order sizing
- BaoStock is used as a single provider only

## Project Alignment Check

P48 remains aligned with the project constraints:

- profit-first, but no premature profitability claim
- integration-first, reusing the P47 comparison framework
- A-share focused
- broader real-provider sample instead of toy data
- no new generic safety gates
- no broker or live trading
- no tracked `.external/` artifacts

## Next Phase Recommendation

Do not continue expanding generic import-boundary validation after P48.

The next phase should move closer to tradability:

1. Add provider cross-validation with Tushare or another mature provider.
2. Compare BaoStock vs secondary provider OHLCV, adjustment consistency, missing dates, ETF coverage, and volume fields.
3. Build A-share Market Reality Sandbox v1:
   - T+1
   - 100-share board lot
   - fees
   - stamp duty
   - slippage
   - suspension
   - limit up/down
   - cash constraints
   - volume/capacity limits
4. Fix signal-to-position logic for rank-based factors.
5. Add capital-aware paper order generation for 1000 / 10000 / 100000 CNY account sizes.

Recommended next branch:

`p49-provider-cross-validation-and-market-reality-prep`

