"""Optional deployable Prefect wrapper; imports have no scheduling side effects."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from quantpilot_core.production_candidate import load_runtime_manifest
from quantpilot_core.real_candidate_pipeline import RealCandidatePipelineConfig
from .active_shadow import ActiveShadowConfig
from .contracts import ContinuousPaperCycleConfig
from .service import ContinuousPaperCycle
from .store import PostgreSQLReportingStore

SHANGHAI_TIMEZONE = "Asia/Shanghai"


def retryable_exception(exc: BaseException) -> bool:
    if exc.__class__.__name__ in {"ReportingConflictError", "ValueError", "TypeError"}:
        return False
    return any(word in str(exc).lower() for word in ("connection", "timeout", "temporar", "postgres", "network"))


def prefect_retry_condition(_task: Any, _task_run: Any, state: Any) -> bool:
    """Apply the cycle retry policy using Prefect 3's task callback signature."""
    return retryable_exception(state.result(raise_on_failure=False))


def run_continuous_paper_flow(*, production_manifest_path: str, decision_session: str, state_path: str, report_path: str, run_id: str, dsn_env_var: str = "QUANTPILOT_POSTGRES_DSN", active_shadow: dict[str, Any] | None = None, **pipeline_options: Any) -> Any:
    """Construct all runtime objects from serializable scheduled-flow parameters."""
    dsn = os.environ.get(dsn_env_var)
    if not dsn:
        raise RuntimeError(f"required PostgreSQL DSN environment variable is not set: {dsn_env_var}")
    manifest = load_runtime_manifest(Path(production_manifest_path))
    pipeline = RealCandidatePipelineConfig(decision_session=decision_session, state_path=state_path, report_path=report_path, production_manifest=manifest, **pipeline_options)
    config = ContinuousPaperCycleConfig(pipeline_config=pipeline, run_id=run_id, active_shadow=ActiveShadowConfig(**(active_shadow or {})))
    return ContinuousPaperCycle(PostgreSQLReportingStore(dsn)).run_once(config)


try:
    from prefect import flow, task
except ModuleNotFoundError as exc:
    if exc.name != "prefect":
        raise
    continuous_paper_flow = run_continuous_paper_flow
else:
    # Prefect 3 applies retry conditions to tasks, not flow decorators.  Keep
    # construction import-only; serving remains the explicit script action.
    _run_continuous_paper_task = task(
        name="quantpilot-continuous-paper-cycle-v1",
        retries=2,
        retry_condition_fn=prefect_retry_condition,
    )(run_continuous_paper_flow)

    @flow(name="quantpilot-continuous-paper-v1")
    def continuous_paper_flow(
        *,
        production_manifest_path: str,
        decision_session: str,
        state_path: str,
        report_path: str,
        run_id: str,
        dsn_env_var: str = "QUANTPILOT_POSTGRES_DSN",
        active_shadow: dict[str, Any] | None = None,
        pipeline_options: dict[str, Any] | None = None,
    ) -> Any:
        """Prefect-visible parameters plus an explicit serializable option mapping."""
        return _run_continuous_paper_task(
            production_manifest_path=production_manifest_path,
            decision_session=decision_session,
            state_path=state_path,
            report_path=report_path,
            run_id=run_id,
            dsn_env_var=dsn_env_var,
            active_shadow=active_shadow,
            **(pipeline_options or {}),
        )
