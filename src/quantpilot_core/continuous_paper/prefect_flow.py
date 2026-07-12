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
    from prefect import flow
    continuous_paper_flow = flow(name="quantpilot-continuous-paper-v1", retries=2, retry_condition_fn=lambda _task, _state, _run: retryable_exception(_state.result(raise_on_failure=False)))(run_continuous_paper_flow)
except ImportError:
    continuous_paper_flow = run_continuous_paper_flow
