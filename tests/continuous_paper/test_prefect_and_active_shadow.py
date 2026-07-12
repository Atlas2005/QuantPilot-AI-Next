from __future__ import annotations

import importlib

from quantpilot_core.continuous_paper.active_shadow import ActiveShadowConfig, ActiveShadowRunner
from quantpilot_core.quant_firm.deepseek_advisory import DeepSeekAdvisoryRole


def test_prefect_module_import_has_no_scheduling_side_effect(monkeypatch) -> None:
    module = importlib.import_module("quantpilot_core.continuous_paper.prefect_flow")
    assert module.SHANGHAI_TIMEZONE == "Asia/Shanghai"
    assert module.retryable_exception(ValueError("manifest mismatch")) is False
    assert module.retryable_exception(RuntimeError("connection reset")) is True


class _FailingAgent:
    config = type("Config", (), {"model": "test-model"})()
    def advise(self, _input): raise RuntimeError("provider failed")


class _RecordingAgent:
    config = type("Config", (), {"model": "test-model"})()
    def __init__(self): self.inputs = []
    def advise(self, advisory_input):
        self.inputs.append(advisory_input)
        return {"status": "advisory", "role": advisory_input.role.value}


def test_failed_provider_counts_physical_request_and_cost(tmp_path) -> None:
    config = ActiveShadowConfig(enabled=True, enable_live_calls=True, max_physical_model_calls_per_cycle=1, max_estimated_cost_per_cycle=2.0, estimated_cost_per_call=1.0, cache_path=tmp_path, allow_roles=(DeepSeekAdvisoryRole.RESEARCH_DESK,))
    result = ActiveShadowRunner(config, agent=_FailingAgent()).run({"pit": "safe"})
    assert result["physical_model_calls"] == 1
    assert result["estimated_api_cost"] == 1.0
    assert result["abstentions"] == 1


def test_cost_cap_prevents_physical_request(tmp_path) -> None:
    config = ActiveShadowConfig(enabled=True, enable_live_calls=True, max_physical_model_calls_per_cycle=1, max_estimated_cost_per_cycle=0.5, estimated_cost_per_call=1.0, cache_path=tmp_path, allow_roles=(DeepSeekAdvisoryRole.RESEARCH_DESK,))
    result = ActiveShadowRunner(config, agent=_FailingAgent()).run({"pit": "safe"})
    assert result["physical_model_calls"] == 0
    assert result["roles"][DeepSeekAdvisoryRole.RESEARCH_DESK.value]["reason"] == "cost_budget_exhausted"


def test_committee_receives_bound_specialist_evidence_digests(tmp_path) -> None:
    agent = _RecordingAgent()
    roles = (DeepSeekAdvisoryRole.RESEARCH_DESK, DeepSeekAdvisoryRole.INVESTMENT_COMMITTEE)
    config = ActiveShadowConfig(enabled=True, enable_live_calls=True, max_physical_model_calls_per_cycle=2, max_estimated_cost_per_cycle=2.0, estimated_cost_per_call=1.0, cache_path=tmp_path, allow_roles=roles)
    ActiveShadowRunner(config, agent=agent).run({"pit": "safe"})
    committee_input = agent.inputs[-1].quant_firm_decision_report_summary
    assert committee_input["specialist_evidence_digests"]
