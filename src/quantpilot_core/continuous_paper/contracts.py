"""Public, immutable contracts for one continuous paper-trading cycle."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from quantpilot_core.real_candidate_pipeline import RealCandidatePipelineConfig


@dataclass(frozen=True)
class ContinuousPaperCycleConfig:
    """Inputs owned by orchestration, never by the production strategy."""

    pipeline_config: RealCandidatePipelineConfig
    run_id: str
    prefect_flow_id: str | None = None
    prefect_deployment_id: str | None = None
    prefect_flow_run_id: str | None = None
    active_shadow: Any | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, str) or not self.run_id.strip():
            raise ValueError("run_id must be a non-empty string")
        if not isinstance(self.pipeline_config, RealCandidatePipelineConfig):
            raise TypeError("pipeline_config must be RealCandidatePipelineConfig")


@dataclass(frozen=True)
class ContinuousPaperCycleResult:
    session_id: str
    run_id: str
    status: str
    report_digest: str
    production_input_digest: str
    started_at: datetime
    completed_at: datetime
    replay_status: str
    shadow_report: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReportingCycleBundle:
    """All immutable reporting rows for one production session."""

    session: Mapping[str, Any]
    report: Mapping[str, Any]
    learning: Mapping[str, Any]
    shadow: Mapping[str, Any]
    facts: Mapping[str, tuple[Mapping[str, Any], ...]]

