"""Replay adjustment planning for P40 AI shadow decisions."""

from __future__ import annotations

from quantpilot_core.ai_open_source_provider_small_sample_mixed_etf_replay.contracts import (
    AIAdjustedReplayResult,
    AIShadowDecisionSet,
    ReplayAdjustmentPlan,
)
from quantpilot_core.real_provider_mixed_etf_paper_replay import ProviderMixedEtfReplayReport


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
    baseline_replay: ProviderMixedEtfReplayReport,
) -> ReplayAdjustmentPlan:
    """Convert AI shadow recommendations into bounded replay adjustments."""

    safe_recommendations = [
        item for item in decisions.recommendations if item.role not in decisions.meta_blocked_roles
    ]
    forbidden_rejected = _forbidden_adjustments(decisions)
    etf_delta = sum(item.recommended_etf_weight_adjustment for item in safe_recommendations)
    multiplier_raw = _average_multiplier(safe_recommendations)
    multiplier = max(0.50, min(1.50, round(multiplier_raw, 4)))
    require_provider_sample = bool(baseline_replay.provider_replay.validation.blockers)
    require_alpha = baseline_replay.provider_replay.net_pnl_after_cost <= 0
    reduce_turnover = baseline_replay.provider_replay.cost_tax_slippage_total > 10
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
    baseline_replay: ProviderMixedEtfReplayReport,
    decisions: AIShadowDecisionSet,
) -> AIAdjustedReplayResult:
    """Compute deterministic paper metric deltas from the bounded adjustment plan."""

    plan = build_replay_adjustment_plan(decisions, baseline_replay)
    base = baseline_replay.provider_replay
    position_effect = plan.position_size_multiplier - 1.0
    etf_effect = plan.etf_preference_delta
    fill_rate_delta = 0.0 if base.fill_rate >= 1.0 else round(min(0.05, 1.0 - base.fill_rate), 6)
    zero_trade_delta = -1 if base.zero_trade_day_count > 0 and plan.prefer_mixed_stock_etf_universe else 0
    capital_delta = round(max(position_effect, 0.0) * base.capital_used_average, 6)
    cost_drag_delta = -0.0005 if plan.reduce_turnover else 0.0
    net_delta = round((position_effect * max(base.net_pnl_after_cost, 0.0)) + (etf_effect * 10.0), 4)
    turnover_delta = round(position_effect * 0.01, 6)
    improved = net_delta >= 0 and fill_rate_delta >= 0 and not plan.require_provider_sample_improvement
    return AIAdjustedReplayResult(
        baseline_replay=baseline_replay,
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
        mixed_stock_etf_remains_default=baseline_replay.etf_inclusion_remained_useful
        and plan.prefer_mixed_stock_etf_universe,
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
