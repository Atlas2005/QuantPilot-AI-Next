from __future__ import annotations

import importlib
import inspect
import sys
import types

import pytest

from quantpilot_core.continuous_paper.active_shadow import ActiveShadowConfig, ActiveShadowRunner
from quantpilot_core.quant_firm.deepseek_advisory import DeepSeekAdvisoryRole


def test_prefect_module_import_has_no_scheduling_side_effect(monkeypatch) -> None:
    module = importlib.import_module("quantpilot_core.continuous_paper.prefect_flow")
    assert module.SHANGHAI_TIMEZONE == "Asia/Shanghai"
    assert module.retryable_exception(ValueError("manifest mismatch")) is False
    assert module.retryable_exception(RuntimeError("connection reset")) is True


def test_prefect_v3_retry_condition_is_attached_to_task(monkeypatch) -> None:
    captured: dict[str, dict[str, object]] = {}

    def decorator(kind: str):
        def factory(**kwargs):
            captured[kind] = kwargs
            return lambda function: function
        return factory

    fake_prefect = types.ModuleType("prefect")
    fake_prefect.flow = decorator("flow")
    fake_prefect.task = decorator("task")
    with monkeypatch.context() as scoped:
        scoped.setitem(sys.modules, "prefect", fake_prefect)
        scoped.delitem(sys.modules, "quantpilot_core.continuous_paper.prefect_flow", raising=False)
        module = importlib.import_module("quantpilot_core.continuous_paper.prefect_flow")

    assert captured["flow"] == {"name": "quantpilot-continuous-paper-v1"}
    assert captured["task"]["retries"] == 2
    assert captured["task"]["retry_condition_fn"] is module.prefect_retry_condition

    state = types.SimpleNamespace(result=lambda *, raise_on_failure: RuntimeError("connection reset"))
    assert module.prefect_retry_condition(None, None, state) is True
    sys.modules.pop("quantpilot_core.continuous_paper.prefect_flow", None)
    importlib.import_module("quantpilot_core.continuous_paper.prefect_flow")


def test_serve_helper_uses_timezone_aware_prefect_schedule(monkeypatch) -> None:
    from scripts import serve_continuous_paper_v1 as serve_script

    captured: dict[str, object] = {}

    class FakeFlow:
        def serve(self, **kwargs):
            captured["serve"] = kwargs

    def fake_cron(expression, *, timezone):
        captured["cron"] = (expression, timezone)
        return "schedule"

    fake_flow_module = types.ModuleType("quantpilot_core.continuous_paper.prefect_flow")
    fake_flow_module.continuous_paper_flow = FakeFlow()
    fake_prefect = types.ModuleType("prefect")
    fake_prefect.__path__ = []
    fake_schedules = types.ModuleType("prefect.schedules")
    fake_schedules.Cron = fake_cron
    argv = [
        "serve_continuous_paper_v1.py",
        "--production-manifest", "manifest.json",
        "--decision-session", "2026-07-13",
        "--state-path", "state.json",
        "--report-path", "report.json",
        "--run-id", "run-1",
        "--timezone", "Asia/Shanghai",
    ]
    with monkeypatch.context() as scoped:
        scoped.setitem(sys.modules, "quantpilot_core.continuous_paper.prefect_flow", fake_flow_module)
        scoped.setitem(sys.modules, "prefect", fake_prefect)
        scoped.setitem(sys.modules, "prefect.schedules", fake_schedules)
        scoped.setattr(sys, "argv", argv)
        serve_script.main()

    assert captured["cron"] == ("30 16 * * 1-5", "Asia/Shanghai")
    serve_kwargs = captured["serve"]
    assert serve_kwargs["schedules"] == ["schedule"]
    assert "timezone" not in serve_kwargs and "cron" not in serve_kwargs
    assert serve_kwargs["parameters"]["decision_session"] == "2026-07-13"


def test_real_prefect_flow_smoke_has_explicit_parameters_and_no_deployment(monkeypatch) -> None:
    prefect = pytest.importorskip("prefect")
    from prefect.flows import Flow

    with monkeypatch.context() as scoped:
        scoped.setattr(Flow, "serve", lambda *_args, **_kwargs: pytest.fail("import must not create a deployment"))
        scoped.delitem(sys.modules, "quantpilot_core.continuous_paper.prefect_flow", raising=False)
        module = importlib.import_module("quantpilot_core.continuous_paper.prefect_flow")

    assert isinstance(module.continuous_paper_flow, Flow)
    assert module._run_continuous_paper_task.retries == 2
    assert module._run_continuous_paper_task.retry_condition_fn is module.prefect_retry_condition
    parameters = inspect.signature(module.continuous_paper_flow.fn).parameters
    assert set(("production_manifest_path", "decision_session", "state_path", "report_path", "run_id", "pipeline_options")) <= set(parameters)
    assert prefect.__version__.split(".")[0] == "3"


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
