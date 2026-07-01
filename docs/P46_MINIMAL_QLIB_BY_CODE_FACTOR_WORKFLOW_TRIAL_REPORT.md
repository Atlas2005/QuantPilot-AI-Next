# P46 Minimal Qlib By-Code Factor Workflow Trial Report

## Status

Passed.

P46 completed a minimal by-code factor metric trial on the P45 real stock + ETF small sample and connected the result back into the existing P44/P42 import boundary.

The local `.external/` directory is intentionally ignored and not committed. It contains the temporary runtime scripts and generated artifacts.

## Verified Chain

P45 real stock + ETF sample
-> normalized CSV
-> 5-day momentum factor
-> next-day return target
-> IC / Rank IC calculation
-> cost-aware return proxy
-> P46 metric artifact
-> P44 artifact_loader ok=True
-> P44 import_trial ok=True
-> P42 boundary ok=True

## Runtime Data

Source dataset:

p45_eastmoney_direct_stock_etf_small_sample_20251103_20260701

Workflow config:

p46_minimal_factor_momentum_5d_next_return_1d

Coverage:

stock_count: 2
etf_count: 2
evaluation_rows: 616
daily_ic_rows: 154

## Factor and Target

Factor:

5-day close momentum, computed as close percentage change over 5 trading rows per instrument.

Target:

next-day close return, computed as the next 1-day percentage return per instrument.

## Metrics

ic: 0.1034606094217383
rank_ic: 0.09090909090909091
cost_aware_return_proxy: -0.0008995921877558084
cost_adjusted_score: -1.7752713115306744

## Import Boundary Result

P44 loader:

ok: True
blockers: ()

P44 import trial:

ok: True
status: import_accepted
artifact_loaded: True
import_accepted: True
rejection_reasons: ()
dataset_workflow_match: True
benchmark_present: True
mixed_stock_etf_coverage_preserved: True
ic_rankic_available: True
cost_aware_metric_available: True
profitability_claim_rejected: True

P42 boundary:

ok=True
runtime_state=manual_runtime_result_imported
blockers=()

## Explicit Non-Claims

P46 did not perform qrun workflow execution, model training, backtesting, broker integration, paper trading, or live trading.

P46 does not claim profitability.

The cost-aware proxy is negative in this small sample, so the correct interpretation is that the minimal 5-day momentum factor produced usable metrics but did not produce a positive cost-aware proxy.

## Conclusion

P46 passed as a minimal real-data factor metric import trial.

It proves that the project can compute basic factor-quality metrics from the P45 real stock + ETF sample and import those metrics through the existing P44/P42 boundary.

P46 does not prove production model quality, profitability, tradability, or execution readiness.

## Recommended Next Step

P47 should test at least one alternative minimal factor or ensemble comparison on the same real small sample, with the explicit goal of improving cost-aware proxy without adding new generic safety gates.
