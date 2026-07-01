"""Replay adjustment planning for P40 AI shadow decisions."""

from __future__ import annotations

from quantpilot_core.ai_open_source_provider_small_sample_mixed_etf_replay.contracts import (
    AIAdjustedReplayResult,
    AIShadowDecisionSet,
    ReplayAdjustmentPlan,
)
from quantpilot_core.provider_vectorbt_replay import ProviderVectorbtReplayResult


FORBIDDEN_ACTION_MARKERS = {
    "live_trade",
    "broker_connect",
    "account_read",
    "credential",
    "bypass_market_rules",
    "ignore_cost",
    "bypass_sample_validation",
    "guaranteed_profit",
}


def build_replay_adjustment_plan(
    decisions: AIShadowDecisionSet,
    provider_vectorbt_replay: ProviderVectorbtReplayResult,
) -> ReplayAdjustmentPlan:
    """Convert AI shadow recommendations into bounded replay adjustments."""

    safe_recommendations = [
        item for item in decisions.recommendations if item.role not in decisions.meta_blocked_roles
    ]
    forbidden_rejected = _forbidden_adjustments(decisions)
    etf_delta = sum(item.recommended_etf_weight_adjustment for item in safe_recommendations)
    multiplier_raw = _average_multiplier(safe_recommendations)
    multiplier = max(0.50, min(1.50, round(multiplier_raw, 4)))
    require_provider_sample = bool(provider_vectorbt_replay.provider_validation.blockers)
    require_alpha = (provider_vectorbt_replay.total_return or 0.0) <= 0
    reduce_turnover = (provider_vectorbt_replay.turnover_proxy or 0.0) > 0.75
    return ReplayAdjustmentPlan(
        prefer_mixed_stock_etf_universe=True,
        etf_preference_delta=round(max(-0.25, min(0.25, etf_delta)), 4),
        position_size_multiplier=multiplier,
        reduce_turnover=reduce_turnover,
        require_alpha_improvement=require_alpha,
        require_provider_sample_improvement=require_provider_sample,
        forbidden_adjustments_rejected=forbidden_rejected,
        evidence_refs=("evidence://p40/replay-adjustment-plan",),
    )


def build_ai_adjusted_replay_result(
    provider_vectorbt_replay: ProviderVectorbtReplayResult,
    decisions: AIShadowDecisionSet,
) -> AIAdjustedReplayResult:
    """Compute deterministic paper metric deltas from the bounded adjustment plan."""

    plan = build_replay_adjustment_plan(decisions, provider_vectorbt_replay)
    position_effect = plan.position_size_multiplier - 1.0
    etf_effect = plan.etf_preference_delta
    trade_count = provider_vectorbt_replay.trade_count or 0
    fill_rate_delta = 0.0 if trade_count > 0 else 0.05
    zero_trade_delta = 0 if trade_count > 0 else -1
    capital_delta = round(max(position_effect, 0.0) * (provider_vectorbt_replay.turnover_proxy or 0.0), 6)
    cost_drag_delta = -0.0005 if plan.reduce_turnover else 0.0
    net_delta = round((position_effect * max(provider_vectorbt_replay.total_return or 0.0, 0.0)) + (etf_effect * 10.0), 4)
    turnover_delta = round(position_effect * 0.01, 6)
    improved = net_delta >= 0 and fill_rate_delta >= 0 and not plan.require_provider_sample_improvement
    return AIAdjustedReplayResult(
        provider_vectorbt_replay=provider_vectorbt_replay,
        adjustment_plan=plan,
        fill_rate_delta=fill_rate_delta,
        zero_trade_day_delta=zero_trade_delta,
        capital_usage_delta=capital_delta,
        cost_drag_delta=cost_drag_delta,
        net_pnl_after_cost_delta=net_delta,
        turnover_delta=turnover_delta,
        etf_weight_change=plan.etf_preference_delta,
        ai_adjustment_improved_paper_metrics=improved,
        meta_review_blocked_or_downgraded=bool(
            decisions.meta_blocked_roles or decisions.meta_downgraded_roles
        ),
        mixed_stock_etf_remains_default=trade_count > 0 and plan.prefer_mixed_stock_etf_universe,
    )


def _average_multiplier(recommendations) -> float:
    values = [
        item.recommended_position_size_adjustment
        for item in recommendations
        if item.role != "meta_reviewer"
    ]
    if not values:
        return 1.0
    return sum(values) / len(values)


def _forbidden_adjustments(decisions: AIShadowDecisionSet) -> tuple[str, ...]:
    rejected = set(decisions.unsafe_reasons)
    for item in decisions.recommendations:
        text = " ".join(
            (
                item.recommended_next_action,
                item.recommended_universe_adjustment,
                item.recommended_alpha_adjustment,
                item.cost_warning,
                item.risk_warning,
                " ".join(item.agent_notes),
            )
        )
        rejected.update(marker for marker in FORBIDDEN_ACTION_MARKERS if marker in text)
    return tuple(sorted(rejected))
