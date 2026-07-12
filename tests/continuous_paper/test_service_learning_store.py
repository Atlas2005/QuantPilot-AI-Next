from __future__ import annotations

from types import SimpleNamespace

import pytest

import quantpilot_core.continuous_paper.service as service_module
from quantpilot_core.continuous_paper.active_shadow import ActiveShadowConfig
from quantpilot_core.continuous_paper.contracts import ContinuousPaperCycleConfig, ReportingCycleBundle
from quantpilot_core.continuous_paper.learning import build_learning_payload
from quantpilot_core.continuous_paper.service import ContinuousPaperCycle
from quantpilot_core.continuous_paper.store import InMemoryReportingStore, ReportingConflictError
from quantpilot_core.real_candidate_pipeline import RealCandidatePipelineConfig


def _report() -> dict[str, object]:
    return {
        "session_id": "paper-20260712", "decision_session": "2026-07-12", "execution_session": "2026-07-13",
        "input_digest": "production-input", "order_intents": [{"order_id": "order-1", "symbol": "600000.SH"}],
        "fills": [{"fill_id": "fill-1", "symbol": "600000.SH"}],
        "ledger_after": {"positions": {"600000.SH": 100}, "cash": 900.0},
        "reconciliation_audit": {"reconciliation_id": "reconcile-1", "status": "ok"},
        "quant_firm": {"learning_desk": {"strategy_mutation": {"recommendations": [{"parameter_name": "risk_penalty", "current_value": 1.0, "proposed_value": 1.25, "rationale": "drawdown evidence", "evidence_refs": ["evidence://drawdown"]}]}}},
    }


class _ShadowFailure:
    def __init__(self, _config): pass
    def run(self, _evidence): raise RuntimeError("provider unavailable")


class _ShadowSuccess:
    def __init__(self, _config): pass
    def run(self, _evidence): return {"mode": "active_shadow", "physical_model_calls": 0, "cache_hits": 0, "estimated_api_cost": 0.0, "abstentions": 0}


def _run(monkeypatch, shadow_factory):
    calls = []
    report = _report()
    monkeypatch.setattr(service_module, "load_runtime_manifest", lambda _manifest: {"manifest": "fixed"})
    monkeypatch.setattr(service_module, "manifest_payload", lambda manifest: manifest)
    def pipeline(config, **kwargs):
        calls.append((config, kwargs))
        return SimpleNamespace(daily_paper_loop_result=SimpleNamespace(report=report, status=SimpleNamespace(value="completed")))
    config = ContinuousPaperCycleConfig(RealCandidatePipelineConfig(decision_session="2026-07-12", production_manifest=object()), run_id="run-1", active_shadow=ActiveShadowConfig())
    store = InMemoryReportingStore()
    result = ContinuousPaperCycle(store, pipeline_runner=pipeline, shadow_runner_factory=shadow_factory).run_once(config)
    return result, store, calls


def test_service_calls_production_pipeline_once_and_shadow_failure_is_advisory(monkeypatch) -> None:
    result, store, calls = _run(monkeypatch, _ShadowFailure)
    assert len(calls) == 1
    assert result.status == "completed"
    assert result.shadow_report["mode"] == "abstain"
    assert store.sessions[result.session_id]["production_input_digest"] == "production-input"


def test_shadow_does_not_change_production_session_or_execution_facts(monkeypatch) -> None:
    success, success_store, _ = _run(monkeypatch, _ShadowSuccess)
    failed, failed_store, _ = _run(monkeypatch, _ShadowFailure)
    assert (success.session_id, success.production_input_digest, success.report_digest) == (failed.session_id, failed.production_input_digest, failed.report_digest)
    for table in ("paper_orders", "paper_fills", "paper_positions", "paper_reconciliation"):
        assert success_store.facts[table] == failed_store.facts[table]


def test_learning_proposals_use_real_strategy_mutation_fields() -> None:
    proposal = build_learning_payload(_report(), "paper-20260712")["parameter_proposals"][0]
    assert proposal == {
        "source_session_id": "paper-20260712", "parameter_name": "risk_penalty", "current_value": 1.0,
        "proposed_value": 1.25, "rationale": "drawdown evidence", "supporting_evidence_refs": ("evidence://drawdown",),
        "status": "proposed", "requires_offline_validation": True,
    }


def _bundle(*, session_digest="session", shadow=None, facts=None) -> ReportingCycleBundle:
    return ReportingCycleBundle(
        session={"session_id": "session-1", "run_id": "run-1", "report_digest": session_digest}, report={"report": 1}, learning={},
        shadow=shadow or {"mode": "disabled"}, facts=facts or {"paper_orders": (), "paper_fills": (), "paper_positions": (), "paper_equity_curve": (), "paper_reconciliation": ()},
    )


def test_reporting_store_rolls_back_invalid_cycle_and_detail_rows_are_idempotent() -> None:
    store = InMemoryReportingStore()
    facts = {"paper_orders": ({"session_id": "session-1", "source_identity": "order-1", "source_index": 0, "payload": {"order_id": "order-1"}},), "paper_fills": (), "paper_positions": (), "paper_equity_curve": (), "paper_reconciliation": ()}
    store.persist_cycle(_bundle(facts=facts)); store.persist_cycle(_bundle(facts=facts))
    assert len(store.facts["paper_orders"]) == 1
    with pytest.raises(ValueError): store.persist_cycle(ReportingCycleBundle({"session_id": "bad", "run_id": "run", "report_digest": "x"}, {}, {}, {}, {"not_a_table": ()}))
    assert "bad" not in store.sessions


def test_reporting_store_rejects_conflicting_session_and_shadow_digests() -> None:
    store = InMemoryReportingStore(); store.persist_cycle(_bundle())
    with pytest.raises(ReportingConflictError): store.persist_cycle(_bundle(session_digest="other"))
    with pytest.raises(ReportingConflictError): store.persist_cycle(_bundle(shadow={"mode": "active_shadow", "evidence_digest": "other"}))
