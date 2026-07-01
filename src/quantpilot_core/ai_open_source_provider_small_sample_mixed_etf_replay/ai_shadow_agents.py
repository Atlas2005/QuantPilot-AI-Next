"""Deterministic AI shadow agents for P40."""

from __future__ import annotations

from quantpilot_core.ai_open_source_provider_small_sample_mixed_etf_replay.contracts import (
    AIShadowAgentRecommendation,
    AIShadowAgentRole,
    AIShadowDecisionSet,
    ApprovedProviderSampleValidationResult,
)
from quantpilot_core.real_provider_mixed_etf_paper_replay import ProviderMixedEtfReplayReport


REQUIRED_ROLES = tuple(role.value for role in AIShadowAgentRole)
UNSAFE_MARKERS = {
    "unsupported_profitability_claim": ("profitability_claim", "guaranteed_profit"),
    "live_trading_suggestion": ("live_trade", "broker_connect", "real_order"),
    "cost_blind_suggestion": ("ignore_cost", "cost_blind"),
    "sample_quality_ignored": ("ignore_sample_quality",),
    "market_rules_bypass": ("bypass_market_rules", "bypass_a_share_rules"),
}


def generate_ai_shadow_decision_set(
    validation: ApprovedProviderSampleValidationResult,
    baseline_replay: ProviderMixedEtfReplayReport,
) -> AIShadowDecisionSet:
    """Generate deterministic local shadow-agent outputs without runtime calls."""

    recommendations = (
        _recommendation(
            AIShadowAgentRole.MARKET_DATA_QUALITY,
            "keep_provider_sample_if_quality_flags_clean",
            0.0,
            1.0,
            "prefer_rows_with_complete_ohlcv",
            "cost_model_unchanged",
            "sample_blockers_must_stop_replay" if validation.blockers else "no_sample_blockers",
            "use_approved_local_export",
            0.86,
            validation.quality_flags,
        ),
        _recommendation(
            AIShadowAgentRole.ALPHA_RESEARCH,
            "prefer_mixed_stock_etf_universe",
            0.05,
            1.05,
            "increase_etf_alpha_feature_probe",
            "monitor_cost_after_fill",
            "do_not_claim_real_profitability",
            "run_shadow_adjusted_replay",
            0.74,
            ("evidence://p40/ai/alpha",),
        ),
        _recommendation(
            AIShadowAgentRole.ETF_SELECTION,
            "prefer_liquid_equity_etf",
            0.10,
            1.0,
            "rank_etf_by_fillability_and_cost",
            "etf_cost_drag_lower_than_stock_stamp_model",
            "keep_etf_category_explicit",
            "increase_etf_preference",
            0.80,
            ("evidence://p40/ai/etf",),
        ),
        _recommendation(
            AIShadowAgentRole.SIZING_CAPITAL,
            "keep_mixed_universe",
            0.05,
            1.10,
            "avoid_odd_lot_zero_trade",
            "bounded_size_change_only",
            "respect_available_cash",
            "increase_position_size_within_bounds",
            0.78,
            ("evidence://p40/ai/sizing",),
        ),
        _recommendation(
            AIShadowAgentRole.COST_EXECUTION,
            "keep_mixed_universe",
            0.0,
            0.95 if baseline_replay.provider_replay.cost_tax_slippage_total > 10 else 1.0,
            "alpha_must_clear_cost_after_fill",
            "reduce_turnover_if_cost_drag_high",
            "cost_review_required",
            "keep_cost_model_in_loop",
            0.82,
            ("evidence://p40/ai/cost",),
        ),
        _recommendation(
            AIShadowAgentRole.PORTFOLIO_MANAGER,
            "prefer_mixed_stock_etf_universe",
            0.05,
            1.05,
            "balance_stock_and_etf_exposure",
            "track_turnover_delta",
            "no_account_runtime_or_broker_path",
            "keep_mixed_default_if_replay_positive",
            0.76,
            ("evidence://p40/ai/portfolio",),
        ),
    )
    return meta_review_shadow_recommendations(recommendations)


def meta_review_shadow_recommendations(
    recommendations: tuple[AIShadowAgentRecommendation, ...],
) -> AIShadowDecisionSet:
    """Apply deterministic meta-review to unsafe or unsupported recommendations."""

    reviewed: list[AIShadowAgentRecommendation] = []
    blocked_roles: list[str] = []
    downgraded_roles: list[str] = []
    unsafe_reasons: list[str] = []
    for recommendation in recommendations:
        reasons = _unsafe_reasons(recommendation)
        if reasons:
            unsafe_reasons.extend(reasons)
            blocked_roles.append(recommendation.role)
            reviewed.append(
                AIShadowAgentRecommendation(
                    role=recommendation.role,
                    recommended_universe_adjustment=recommendation.recommended_universe_adjustment,
                    recommended_etf_weight_adjustment=0.0,
                    recommended_position_size_adjustment=1.0,
                    recommended_alpha_adjustment=recommendation.recommended_alpha_adjustment,
                    cost_warning=recommendation.cost_warning,
                    risk_warning="meta_review_blocked_unsafe_recommendation",
                    recommended_next_action="blocked_by_meta_review",
                    confidence=min(recommendation.confidence, 0.35),
                    evidence_refs=recommendation.evidence_refs,
                    blocked_by=tuple(sorted(set(reasons))),
                    agent_notes=recommendation.agent_notes,
                )
            )
        elif recommendation.confidence < 0.50:
            downgraded_roles.append(recommendation.role)
            reviewed.append(recommendation)
        else:
            reviewed.append(recommendation)

    meta = AIShadowAgentRecommendation(
        role=AIShadowAgentRole.META_REVIEWER.value,
        recommended_universe_adjustment="allow_safe_shadow_adjustments_only",
        recommended_etf_weight_adjustment=0.0,
        recommended_position_size_adjustment=1.0,
        recommended_alpha_adjustment="reject_unsupported_profitability_claims",
        cost_warning="cost_after_fill_must_remain_in_loop",
        risk_warning="live_trading_and_broker_paths_blocked",
        recommended_next_action="apply_bounded_shadow_plan",
        confidence=0.90,
        evidence_refs=("evidence://p40/ai/meta-review",),
        blocked_by=tuple(sorted(set(unsafe_reasons))),
        agent_notes=("deterministic_shadow_mode", "no_runtime_model_call"),
    )
    return AIShadowDecisionSet(
        recommendations=tuple([*reviewed, meta]),
        meta_blocked_roles=tuple(sorted(set(blocked_roles))),
        meta_downgraded_roles=tuple(sorted(set(downgraded_roles))),
        unsafe_reasons=tuple(sorted(set(unsafe_reasons))),
        deterministic_shadow_mode=True,
    )


def _recommendation(
    role: AIShadowAgentRole,
    universe: str,
    etf_delta: float,
    size_multiplier: float,
    alpha: str,
    cost: str,
    risk: str,
    action: str,
    confidence: float,
    evidence_refs: tuple[str, ...],
) -> AIShadowAgentRecommendation:
    return AIShadowAgentRecommendation(
        role=role.value,
        recommended_universe_adjustment=universe,
        recommended_etf_weight_adjustment=etf_delta,
        recommended_position_size_adjustment=size_multiplier,
        recommended_alpha_adjustment=alpha,
        cost_warning=cost,
        risk_warning=risk,
        recommended_next_action=action,
        confidence=confidence,
        evidence_refs=evidence_refs,
        blocked_by=(),
        agent_notes=("shadow_agent_output_schema_v1",),
    )


def _unsafe_reasons(recommendation: AIShadowAgentRecommendation) -> tuple[str, ...]:
    text = " ".join(
        (
            recommendation.recommended_universe_adjustment,
            recommendation.recommended_alpha_adjustment,
            recommendation.cost_warning,
            recommendation.risk_warning,
            recommendation.recommended_next_action,
            " ".join(recommendation.agent_notes),
        )
    )
    reasons = [
        reason
        for reason, markers in UNSAFE_MARKERS.items()
        if any(marker in text for marker in markers)
    ]
    return tuple(reasons)
