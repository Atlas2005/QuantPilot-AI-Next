"""Deterministic alpha, sizing, ETF universe tuning decisions."""

from __future__ import annotations

from quantpilot_core.alpha_sizing_etf_universe_tuning_loop.contracts import (
    AlphaSignalQuality,
    InstrumentType,
    SizingCandidate,
    TuningDecision,
)


def tune_alpha_sizing_candidates(
    sizing_candidates: tuple[SizingCandidate, ...],
    alpha_quality_by_symbol: dict[str, AlphaSignalQuality],
) -> tuple[TuningDecision, ...]:
    """Produce deterministic candidate decisions for the next paper loop."""

    decisions = [
        _decision_for_candidate(candidate, alpha_quality_by_symbol.get(candidate.symbol))
        for candidate in sizing_candidates
    ]
    return tuple(sorted(decisions, key=lambda item: (item.instrument_type, item.symbol)))


def _decision_for_candidate(
    candidate: SizingCandidate,
    quality: AlphaSignalQuality | None,
) -> TuningDecision:
    alpha_score = _alpha_score(quality)
    sizing_score = _sizing_score(candidate)
    tradability_score = candidate.tradability_score
    cost_score = _cost_score(candidate)
    reasons = _reasons(candidate, alpha_score, sizing_score, cost_score)
    action = _recommended_action(candidate, alpha_score, sizing_score, tradability_score, cost_score)
    return TuningDecision(
        symbol=candidate.symbol,
        instrument_type=candidate.instrument_type,
        accepted=action not in {"reject_candidate", "improve_alpha"},
        alpha_quality_score=alpha_score,
        sizing_score=sizing_score,
        tradability_score=tradability_score,
        cost_after_fill_score=cost_score,
        recommended_action=action,
        reasons=reasons,
    )


def _alpha_score(quality: AlphaSignalQuality | None) -> float:
    if quality is None:
        return 0.0
    score = (
        quality.alpha_score * 0.45
        + quality.hit_rate * 0.20
        + max(0.0, quality.rank_ic) * 0.15
        + quality.confidence * 0.20
    )
    return round(max(0.0, min(score, 1.0)), 4)


def _sizing_score(candidate: SizingCandidate) -> float:
    if not candidate.zero_trade_risk_reduced:
        return 0.2
    if candidate.capital_usage_ratio < 0.005:
        return 0.55
    if candidate.capital_usage_ratio > 0.25:
        return 0.5
    return 0.86


def _cost_score(candidate: SizingCandidate) -> float:
    if candidate.estimated_cost_drag <= 0.0005:
        return 0.92
    if candidate.estimated_cost_drag <= 0.0015:
        return 0.78
    if candidate.estimated_cost_drag <= 0.003:
        return 0.55
    return 0.25


def _recommended_action(
    candidate: SizingCandidate,
    alpha_score: float,
    sizing_score: float,
    tradability_score: float,
    cost_score: float,
) -> str:
    if alpha_score < 0.35:
        return "improve_alpha"
    if cost_score < 0.50:
        return "reduce_cost_drag"
    if sizing_score < 0.60 and candidate.capital_usage_ratio < 0.005:
        return "increase_position_size"
    if candidate.capital_usage_ratio > 0.25:
        return "reduce_position_size"
    if candidate.instrument_type == InstrumentType.ETF.value and tradability_score >= 0.85:
        return "prefer_etf_for_small_capital"
    if tradability_score >= 0.65 and sizing_score >= 0.60:
        return "keep_candidate"
    return "reject_candidate"


def _reasons(
    candidate: SizingCandidate,
    alpha_score: float,
    sizing_score: float,
    cost_score: float,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if alpha_score < 0.35:
        reasons.append("alpha_quality_low")
    if sizing_score < 0.60:
        reasons.append("sizing_needs_adjustment")
    if cost_score < 0.50:
        reasons.append("cost_drag_high")
    if candidate.instrument_type == InstrumentType.ETF.value:
        reasons.append("etf_diversification_candidate")
    if candidate.zero_trade_risk_reduced:
        reasons.append("min_trade_unit_satisfied")
    return tuple(reasons)
