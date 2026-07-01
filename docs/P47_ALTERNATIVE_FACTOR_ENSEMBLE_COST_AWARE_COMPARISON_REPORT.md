# P47 Alternative Factor Ensemble Cost-Aware Comparison Report

## Status

Passed.

P47 compared multiple alternative factor candidates on the same P45 real stock + ETF small sample and selected the candidate with the best cost-aware return proxy.

The local `.external/` directory remains ignored and is not committed. It contains temporary runtime scripts and generated artifacts.

## Verified Chain

P45 real stock + ETF sample
-> alternative factor candidates
-> candidate-level IC / Rank IC
-> candidate-level cost-aware proxy
-> selected best candidate by max cost_aware_return_proxy
-> P47 artifact
-> P44 artifact_loader ok=True
-> P44 import_trial ok=True
-> P42 boundary ok=True

## Candidates

Tested candidates:

- momentum_5d
- reversal_1d
- volatility_adjusted_momentum_5d
- ensemble_mean_rank

Selection rule:

max_cost_aware_return_proxy

Selected candidate:

ensemble_mean_rank

## Selected Metrics

ic: 0.1098500154888114
rank_ic: 0.0932660002889823
cost_aware_return_proxy: 0.0003410274379820331
cost_adjusted_score: 1.0

## Improvement Over P46

P46 baseline:

momentum_5d cost_aware_return_proxy: -0.0008995921877558084

P47 selected candidate:

ensemble_mean_rank cost_aware_return_proxy: 0.0003410274379820331

P47 improved the cost-aware proxy from negative to positive on the same small sample.

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

P47 did not perform qrun workflow execution, model training, backtesting, broker integration, paper trading, or live trading.

P47 does not claim profitability.

The selected candidate has a positive cost-aware proxy on a very small 2 stock + 2 ETF sample. This is a candidate-ranking signal only, not a production profitability claim.

## Conclusion

P47 passed as an alternative factor ensemble cost-aware comparison trial.

It proves that the project can compare multiple simple factor candidates on the P45 real stock + ETF sample, select the best candidate by cost-aware proxy, and import the result through the existing P44/P42 boundary.

P47 moves the project from single-factor metric import toward candidate selection and cost-aware factor comparison.

## Recommended Next Step

P48 should expand the same comparison framework to a broader real provider sample while keeping the same import boundary and avoiding new generic safety gates.
