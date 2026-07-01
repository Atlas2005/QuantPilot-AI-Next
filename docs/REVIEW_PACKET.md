# Review Packet

## Task Name

P41: Qlib Real Offline Workflow Spike.

## Changed Files

- `docs/QLIB_REAL_OFFLINE_WORKFLOW_SPIKE.md`
- `docs/REVIEW_PACKET.md`
- `src/quantpilot_core/qlib_real_offline_workflow_spike/__init__.py`
- `src/quantpilot_core/qlib_real_offline_workflow_spike/comparison.py`
- `src/quantpilot_core/qlib_real_offline_workflow_spike/contracts.py`
- `src/quantpilot_core/qlib_real_offline_workflow_spike/dataset_bridge.py`
- `src/quantpilot_core/qlib_real_offline_workflow_spike/evaluation.py`
- `src/quantpilot_core/qlib_real_offline_workflow_spike/factor_mapping.py`
- `src/quantpilot_core/qlib_real_offline_workflow_spike/report.py`
- `src/quantpilot_core/qlib_real_offline_workflow_spike/workflow_config.py`
- `tests/qlib_real_offline_workflow_spike/test_qlib_real_offline_workflow_spike.py`

## Safety Checks

- `src/` changed: Yes. Added standard-library-only P41 Qlib-style local dataset, workflow config, factor mapping, evaluation, comparison, and report boundary.
- Tests changed: Yes. Added deterministic P41 tests.
- Documentation changed: Yes. Added P41 documentation and updated this review packet.
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

P41 moves Qlib from metadata-only handoff to a Qlib-style offline workflow spike.

It builds glue around Qlib boundaries instead of reinventing Qlib: local dataset spec, workflow config, factor candidates, deterministic offline evaluation, optional runtime status, and comparison against the P40 AI-shadow-adjusted mixed ETF replay baseline.

## Open-Source Integration Summary

- Qlib is the primary external framework boundary for this stage.
- Qlib remains optional and is not required for default tests.
- qrun is disabled by default.
- Dataset/workflow metadata is structured for later optional runtime execution.
- P41 does not install dependencies or run a real Qlib backtest.

## Qlib Runtime Status Summary

Default behavior reports optional runtime status explicitly and keeps runtime execution disabled by default. If Qlib is unavailable, P41 reports `UNAVAILABLE_OPTIONAL_DEPENDENCY` while default tests still pass.

## Dataset / Workflow / Factor / Evaluation Summary

- Dataset bridge validates mixed A-share stock and ETF coverage, explicit instrument kind, ETF category, OHLCV fields, date uniqueness, future rows, close/volume, and deterministic date normalization.
- Workflow config includes dataset, universe, benchmark, label placeholder, factor list, train/validation/test placeholders, cost model assumptions, execution assumptions, runtime status, and disabled-by-default runtime flag.
- Factor mapping creates momentum, volatility, liquidity, cost drag, ETF category, capital fit, and AI shadow preference proxies.
- Offline evaluation computes candidate, cost-adjusted, tradability, and small-capital fit scores without claiming real profitability.

## Comparison Against P40

P41 compares Qlib-style offline evaluation with the P40 AI-shadow-adjusted mixed ETF replay baseline and reports mixed stock+ETF support, factor alignment, cost-aware agreement, optional runtime readiness, and promotion blockers.

## Safety Barrier Status

- Pre-P34 estimated barrier: `185.0%`
- P34 through P41 active barrier: `140.0%`
- Target: `<= 140%`
- P41 does not raise the safety barrier. It advances Qlib integration through offline workflow glue under the pruned gate set.

## Validation Commands and Results

`.venv/bin/python -m compileall src`

Result: passed.

`.venv/bin/python -m pytest tests/qlib_real_offline_workflow_spike`

Result: passed.

```text
platform darwin -- Python 3.12.10, pytest-9.1.1
collected 26 items
26 passed in 0.04s
```

`.venv/bin/python -m pytest`

Result: passed.

```text
platform darwin -- Python 3.12.10, pytest-9.1.1
collected 804 items
804 passed in 0.40s
```

## P41 Summary

P41 adds a Qlib-style local dataset bridge, workflow config metadata, factor candidate mapping, deterministic offline evaluation, comparison against P40 AI-shadow-adjusted replay, and report generation.

## Risks

- P41 is not a real Qlib backtest.
- Optional Qlib dependency is not installed or required.
- qrun is disabled by default.
- Scores are deterministic workflow-readiness proxies, not real alpha evidence.
- Provider sample quality and factor quality still need larger approved samples.

## Recommended Next Step

Install an isolated optional Qlib environment outside default pytest and run a controlled manual Qlib runtime spike using the P41 dataset/workflow metadata.

## Code Evidence Snapshot

- `contracts.py`: defines runtime status, dataset source, instrument kind, dataset spec, field mapping, factor, workflow, evaluation, comparison, and report contracts.
- `dataset_bridge.py`: validates and normalizes local mixed stock/ETF records into a Qlib-style dataset spec.
- `workflow_config.py`: builds Qlib-style workflow metadata and detects optional runtime status without requiring Qlib.
- `factor_mapping.py`: maps existing alpha/AI/replay concepts into Qlib-style factor candidates with leakage-control notes.
- `evaluation.py`: computes deterministic offline proxy scores and avoids profitability claims.
- `comparison.py`: compares P41 evaluation with P40 AI-adjusted replay and reports promotion blockers.
- `report.py`: builds the P41 report, keeps safety barrier at `<= 140%`, and selects the next improvement target.
- `tests`: cover dataset validation, workflow config, runtime status, factor mapping, offline evaluation, P40 comparison, promotion blockers, safety barrier, deterministic ordering, and forbidden runtime behavior.
