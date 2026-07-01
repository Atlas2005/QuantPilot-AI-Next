# Review Packet

## Task Name

P42: Controlled Optional Qlib Runtime Spike.

## Changed Files

- `docs/CONTROLLED_OPTIONAL_QLIB_RUNTIME_SPIKE.md`
- `docs/REVIEW_PACKET.md`
- `src/quantpilot_core/controlled_optional_qlib_runtime_spike/__init__.py`
- `src/quantpilot_core/controlled_optional_qlib_runtime_spike/comparison.py`
- `src/quantpilot_core/controlled_optional_qlib_runtime_spike/contracts.py`
- `src/quantpilot_core/controlled_optional_qlib_runtime_spike/execution_plan.py`
- `src/quantpilot_core/controlled_optional_qlib_runtime_spike/report.py`
- `src/quantpilot_core/controlled_optional_qlib_runtime_spike/result_import.py`
- `src/quantpilot_core/controlled_optional_qlib_runtime_spike/runtime_detection.py`
- `tests/controlled_optional_qlib_runtime_spike/test_controlled_optional_qlib_runtime_spike.py`

## Safety Checks

- `src/` changed: Yes. Added standard-library-only P42 optional runtime detection, manual plan, result import, comparison, and report boundary.
- Tests changed: Yes. Added deterministic P42 tests.
- Documentation changed: Yes. Added P42 documentation and updated this review packet.
- Dependencies changed: No.
- Packages installed: No.
- Packages uninstalled: No.
- `pyproject.toml` changed: No.
- Market data/API used during implementation: No.
- Provider API called during implementation: No.
- Live/remote provider fetch in default tests: No.
- Network calls in default tests: No.
- Production data assets written: No.
- Real data fetched: No.
- DeepSeek/API call added: No.
- OpenAI/API call added: No.
- Runtime LLM call added: No.
- Model training added: No.
- Live strategy weight update added: No.
- Real account API read: No.
- Broker connection added: No.
- Vendor broker SDK imported: No.
- Broker credentials handling added: No.
- Live order path added: No.
- Real order placement added: No.
- Qlib runtime run by default: No.
- qrun run by default: No.
- Qlib required for default pytest: No.
- Real alpha evidence produced: No.
- Profitability claim made: No.
- Generic preflight-only gate added: No.

## Value Orientation

P42 creates a controlled optional Qlib runtime and result import boundary.

It advances open-source integration by preparing manual-local Qlib execution and local result import without making the optional dependency required or running qrun by default.

## Open-Source Integration Summary

- Qlib remains the primary external framework boundary.
- Runtime detection checks optional availability without importing Qlib in default tests.
- Manual execution plan is local-only and user-confirmed.
- Result import boundary can ingest manually produced local runtime-like records.
- No dependencies are installed and no runtime execution occurs by default.

## Qlib Runtime Detection Summary

P42 reports:

- unavailable optional dependency when Qlib is absent
- available but disabled by default when Qlib appears present
- manual execution only when explicitly requested

Network, broker, LLM, and qrun remain disabled by default.

## Manual Execution Plan Summary

The plan includes dataset id, workflow config summary, disabled-by-default qrun flag, manual-local-only flag, user confirmation requirement, no-network/no-broker/no-account requirements, result import path placeholder, warnings, and a statement that default pytest does not execute Qlib.

## Runtime Result Import Summary

The import boundary validates local source, dataset/workflow match, IC/RankIC or missing reason, cost-aware metric or missing reason, explicit benchmark, mixed stock+ETF coverage, manual/import-only mode, warnings, and absence of profitability claims.

## Comparison Against P41/P40 Summary

P42 compares imported runtime-like records against the P41 offline evaluation proxy and P40 replay metadata, then reports score delta, cost-aware agreement, factor-signal agreement, ETF coverage preservation, and promotion decision.

## Safety Barrier Status

- Pre-P34 estimated barrier: `185.0%`
- P34 through P42 active barrier: `140.0%`
- Target: `<= 140%`
- P42 does not raise the safety barrier.

## Validation Commands and Results

`.venv/bin/python -m compileall src`

Result: passed.

`.venv/bin/python -m pytest tests/controlled_optional_qlib_runtime_spike`

Result: passed.

```text
platform darwin -- Python 3.12.10, pytest-9.1.1
collected 26 items
26 passed in 0.06s
```

`.venv/bin/python -m pytest`

Result: passed.

```text
platform darwin -- Python 3.12.10, pytest-9.1.1
collected 830 items
830 passed in 0.44s
```

## P42 Summary

P42 adds optional runtime detection, manual Qlib execution planning, local runtime-like result import validation, comparison against P41/P40, and controlled promotion decision logic.

## Risks

- P42 does not execute a real Qlib run.
- Imported runtime-like records are deterministic local fixtures in tests.
- Real optional runtime trial still requires a separate environment and manual approval.
- Scores are not profitability evidence.

## Recommended Next Step

Prepare an isolated optional Qlib environment and manually generate a local runtime result record for import through the P42 boundary.

## Code Evidence Snapshot

- `contracts.py`: defines optional runtime state, execution mode, detection, plan, result import, comparison, and report contracts.
- `runtime_detection.py`: detects optional availability without importing Qlib and keeps default execution disabled.
- `execution_plan.py`: builds a local-only, user-confirmed manual plan with qrun disabled by default.
- `result_import.py`: validates local runtime-like records and rejects mismatches, missing metrics, missing benchmark, unsafe execution modes, and profitability claims.
- `comparison.py`: compares imported records against P41/P40 direction and computes promotion decisions.
- `report.py`: builds the P42 report, keeps safety barrier at `<= 140%`, and selects next improvement target.
- `tests`: cover runtime detection, manual plan, result import validation, comparison, promotion decisions, safety barrier, deterministic ordering, and forbidden runtime behavior.
