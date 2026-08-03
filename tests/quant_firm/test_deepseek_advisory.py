from __future__ import annotations

import builtins
from types import SimpleNamespace

import pytest
import quantpilot_core.quant_firm.deepseek_advisory as advisory_module

from quantpilot_core.deepseek_multi_agent import DEEPSEEK_V4_FLASH, DEEPSEEK_V4_PRO
from quantpilot_core.quant_firm.deepseek_advisory import JSON_OUTPUT_CONTRACT_LINES
from quantpilot_core.quant_firm import (
    DeepSeekAdvisoryAgent,
    DeepSeekAdvisoryInput,
    DeepSeekAdvisoryOutput,
    DeepSeekAdvisoryRole,
    DeepSeekClientConfig,
    DeepSeekStructuredEvidenceClient,
    QuantFirmDeepSeekModelPolicy,
    run_deepseek_advisory_fallback,
    run_quant_firm_decision_cycle,
)


def rich_advisory_input(role: DeepSeekAdvisoryRole) -> DeepSeekAdvisoryInput:
    return DeepSeekAdvisoryInput(
        role=role,
        learning_desk_output={"primary_failure": "high_cost_drag", "mutation": "increase_turnover_penalty"},
        quant_firm_decision_report_summary={"final_recommendation": "approve_offline_shadow_cycle"},
        research_committee_summary={"ranking": ["factor_a", "factor_b"]},
        information_agent_summary={"northbound": "supportive", "moneyflow": "mixed"},
        execution_candidate_report_summary={"strategy_id": "EXEC1", "candidate_count": 2},
        portfolio_allocation_plan_summary={"strategy_id": "EXEC1:EXEC2", "max_weight": 0.55},
        vectorbt_stats={"total_return": -0.02, "max_drawdown": -0.09},
        qlib_report={"information_coefficient": 0.04},
        rqalpha_artifact_summary={"status": "offline_artifact_ready"},
        cost_after_fill_metrics={"cost_drag": 0.007},
        current_parameters={"holding_period": 5, "turnover_penalty": 0.02},
        market_regime="risk_off",
        run_label="unit-test-run",
    )


def test_default_config_uses_v4_flash() -> None:
    assert DeepSeekClientConfig().model == DEEPSEEK_V4_FLASH


def test_deprecated_deepseek_chat_normalizes_to_v4_flash() -> None:
    policy = QuantFirmDeepSeekModelPolicy()

    selection = policy.normalize_requested_model("deepseek-chat")

    assert selection.model == DEEPSEEK_V4_FLASH
    assert "deprecated_model_normalized:deepseek-chat->deepseek-v4-flash" in selection.warnings
    assert DeepSeekClientConfig(model="deepseek-chat").model == DEEPSEEK_V4_FLASH


def test_deprecated_config_model_warning_is_preserved_in_fallback_notes() -> None:
    output = DeepSeekAdvisoryAgent(DeepSeekClientConfig(model="deepseek-chat")).advise(
        rich_advisory_input(DeepSeekAdvisoryRole.RESEARCH_DESK)
    )

    assert output.is_fallback is True
    assert "deepseek_model:deepseek-v4-flash" in output.tool_integration_notes
    assert (
        "deprecated_model_normalized:deepseek-chat->deepseek-v4-flash"
        in output.tool_integration_notes
    )


def test_deprecated_deepseek_reasoner_normalizes_to_v4_pro() -> None:
    policy = QuantFirmDeepSeekModelPolicy()

    selection = policy.normalize_requested_model("deepseek-reasoner")

    assert selection.model == DEEPSEEK_V4_PRO
    assert "deprecated_model_normalized:deepseek-reasoner->deepseek-v4-pro" in selection.warnings
    assert DeepSeekClientConfig(model="deepseek-reasoner").model == DEEPSEEK_V4_PRO


def test_role_model_policy_maps_roles_to_model_and_reasoning_defaults() -> None:
    policy = QuantFirmDeepSeekModelPolicy()
    expected = {
        DeepSeekAdvisoryRole.INFORMATION_DESK: (DEEPSEEK_V4_FLASH, False, "low"),
        DeepSeekAdvisoryRole.BACKTEST_DESK: (DEEPSEEK_V4_FLASH, False, "low"),
        DeepSeekAdvisoryRole.EXECUTION_SIMULATION_DESK: (DEEPSEEK_V4_FLASH, False, "low"),
        DeepSeekAdvisoryRole.RESEARCH_DESK: (DEEPSEEK_V4_PRO, True, "medium"),
        DeepSeekAdvisoryRole.PORTFOLIO_DESK: (DEEPSEEK_V4_PRO, True, "medium"),
        DeepSeekAdvisoryRole.LEARNING_DESK: (DEEPSEEK_V4_PRO, True, "high"),
        DeepSeekAdvisoryRole.INVESTMENT_COMMITTEE: (DEEPSEEK_V4_PRO, True, "high"),
    }

    for role, values in expected.items():
        selection = policy.selection_for(role)

        assert (selection.model, selection.enable_thinking, selection.reasoning_effort) == values


def test_explicit_config_model_overrides_role_default() -> None:
    selection = QuantFirmDeepSeekModelPolicy().selection_for(
        DeepSeekAdvisoryRole.INVESTMENT_COMMITTEE,
        DeepSeekClientConfig(model=DEEPSEEK_V4_FLASH),
    )

    assert selection.model == DEEPSEEK_V4_FLASH
    assert selection.enable_thinking is True
    assert selection.reasoning_effort == "high"


def test_environment_model_policy_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_MODEL_DEFAULT", "deepseek-v4-flash-env")
    monkeypatch.setenv("DEEPSEEK_MODEL_FLASH", "deepseek-v4-flash-env")
    monkeypatch.setenv("DEEPSEEK_MODEL_PRO", "deepseek-v4-pro-env")
    monkeypatch.setenv("DEEPSEEK_REASONING_EFFORT_DEFAULT", "minimal")

    policy = QuantFirmDeepSeekModelPolicy.from_environment()

    assert DeepSeekClientConfig().model == "deepseek-v4-flash-env"
    assert (
        policy.selection_for(DeepSeekAdvisoryRole.BACKTEST_DESK).model
        == "deepseek-v4-flash-env"
    )
    assert (
        policy.selection_for(DeepSeekAdvisoryRole.BACKTEST_DESK).reasoning_effort
        == "minimal"
    )
    assert policy.selection_for(DeepSeekAdvisoryRole.RESEARCH_DESK).model == "deepseek-v4-pro-env"


def test_missing_api_key_returns_deterministic_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    agent = DeepSeekAdvisoryAgent(DeepSeekClientConfig(enable_live_call=True))

    output = agent.advise(rich_advisory_input(DeepSeekAdvisoryRole.BACKTEST_DESK))

    assert output.is_fallback is True
    assert output.used_model == "deterministic_fallback"
    assert output.role is DeepSeekAdvisoryRole.BACKTEST_DESK
    assert "vectorbt_stats" in output.evidence_used
    assert "advisory_only_no_network_call" in output.tool_integration_notes


def test_default_mode_never_calls_live_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "present-but-disabled")

    def fail_live_call(*args, **kwargs):
        raise AssertionError("live DeepSeek path must not run by default")

    monkeypatch.setattr(DeepSeekAdvisoryAgent, "_live_advisory", fail_live_call)

    output = DeepSeekAdvisoryAgent().advise(rich_advisory_input(DeepSeekAdvisoryRole.RESEARCH_DESK))

    assert output.is_fallback is True
    assert output.used_model == "deterministic_fallback"


def test_missing_key_path_does_not_import_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "openai":
            raise AssertionError("openai must be imported only on keyed live calls")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    output = DeepSeekAdvisoryAgent(DeepSeekClientConfig(enable_live_call=True)).advise(
        rich_advisory_input(DeepSeekAdvisoryRole.INVESTMENT_COMMITTEE)
    )

    assert output.is_fallback is True


def test_live_agent_uses_existing_structured_http_client_by_default() -> None:
    agent = DeepSeekAdvisoryAgent(DeepSeekClientConfig(enable_live_call=True))
    assert isinstance(agent.live_client, DeepSeekStructuredEvidenceClient)
    assert agent.physical_model_calls == 0


def test_live_agent_uses_transport_model_usage_and_physical_counter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "process-secret")

    class _Transport:
        def __init__(self) -> None:
            self.physical_request_count = 0
            self.requests = []

        def __call__(self, request):
            self.requests.append(request)
            self.physical_request_count += 1
            return {
                "content": "real transport response",
                "model": "deepseek-runtime-model",
                "usage": {"prompt_tokens": 41, "completion_tokens": 9},
                "finish_reason": "stop",
            }

    transport = _Transport()
    agent = DeepSeekAdvisoryAgent(
        DeepSeekClientConfig(enable_live_call=True),
        live_client=transport,
    )
    output = agent.advise(
        rich_advisory_input(DeepSeekAdvisoryRole.RESEARCH_DESK)
    )
    assert agent.physical_model_calls == 1
    assert output.is_fallback is False
    assert output.used_model == "deepseek-runtime-model"
    assert output.raw_response_usage == {"prompt_tokens": 41, "completion_tokens": 9}
    assert transport.requests[0]["reasoning_mode"] == "medium"


def test_existing_structured_client_counts_only_chat_completion_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "process-secret")
    requests = []

    class _Completions:
        def create(self, **kwargs):
            requests.append(kwargs)
            return SimpleNamespace(
                model="deepseek-response-model",
                choices=[SimpleNamespace(
                    message=SimpleNamespace(content="transport content"),
                    finish_reason="stop",
                )],
                usage=SimpleNamespace(
                    prompt_tokens=12,
                    prompt_cache_hit_tokens=2,
                    prompt_cache_miss_tokens=10,
                    completion_tokens=3,
                ),
            )

    fake_module = SimpleNamespace(
        OpenAI=lambda **_kwargs: SimpleNamespace(
            chat=SimpleNamespace(completions=_Completions())
        )
    )
    monkeypatch.setattr(advisory_module, "import_module", lambda _name: fake_module)
    client = DeepSeekStructuredEvidenceClient(
        DeepSeekClientConfig(enable_live_call=True)
    )
    expected_messages = [
        {
            "role": "user",
            "content": "Return exactly one valid JSON object containing the evidence.",
        }
    ]
    response = client({
        "model": "deepseek-request-model",
        "messages": expected_messages,
        "reasoning_mode": "low",
        "enable_thinking": False,
    })
    assert client.physical_request_count == 1
    assert len(requests) == 1
    assert requests[0]["messages"] == expected_messages
    assert any(
        "json" in str(message.get("content", "")).lower()
        for message in requests[0]["messages"]
    )
    assert requests[0]["response_format"] == {"type": "json_object"}
    assert response["model"] == "deepseek-response-model"
    assert response["usage"]["prompt_tokens"] == 12


def test_structured_client_dependency_failure_is_not_a_physical_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "process-secret")

    def missing(_name):
        raise ImportError("runtime missing")

    monkeypatch.setattr(advisory_module, "import_module", missing)
    client = DeepSeekStructuredEvidenceClient(
        DeepSeekClientConfig(enable_live_call=True)
    )
    with pytest.raises(RuntimeError, match="runtime is unavailable"):
        client({"model": "m", "messages": []})
    assert client.physical_request_count == 0


def test_each_advisory_role_builds_role_specific_fallback_output() -> None:
    for role in DeepSeekAdvisoryRole:
        output = DeepSeekAdvisoryAgent().advise(rich_advisory_input(role))

        assert output.role is role
        assert role.value in output.advisory_summary
        assert output.parameter_tuning_suggestions
        assert output.research_directions
        assert output.risk_notes
        assert output.confidence > 0


def test_all_seven_desks_share_one_json_output_contract() -> None:
    for role in DeepSeekAdvisoryRole:
        prompt = DeepSeekAdvisoryAgent().build_prompt(rich_advisory_input(role))

        assert all(line in prompt for line in JSON_OUTPUT_CONTRACT_LINES)


def test_shared_json_contract_specifies_single_object_json_only_no_fence_no_prose() -> None:
    prompt = DeepSeekAdvisoryAgent().build_prompt(
        rich_advisory_input(DeepSeekAdvisoryRole.RESEARCH_DESK)
    )

    assert "Return exactly one valid JSON object." in prompt
    assert "The response must be JSON only." in prompt
    assert "Do not use Markdown code fences." in prompt
    assert "Do not include prose before or after the JSON object." in prompt
    assert "```" not in prompt


def test_live_request_messages_contain_json_word_for_every_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "process-secret")

    class _Transport:
        def __init__(self) -> None:
            self.requests = []
            self.physical_request_count = 0

        def __call__(self, request):
            self.requests.append(request)
            self.physical_request_count += 1
            return {
                "content": "real transport response",
                "model": "deepseek-runtime-model",
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                "finish_reason": "stop",
            }

    transport = _Transport()
    agent = DeepSeekAdvisoryAgent(
        DeepSeekClientConfig(enable_live_call=True),
        live_client=transport,
    )
    for role in DeepSeekAdvisoryRole:
        output = agent.advise(rich_advisory_input(role))
        assert output.is_fallback is False
    assert len(transport.requests) == len(list(DeepSeekAdvisoryRole))
    for request in transport.requests:
        messages = [str(item.get("content", "")) for item in request["messages"]]
        assert any("json" in message.lower() for message in messages)


def test_prompt_includes_mature_framework_evidence_and_execution_exclusions() -> None:
    prompt = DeepSeekAdvisoryAgent().build_prompt(rich_advisory_input(DeepSeekAdvisoryRole.BACKTEST_DESK))

    assert "learning_desk_output" in prompt
    assert "vectorbt_stats" in prompt
    assert "qlib_report" in prompt
    assert "rqalpha_artifact_summary" in prompt
    assert "execution_candidate_report_summary" in prompt
    assert "portfolio_allocation_plan_summary" in prompt
    assert "Do not connect to a broker or live trading system." in prompt
    assert "Do not emit order execution commands." in prompt
    assert "Do not act as a hard-block safety gate." in prompt
    assert "Do not replace deterministic EXEC1" in prompt


def test_orchestrator_can_include_selected_fallback_deepseek_advisory() -> None:
    decision = run_quant_firm_decision_cycle(
        include_deepseek_advisory=True,
        deepseek_advisory_roles=(
            DeepSeekAdvisoryRole.PORTFOLIO_DESK,
            DeepSeekAdvisoryRole.LEARNING_DESK,
        ),
        context={
            "market_regime": "risk_off",
            "qlib_report": {"ic": 0.03},
            "cost_after_fill_metrics": {"cost_drag": 0.006},
        },
    )

    assert len(decision.deepseek_advisory) == 2
    assert [item.role for item in decision.deepseek_advisory] == [
        DeepSeekAdvisoryRole.PORTFOLIO_DESK,
        DeepSeekAdvisoryRole.LEARNING_DESK,
    ]
    assert all(item.is_fallback for item in decision.deepseek_advisory)
    assert decision.external_side_effects == ()
    assert decision.broker_adapter_enabled is False


def test_registry_fallback_wrapper_is_advisory_only() -> None:
    output = run_deepseek_advisory_fallback(
        DeepSeekAdvisoryRole.EXECUTION_SIMULATION_DESK,
        vectorbt_stats={"turnover_proxy": 0.8},
        market_regime="risk_off",
    )

    assert isinstance(output, DeepSeekAdvisoryOutput)
    assert output.is_fallback is True
    assert output.role is DeepSeekAdvisoryRole.EXECUTION_SIMULATION_DESK
    assert "no_broker_or_live_execution_path" in output.tool_integration_notes
