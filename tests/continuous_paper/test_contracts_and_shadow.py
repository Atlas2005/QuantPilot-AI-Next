from __future__ import annotations

import json

import pytest

from quantpilot_core.continuous_paper.active_shadow import ActiveShadowConfig, ActiveShadowRunner
from quantpilot_core.continuous_paper.contracts import ReportingCycleBundle
from quantpilot_core.continuous_paper.store import InMemoryReportingStore, ReportingConflictError


def _bundle(payload: dict[str, object]) -> ReportingCycleBundle:
    return ReportingCycleBundle(
        session={"session_id": "session-1", "run_id": "run-1", "report_digest": "report"},
        report=payload,
        learning={}, shadow={"mode": "disabled"},
        facts={"paper_orders": (), "paper_fills": (), "paper_positions": (), "paper_equity_curve": (), "paper_reconciliation": ()},
    )


def test_memory_store_replay_is_idempotent_and_conflict_safe() -> None:
    store = InMemoryReportingStore()
    store.persist_cycle(_bundle({"value": 1}))
    store.persist_cycle(_bundle({"value": 1}))
    with pytest.raises(ReportingConflictError):
        store.persist_cycle(_bundle({"value": 2}))


def test_disabled_shadow_has_no_physical_requests(tmp_path) -> None:
    result = ActiveShadowRunner(ActiveShadowConfig(cache_path=tmp_path)).run({"pit": "evidence"})
    assert result["mode"] == "disabled"
    assert result["physical_model_calls"] == 0


def test_malformed_cache_abstains_without_provider_call(tmp_path) -> None:
    (tmp_path / "bad.json").write_text("not json")
    result = ActiveShadowRunner(ActiveShadowConfig(enabled=True, cache_path=tmp_path)).run({"pit": "evidence"})
    assert result["physical_model_calls"] == 0
    assert result["abstentions"] > 0
