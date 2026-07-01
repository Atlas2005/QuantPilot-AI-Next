# P45 Real Isolated Qlib Runtime Trial Report

## Status

Passed.

P45 completed a real isolated Qlib data-layer runtime trial and connected the result back into the existing P44/P42 import boundary.

The local `.external/` directory is intentionally ignored and not committed. It contains the isolated venv, cloned Qlib repo, CSV exports, Qlib `.bin` files, and generated local artifacts.

## Verified Chain

Eastmoney direct real data
-> approved local CSV
-> normalized CSV
-> Qlib input CSV
-> by-symbol CSV
-> Qlib .bin dataset
-> qlib.init
-> D.features read
-> P45 evidence JSON
-> P44-compatible artifact JSON
-> P44 artifact_loader ok=True
-> P44 import_trial ok=True
-> P42 boundary ok=True

## Runtime Data

Instruments:

000001  Ping An Bank
600519  Kweichow Moutai
510300  CSI 300 ETF
159915  ChiNext ETF

Coverage:

date range: 2025-11-03 -> 2026-07-01
rows per instrument: 160
total rows: 640
stock count: 2
ETF count: 2

Qlib runtime read:

shape: (640, 6)
index names: instrument, datetime
fields: open, high, low, close, volume, amount
non-null counts: 640 for each field

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
profitability_claim_rejected: True

P42 boundary:

ok=True
runtime_state=manual_runtime_result_imported
blockers=()

## Explicit Non-Claims

P45 did not perform model training, qrun workflow execution, backtesting, profitability validation, broker integration, or paper/live trading execution.

Missing metrics were correctly declared:

ic_rankic_available: False
cost_aware_metric_available: False

## Conclusion

P45 passed as a real Qlib data-layer runtime smoke trial.

It proves that the project can ingest a real small stock + ETF provider sample into Qlib runtime format and connect the evidence back into the existing P44/P42 import boundary.

P45 does not prove model quality, factor validity, profitability, or execution readiness.

## Recommended Next Step

P46 should run a minimal Qlib by-code factor/workflow trial on the same small sample and produce real factor or prediction metrics without making unsupported profitability claims.
