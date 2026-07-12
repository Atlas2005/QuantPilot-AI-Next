"""Application service coordinating exactly one existing production paper cycle."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from quantpilot_core.production_candidate import load_runtime_manifest, manifest_payload
from quantpilot_core.real_candidate_pipeline import run_real_candidate_daily_paper

from .active_shadow import ActiveShadowConfig, ActiveShadowRunner
from .contracts import ContinuousPaperCycleConfig, ContinuousPaperCycleResult, ReportingCycleBundle
from .facts import extract_daily_report_facts
from .learning import build_learning_payload
from .store import InMemoryReportingStore, ReportingStore, payload_digest


class ContinuousPaperCycle:
    def __init__(self, store: ReportingStore | None = None, *, pipeline_runner: Callable[..., Any] = run_real_candidate_daily_paper, shadow_runner_factory: Callable[[ActiveShadowConfig], Any] = ActiveShadowRunner, clock: Callable[[], datetime] | None = None) -> None:
        self.store = store or InMemoryReportingStore()
        self.pipeline_runner = pipeline_runner
        self.shadow_runner_factory = shadow_runner_factory
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def run_once(self, config: ContinuousPaperCycleConfig, **pipeline_dependencies: Any) -> ContinuousPaperCycleResult:
        self.store.initialize()
        # Validate strict manifest binding before production work begins.
        manifest = load_runtime_manifest(config.pipeline_config.production_manifest)
        started_at = self.clock()
        pipeline_result = self.pipeline_runner(config.pipeline_config, **pipeline_dependencies)
        daily = pipeline_result.daily_paper_loop_result
        if daily is None:
            raise RuntimeError("real_candidate_pipeline did not produce a daily paper result")
        report = dict(daily.report)
        session_id = str(report.get("session_id", ""))
        if not session_id:
            raise ValueError("daily paper report must contain session_id")
        report_digest = payload_digest(report)
        production_input_digest = str(report.get("input_digest", ""))
        completed_at = self.clock()
        shadow_config = config.active_shadow if isinstance(config.active_shadow, ActiveShadowConfig) else ActiveShadowConfig()
        provisional_learning = build_learning_payload(report, session_id)
        try:
            shadow = self.shadow_runner_factory(shadow_config).run({"session_id": session_id, "daily_report": report, "learning_desk": provisional_learning})
        except Exception as exc:  # Defensive boundary: advisory never loses production facts.
            shadow = {"mode": "abstain", "evidence_digest": payload_digest(report), "physical_model_calls": 0, "cache_hits": 0, "estimated_api_cost": 0.0, "abstentions": 1, "reason": f"shadow_runner_failure:{type(exc).__name__}"}
        delta = _production_shadow_delta(report, shadow)
        learning = build_learning_payload(report, session_id, delta)
        session = {
            "session_id": session_id, "run_id": config.run_id, "decision_session": report["decision_session"],
            "execution_session": report.get("execution_session"), "status": daily.status.value,
            "strategy_id": config.pipeline_config.strategy_id,
            "production_manifest_digest": payload_digest(manifest_payload(manifest)),
            "effective_parameter_digest": report.get("effective_parameter_digest"),
            "production_input_digest": production_input_digest,
            "state_hash_before": report.get("state_hash_before"), "state_hash_after": report.get("state_hash_after"),
            "prefect_flow_id": config.prefect_flow_id, "prefect_deployment_id": config.prefect_deployment_id,
            "prefect_flow_run_id": config.prefect_flow_run_id, "replay_status": daily.status.value,
            "failure_class": None, "failure_reason": None, "started_at": started_at, "completed_at": completed_at,
            "report_digest": report_digest,
        }
        self.store.persist_cycle(ReportingCycleBundle(session, report, learning, shadow, extract_daily_report_facts(report)))
        return ContinuousPaperCycleResult(session_id, config.run_id, daily.status.value, report_digest, production_input_digest, started_at, completed_at, daily.status.value, shadow)


def _production_shadow_delta(report: Mapping[str, Any], shadow: Mapping[str, Any]) -> Mapping[str, Any]:
    """A reporting comparison only; does not feed any execution artifact."""
    return {"production_report_digest": payload_digest(report), "shadow_digest": payload_digest(shadow), "shadow_mode": shadow.get("mode"), "shadow_abstentions": shadow.get("abstentions", 0)}
