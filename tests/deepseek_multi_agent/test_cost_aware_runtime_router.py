import pytest

from quantpilot_core.deepseek_multi_agent import (
    DEEPSEEK_V4_FLASH,
    DEEPSEEK_V4_PRO,
    AgentRole,
    CostBudgetPolicy,
    FakeAIClient,
    ModelPrice,
    ModelRouteRequest,
    RuntimeProvider,
    RuntimeTaskCategory,
    TokenEstimate,
    estimate_model_call_cost_usd,
    route_model_for_request,
)


def budget(**overrides):
    values = {
        "max_usd_per_run": 1.0,
        "max_usd_per_day": 10.0,
        "max_tokens_per_agent_call": 100_000,
        "allow_defer": False,
    }
    values.update(overrides)
    return CostBudgetPolicy(**values)


def route_request(**overrides):
    values = {
        "provider": RuntimeProvider.DEEPSEEK,
        "role": AgentRole.NEWS_AGENT,
        "task_category": RuntimeTaskCategory.NEWS_EVENT,
        "as_of_time_bjt": "2026-06-30T10:00:00",
        "token_estimate": TokenEstimate(
            input_tokens=1000,
            output_tokens=200,
            cache_hit_input_tokens=100,
        ),
        "critical": False,
        "proposed_trade_exists": False,
        "budget_policy": budget(),
        "requested_model": None,
    }
    values.update(overrides)
    return ModelRouteRequest(**values)


def test_flash_is_selected_for_news_event() -> None:
    decision = route_model_for_request(route_request())

    assert decision.ok is True
    assert decision.model == DEEPSEEK_V4_FLASH
    assert decision.uses_llm is True


def test_hard_gate_tasks_use_no_llm() -> None:
    decision = route_model_for_request(
        route_request(task_category=RuntimeTaskCategory.ACCOUNT_HARD_GATE)
    )

    assert decision.ok is True
    assert decision.model is None
    assert decision.uses_llm is False
    assert decision.estimated_cost_usd == 0.0


def test_factor_review_uses_pro_outside_peak() -> None:
    decision = route_model_for_request(
        route_request(
            task_category=RuntimeTaskCategory.FACTOR_REVIEW,
            as_of_time_bjt="13:00:00",
        )
    )

    assert decision.is_peak is False
    assert decision.model == DEEPSEEK_V4_PRO


def test_factor_review_downgrades_to_flash_during_peak_when_noncritical() -> None:
    decision = route_model_for_request(
        route_request(task_category=RuntimeTaskCategory.FACTOR_REVIEW)
    )

    assert decision.is_peak is True
    assert decision.model == DEEPSEEK_V4_FLASH
    assert "peak_noncritical_pro_downgraded_to_flash" in decision.warnings


def test_risk_review_can_use_pro_during_peak_when_critical_and_in_budget() -> None:
    decision = route_model_for_request(
        route_request(
            role=AgentRole.RISK_AGENT,
            task_category=RuntimeTaskCategory.RISK_REVIEW,
            critical=True,
        )
    )

    assert decision.is_peak is True
    assert decision.model == DEEPSEEK_V4_PRO
    assert decision.ok is True


def test_supervisor_decision_can_use_pro_during_peak_when_critical_and_in_budget() -> None:
    decision = route_model_for_request(
        route_request(
            role=AgentRole.SUPERVISOR_AGENT,
            task_category=RuntimeTaskCategory.SUPERVISOR_DECISION,
            critical=True,
        )
    )

    assert decision.model == DEEPSEEK_V4_PRO
    assert decision.ok is True


def test_deprecated_model_names_are_rejected() -> None:
    decision = route_model_for_request(route_request(requested_model="deepseek-chat"))

    assert decision.ok is False
    assert decision.reason == "deprecated_model_not_allowed"


def test_unsupported_model_names_are_rejected() -> None:
    decision = route_model_for_request(route_request(requested_model="not-a-model"))

    assert decision.ok is False
    assert decision.reason == "unsupported_model_not_allowed"


def test_over_budget_call_is_rejected() -> None:
    decision = route_model_for_request(
        route_request(
            token_estimate=TokenEstimate(input_tokens=1_000_000, output_tokens=1_000_000),
            budget_policy=budget(max_usd_per_run=0.01, max_tokens_per_agent_call=3_000_000),
        )
    )

    assert decision.ok is False
    assert decision.deferred is False
    assert decision.reason == "cost_over_budget_rejected"


def test_over_budget_call_is_deferred_when_allowed() -> None:
    decision = route_model_for_request(
        route_request(
            token_estimate=TokenEstimate(input_tokens=1_000_000, output_tokens=1_000_000),
            budget_policy=budget(
                max_usd_per_run=0.01,
                max_tokens_per_agent_call=3_000_000,
                allow_defer=True,
            ),
        )
    )

    assert decision.ok is False
    assert decision.deferred is True
    assert decision.reason == "cost_over_budget_deferred"


def test_excessive_token_estimate_is_rejected() -> None:
    decision = route_model_for_request(
        route_request(
            token_estimate=TokenEstimate(input_tokens=1000, output_tokens=1000),
            budget_policy=budget(max_tokens_per_agent_call=100),
        )
    )

    assert decision.ok is False
    assert decision.reason == "token_estimate_exceeds_agent_call_limit"


def test_fake_client_refuses_invalid_decisions() -> None:
    decision = route_model_for_request(route_request(requested_model="deepseek-reasoner"))

    with pytest.raises(RuntimeError, match="not ok"):
        FakeAIClient().run(decision)


def test_fake_client_returns_deterministic_response_for_valid_llm_decision() -> None:
    decision = route_model_for_request(route_request())

    response = FakeAIClient().run(decision)

    assert response.provider is RuntimeProvider.DEEPSEEK
    assert response.model == DEEPSEEK_V4_FLASH
    assert response.content == "fake_response:deepseek:deepseek-v4-flash"
    assert response.estimated_cost_usd == decision.estimated_cost_usd


def test_estimate_model_call_cost_uses_cache_hit_and_miss_tokens() -> None:
    cost = estimate_model_call_cost_usd(
        DEEPSEEK_V4_FLASH,
        TokenEstimate(input_tokens=1000, output_tokens=500, cache_hit_input_tokens=250),
        is_peak=False,
        model_prices={
            DEEPSEEK_V4_FLASH: ModelPrice(
                cache_hit_input_per_1m=1.0,
                cache_miss_input_per_1m=2.0,
                output_per_1m=4.0,
                peak_multiplier=2.0,
            )
        },
    )

    assert cost == 0.00375
