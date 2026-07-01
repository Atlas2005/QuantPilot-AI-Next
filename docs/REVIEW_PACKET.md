# Review Packet

## Task Name

P43: Isolated Manual Qlib Runtime Trial Runbook.

## Changed Files

- `docs/ISOLATED_MANUAL_QLIB_RUNTIME_TRIAL_RUNBOOK.md`
- `docs/REVIEW_PACKET.md`
- `src/quantpilot_core/isolated_manual_qlib_runtime_trial_runbook/__init__.py`
- `src/quantpilot_core/isolated_manual_qlib_runtime_trial_runbook/artifact_checklist.py`
- `src/quantpilot_core/isolated_manual_qlib_runtime_trial_runbook/command_plan.py`
- `src/quantpilot_core/isolated_manual_qlib_runtime_trial_runbook/contracts.py`
- `src/quantpilot_core/isolated_manual_qlib_runtime_trial_runbook/environment_plan.py`
- `src/quantpilot_core/isolated_manual_qlib_runtime_trial_runbook/report.py`
- `src/quantpilot_core/isolated_manual_qlib_runtime_trial_runbook/result_capture.py`
- `tests/isolated_manual_qlib_runtime_trial_runbook/test_isolated_manual_qlib_runtime_trial_runbook.py`

## Safety Checks

- `src/` changed: Yes. Added standard-library-only P43 isolated manual Qlib runbook, checklist, command template, result template, and report boundary.
- Tests changed: Yes. Added deterministic P43 tests.
- Documentation changed: Yes. Added P43 runbook documentation and updated this review packet.
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

P43 makes the isolated manual Qlib runtime trial executable without polluting the default project environment.

It converts the P41/P42 metadata boundary into a practical runbook: isolated environment plan, required artifact checklist, manual command templates, and a P42-compatible result capture template.

## Open-Source Integration Summary

- Qlib remains optional.
- Installation is documented only and isolated from the default project environment.
- Default tests do not import Qlib or run qrun.
- Manual result capture feeds back into the P42 import boundary.

## Isolated Environment Plan Summary

P43 supports isolated venv, Conda environment, and optional container modes. Each plan preserves the default project environment, avoids dependency-file changes, marks Qlib optional, includes cleanup commands, and records rollback notes.

## Artifact Checklist Summary

The checklist covers dataset spec, workflow config, factor mapping, cost model assumptions, execution assumptions, and result record template. Missing required artifacts block manual readiness.

## Manual Command Plan Summary

The command plan provides documentation-only templates for environment creation, optional Qlib installation, dataset preparation, qrun/by-code execution, result export, and result import. Commands are not executed by default and contain no broker/account/credential path.

## Result Capture Template Summary

The result capture template matches P42 import expectations: local result source, dataset id, workflow config id, benchmark, stock/ETF counts, IC/RankIC placeholders, cost-aware placeholders, import-only execution mode, warnings, and no profitability claim.

## Safety Barrier Status

- Pre-P34 estimated barrier: `185.0%`
- P34 through P43 active barrier: `140.0%`
- Target: `<= 140%`
- P43 does not raise the safety barrier.

## Validation Commands and Results

`.venv/bin/python -m compileall src`

Result: passed.

`.venv/bin/python -m pytest tests/isolated_manual_qlib_runtime_trial_runbook`

Result: passed.

```text
platform darwin -- Python 3.12.10, pytest-9.1.1
collected 23 items
23 passed in 0.04s
```

`.venv/bin/python -m pytest`

Result: passed.

```text
platform darwin -- Python 3.12.10, pytest-9.1.1
collected 853 items
853 passed in 0.47s
```

## P43 Summary

P43 adds an isolated manual Qlib runtime trial runbook with environment plans, artifact checklist, command templates, result capture template, and readiness report.

## Risks

- P43 does not execute a real Qlib run.
- Installation commands are documentation-only and must be manually executed in isolation.
- Result metrics are templates until a manual run produces local artifacts.
- This does not prove profitability.

## Recommended Next Step

Manually run Qlib in an isolated environment, export the local result record, and import it through the P42 boundary.

## Code Evidence Snapshot

- `contracts.py`: defines environment, execution status, artifact kinds, environment plan, checklist, command plan, result template, and report contracts.
- `environment_plan.py`: builds isolated venv/Conda/container plans while preserving default env and project dependency files.
- `artifact_checklist.py`: builds required artifact checklist and blockers.
- `command_plan.py`: creates documentation-only command templates with qrun not executed by default.
- `result_capture.py`: creates P42-compatible local result capture template with profitability claim false.
- `report.py`: builds readiness report and next-step guidance.
- `tests`: cover environment plans, unchanged defaults, artifact checklist, missing artifact blockers, command safety, result template compatibility, readiness states, safety barrier, deterministic ordering, and forbidden runtime behavior.
