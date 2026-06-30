"""Cost-aware runtime routing preflight for future DeepSeek agents."""

from __future__ import annotations

from datetime import datetime, time

from quantpilot_core.deepseek_multi_agent.runtime_contracts import (
    DEEPSEEK_V4_FLASH,
    DEEPSEEK_V4_PRO,
    DEPRECATED_DEEPSEEK_MODELS,
    SUPPORTED_DEEPSEEK_MODELS,
    CostBudgetPolicy,
    FakeAIResponse,
    ModelPrice,
    ModelRouteDecision,
    ModelRouteRequest,
    RuntimeProvider,
    RuntimeTaskCategory,
    TokenEstimate,
)


DEFAULT_MODEL_PRICES = {
    DEEPSEEK_V4_FLASH: ModelPrice(
        cache_hit_input_per_1m=0.0028,
        cache_miss_input_per_1m=0.14,
        output_per_1m=0.28,
        peak_multiplier=2.0,
    ),
    DEEPSEEK_V4_PRO: ModelPrice(
        cache_hit_input_per_1m=0.003625,
        cache_miss_input_per_1m=0.435,
        output_per_1m=0.87,
        peak_multiplier=2.0,
    ),
}

HARD_GATE_TASKS = frozenset(
    {
        RuntimeTaskCategory.ACCOUNT_HARD_GATE,
        RuntimeTaskCategory.EXECUTION_HARD_GATE,
    }
)


def is_peak_bjt(value: str | datetime | time) -> bool:
    """Return true for deterministic BJT peak windows: 09-12 and 14-18."""

    current_time = _parse_time(value)
    return (
        time(9, 0) <= current_time < time(12, 0)
        or time(14, 0) <= current_time < time(18, 0)
    )


def estimate_model_call_cost_usd(
    model: str,
    token_estimate: TokenEstimate,
    is_peak: bool,
    model_prices: dict[str, ModelPrice] | None = None,
) -> float:
    prices = model_prices or DEFAULT_MODEL_PRICES
    price = prices[model]
    cache_hit_tokens = min(
        token_estimate.cache_hit_input_tokens,
        token_estimate.input_tokens,
    )
    cache_miss_tokens = token_estimate.input_tokens - cache_hit_tokens
    raw_cost = (
        cache_hit_tokens * price.cache_hit_input_per_1m
        + cache_miss_tokens * price.cache_miss_input_per_1m
        + token_estimate.output_tokens * price.output_per_1m
    ) / 1_000_000
    multiplier = price.peak_multiplier if is_peak else 1.0
    return round(raw_cost * multiplier, 10)


def route_model_for_request(
    request: ModelRouteRequest,
    model_prices: dict[str, ModelPrice] | None = None,
) -> ModelRouteDecision:
    peak = is_peak_bjt(request.as_of_time_bjt)
    validation_reasons = _validate_request(request)
    if validation_reasons:
        return ModelRouteDecision(
            ok=False,
            provider=request.provider,
            model=None,
            uses_llm=False,
            deferred=False,
            reason=";".join(validation_reasons),
            estimated_cost_usd=0.0,
            is_peak=peak,
            warnings=(),
        )

    if request.task_category in HARD_GATE_TASKS:
        warning = ()
        if request.requested_model is not None:
            warning = ("hard_gate_ignores_requested_model",)
        return ModelRouteDecision(
            ok=True,
            provider=request.provider,
            model=None,
            uses_llm=False,
            deferred=False,
            reason="hard_gate_uses_no_llm",
            estimated_cost_usd=0.0,
            is_peak=peak,
            warnings=warning,
        )

    model, routing_warnings = _select_model(request, peak)
    estimated = estimate_model_call_cost_usd(
        model,
        request.token_estimate,
        is_peak=peak,
        model_prices=model_prices,
    )
    budget_reason = _budget_reason(estimated, request.budget_policy)
    if budget_reason is not None:
        return ModelRouteDecision(
            ok=False,
            provider=request.provider,
            model=model,
            uses_llm=True,
            deferred=request.budget_policy.allow_defer,
            reason=budget_reason,
            estimated_cost_usd=estimated,
            is_peak=peak,
            warnings=routing_warnings,
        )

    return ModelRouteDecision(
        ok=True,
        provider=request.provider,
        model=model,
        uses_llm=True,
        deferred=False,
        reason="ok",
        estimated_cost_usd=estimated,
        is_peak=peak,
        warnings=routing_warnings,
    )


class FakeAIClient:
    """Deterministic fake client for runtime routing tests and dry preflight."""

    def run(self, decision: ModelRouteDecision) -> FakeAIResponse:
        if not decision.ok:
            raise RuntimeError("route decision is not ok")
        if not decision.uses_llm or decision.model is None:
            raise RuntimeError("route decision does not use an llm")
        return FakeAIResponse(
            provider=decision.provider,
            model=decision.model,
            content=f"fake_response:{decision.provider.value}:{decision.model}",
            estimated_cost_usd=decision.estimated_cost_usd,
        )


def _parse_time(value: str | datetime | time) -> time:
    if isinstance(value, datetime):
        return value.time()
    if isinstance(value, time):
        return value
    try:
        return datetime.fromisoformat(value).time()
    except ValueError:
        return time.fromisoformat(value)


def _validate_request(request: ModelRouteRequest) -> tuple[str, ...]:
    reasons: list[str] = []
    if request.requested_model in DEPRECATED_DEEPSEEK_MODELS:
        reasons.append("deprecated_model_not_allowed")
    elif (
        request.requested_model is not None
        and request.requested_model not in SUPPORTED_DEEPSEEK_MODELS
    ):
        reasons.append("unsupported_model_not_allowed")
    if request.token_estimate.input_tokens < 0 or request.token_estimate.output_tokens < 0:
        reasons.append("token_estimate_negative")
    if request.token_estimate.cache_hit_input_tokens < 0:
        reasons.append("cache_hit_tokens_negative")
    total_tokens = request.token_estimate.input_tokens + request.token_estimate.output_tokens
    if total_tokens > request.budget_policy.max_tokens_per_agent_call:
        reasons.append("token_estimate_exceeds_agent_call_limit")
    if request.budget_policy.max_usd_per_run <= 0:
        reasons.append("run_budget_must_be_positive")
    if request.budget_policy.max_usd_per_day <= 0:
        reasons.append("day_budget_must_be_positive")
    return tuple(reasons)


def _select_model(
    request: ModelRouteRequest,
    peak: bool,
) -> tuple[str, tuple[str, ...]]:
    warnings: list[str] = []
    if request.requested_model == DEEPSEEK_V4_FLASH:
        return DEEPSEEK_V4_FLASH, ()
    if request.requested_model == DEEPSEEK_V4_PRO and peak and not request.critical:
        return DEEPSEEK_V4_FLASH, ("peak_noncritical_pro_downgraded_to_flash",)
    if request.requested_model == DEEPSEEK_V4_PRO:
        return DEEPSEEK_V4_PRO, ()

    if request.task_category in {
        RuntimeTaskCategory.LOW_COST_BATCH,
        RuntimeTaskCategory.NEWS_EVENT,
        RuntimeTaskCategory.DATA_QUALITY,
    }:
        return DEEPSEEK_V4_FLASH, ()
    if request.task_category is RuntimeTaskCategory.STAT_SUMMARY:
        return DEEPSEEK_V4_FLASH, ()
    if request.task_category in {
        RuntimeTaskCategory.FACTOR_REVIEW,
        RuntimeTaskCategory.MARKET_REGIME,
    }:
        if peak and not request.critical:
            return DEEPSEEK_V4_FLASH, ("peak_noncritical_pro_downgraded_to_flash",)
        return DEEPSEEK_V4_PRO, ()
    if request.task_category is RuntimeTaskCategory.RISK_REVIEW:
        if request.critical or request.proposed_trade_exists:
            return DEEPSEEK_V4_PRO, ()
        if peak:
            return DEEPSEEK_V4_FLASH, ("peak_noncritical_risk_uses_flash",)
        return DEEPSEEK_V4_PRO, ()
    if request.task_category is RuntimeTaskCategory.SUPERVISOR_DECISION:
        if request.critical:
            return DEEPSEEK_V4_PRO, ()
        if peak:
            return DEEPSEEK_V4_FLASH, ("peak_noncritical_supervisor_uses_flash",)
        return DEEPSEEK_V4_PRO, ()
    return DEEPSEEK_V4_FLASH, tuple(warnings)


def _budget_reason(
    estimated_cost: float,
    budget_policy: CostBudgetPolicy,
) -> str | None:
    if (
        estimated_cost > budget_policy.max_usd_per_run
        or estimated_cost > budget_policy.max_usd_per_day
    ):
        if budget_policy.allow_defer:
            return "cost_over_budget_deferred"
        return "cost_over_budget_rejected"
    return None
