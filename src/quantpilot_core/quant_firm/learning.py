"""Functional deterministic Learning Desk logic for Quant Firm cycles."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Mapping

from quantpilot_core.execution_candidate import ExecutionCandidateReport
from quantpilot_core.execution_optimizer import PortfolioAllocationPlan
from quantpilot_core.quant_firm.contracts import (
    AttributionRecord,
    AttributionReport,
    ExperimentRecord,
    FailureAnalysisReport,
    FailureCause,
    StrategyMutationPlan,
    StrategyMutationRecommendation,
)


def build_attribution_report(
    execution_candidate_report: ExecutionCandidateReport | None,
    portfolio_allocation_plan: PortfolioAllocationPlan | None,
) -> AttributionReport:
    """Attribute portfolio result to EXEC1 candidate and EXEC2 allocation inputs."""

    if not isinstance(execution_candidate_report, ExecutionCandidateReport):
        return AttributionReport(records=(), aggregate_contribution_score=0.0)

    allocations = {
        allocation.symbol: allocation
        for allocation in portfolio_allocation_plan.allocations
    } if isinstance(portfolio_allocation_plan, PortfolioAllocationPlan) else {}
    capital = (
        portfolio_allocation_plan.assumptions.capital
        if isinstance(portfolio_allocation_plan, PortfolioAllocationPlan)
        else 100_000.0
    )

    rows = []
    for candidate in execution_candidate_report.candidates:
        allocation = allocations.get(candidate.symbol)
        allocation_weight = allocation.target_weight if allocation is not None else 0.0
        cost_drag = (
            round(allocation.cost_estimate.total_cost / capital, 8)
            if allocation is not None and capital > 0
            else 0.0
        )
        contribution_score = round(
            (candidate.confidence * 0.25)
            + (candidate.expected_return * 0.35)
            + (candidate.liquidity_score * 0.15)
            + (allocation_weight * 0.20)
            - (candidate.risk_score * 0.20)
            - (cost_drag * 4.0),
            8,
        )
        rows.append(
            AttributionRecord(
                symbol=candidate.symbol,
                rank=0,
                contribution_score=contribution_score,
                candidate_confidence=round(candidate.confidence, 8),
                expected_return=round(candidate.expected_return, 8),
                risk_score=round(candidate.risk_score, 8),
                liquidity_score=round(candidate.liquidity_score, 8),
                cost_drag=cost_drag,
                allocation_weight=round(allocation_weight, 8),
                evidence_refs=(f"evidence://quant-firm/learning/attribution/{candidate.symbol}",),
            )
        )

    ranked = sorted(rows, key=lambda item: (-item.contribution_score, item.symbol))
    records = tuple(
        AttributionRecord(
            symbol=item.symbol,
            rank=index,
            contribution_score=item.contribution_score,
            candidate_confidence=item.candidate_confidence,
            expected_return=item.expected_return,
            risk_score=item.risk_score,
            liquidity_score=item.liquidity_score,
            cost_drag=item.cost_drag,
            allocation_weight=item.allocation_weight,
            evidence_refs=item.evidence_refs,
        )
        for index, item in enumerate(ranked, start=1)
    )
    aggregate = round(sum(item.contribution_score for item in records), 8)
    return AttributionReport(records=records, aggregate_contribution_score=aggregate)


def build_experiment_record(
    *,
    cycle_id: str,
    strategy_id: str,
    execution_candidate_report: ExecutionCandidateReport | None,
    portfolio_allocation_plan: PortfolioAllocationPlan | None,
    vectorbt_replay_result: Any | None,
    context: Mapping[str, Any],
) -> ExperimentRecord:
    """Create a deterministic in-memory experiment record."""

    parameter_set = {
        "top_n": len(execution_candidate_report.candidates)
        if isinstance(execution_candidate_report, ExecutionCandidateReport)
        else _param(context, "top_n", 0),
        "holding_period": _param(context, "holding_period", 5),
        "risk_penalty": _param(context, "risk_penalty", 1.0),
        "turnover_penalty": (
            portfolio_allocation_plan.assumptions.turnover_penalty_rate
            if isinstance(portfolio_allocation_plan, PortfolioAllocationPlan)
            else _param(context, "turnover_penalty", 0.0005)
        ),
        "gross_exposure": (
            portfolio_allocation_plan.gross_exposure
            if isinstance(portfolio_allocation_plan, PortfolioAllocationPlan)
            else 0.0
        ),
    }
    metrics = _performance_metrics(vectorbt_replay_result)
    metrics["candidate_count"] = parameter_set["top_n"]
    metrics["gross_exposure"] = parameter_set["gross_exposure"]
    return ExperimentRecord(
        experiment_id=f"qf-{strategy_id}-{cycle_id}",
        strategy_id=strategy_id,
        parameter_set=parameter_set,
        performance_metrics=metrics,
        run_label=f"{strategy_id}:{cycle_id}:learning-desk",
        evidence_refs=("evidence://quant-firm/learning/experiment",),
    )


def build_failure_analysis_report(
    execution_candidate_report: ExecutionCandidateReport | None,
    portfolio_allocation_plan: PortfolioAllocationPlan | None,
    vectorbt_replay_result: Any | None,
    market_regime: Any | None = None,
    information_signals: Any | None = None,
) -> FailureAnalysisReport:
    """Classify explainable failure causes with deterministic thresholds."""

    causes: list[FailureCause] = []
    metrics = _performance_metrics(vectorbt_replay_result)
    candidates = execution_candidate_report.candidates if isinstance(execution_candidate_report, ExecutionCandidateReport) else ()
    allocations = portfolio_allocation_plan.allocations if isinstance(portfolio_allocation_plan, PortfolioAllocationPlan) else ()
    capital = portfolio_allocation_plan.assumptions.capital if isinstance(portfolio_allocation_plan, PortfolioAllocationPlan) else 100_000.0
    cost_drag = (
        round(portfolio_allocation_plan.total_estimated_cost / capital, 8)
        if isinstance(portfolio_allocation_plan, PortfolioAllocationPlan) and capital > 0
        else _numeric(metrics.get("cost_drag"), 0.0)
    )
    turnover = _numeric(metrics.get("turnover_proxy", metrics.get("turnover")), 0.0)
    max_drawdown = abs(_numeric(metrics.get("max_drawdown"), 0.0))
    volatility = _numeric(metrics.get("volatility", metrics.get("annualized_volatility")), 0.0)
    avg_expected = _mean(candidate.expected_return for candidate in candidates)
    min_liquidity = min((candidate.liquidity_score for candidate in candidates), default=1.0)
    max_weight = max((allocation.target_weight for allocation in allocations), default=0.0)

    if cost_drag > 0.005:
        causes.append(_cause("high_cost_drag", cost_drag, f"Cost drag {cost_drag:.4f} exceeds 0.005."))
    if turnover > 0.75:
        causes.append(_cause("high_turnover", turnover, f"Turnover {turnover:.4f} exceeds 0.75."))
    if candidates and avg_expected < 0.03:
        causes.append(_cause("weak_expected_return", 0.03 - avg_expected, f"Average expected return {avg_expected:.4f} is below 0.03."))
    if max_weight > 0.60:
        causes.append(_cause("concentration_risk", max_weight, f"Largest allocation weight {max_weight:.4f} exceeds 0.60."))
    if min_liquidity < 0.40:
        causes.append(_cause("low_liquidity", 1.0 - min_liquidity, f"Minimum liquidity score {min_liquidity:.4f} is below 0.40."))
    if max_drawdown > 0.08:
        causes.append(_cause("drawdown_problem", max_drawdown, f"Absolute max drawdown {max_drawdown:.4f} exceeds 0.08."))
    if volatility > 0.20:
        causes.append(_cause("volatility_problem", volatility, f"Volatility {volatility:.4f} exceeds 0.20."))
    if _regime_mismatch(market_regime, information_signals, portfolio_allocation_plan):
        causes.append(_cause("regime_mismatch", 0.75, "Risk-on allocation conflicts with supplied risk-off regime evidence."))

    ordered = tuple(sorted(causes, key=lambda item: (-item.severity, item.cause)))
    return FailureAnalysisReport(
        causes=ordered,
        primary_cause=ordered[0].cause if ordered else None,
        no_failure_detected=not ordered,
    )


def build_strategy_mutation_plan(
    *,
    experiment: ExperimentRecord,
    failure_analysis: FailureAnalysisReport,
    attribution: AttributionReport,
) -> StrategyMutationPlan:
    """Generate next-iteration deterministic parameter recommendations."""

    causes = {cause.cause for cause in failure_analysis.causes}
    params = experiment.parameter_set
    top_n = int(_numeric(params.get("top_n"), 0))
    holding_period = int(_numeric(params.get("holding_period"), 5))
    risk_penalty = float(_numeric(params.get("risk_penalty"), 1.0))
    turnover_penalty = float(_numeric(params.get("turnover_penalty"), 0.0005))
    recommendations: list[StrategyMutationRecommendation] = []

    if "concentration_risk" in causes or "low_liquidity" in causes:
        recommendations.append(_mutation("top_n", top_n, max(top_n + 1, 2), "Broaden candidates to reduce concentration or liquidity dependence."))
    elif "weak_expected_return" in causes and top_n > 1:
        recommendations.append(_mutation("top_n", top_n, max(1, top_n - 1), "Tighten candidate selection when expected return is weak."))

    if "high_turnover" in causes or "high_cost_drag" in causes:
        recommendations.append(_mutation("holding_period", holding_period, holding_period + 2, "Lengthen holding period to reduce turnover and cost drag."))

    if {"drawdown_problem", "volatility_problem", "regime_mismatch", "concentration_risk"} & causes:
        recommendations.append(_mutation("risk_penalty", risk_penalty, round(risk_penalty + 0.25, 6), "Increase risk penalty for adverse risk diagnostics."))

    if {"high_turnover", "high_cost_drag"} & causes:
        recommendations.append(_mutation("turnover_penalty", turnover_penalty, round(turnover_penalty * 1.5, 8), "Increase turnover penalty after cost or turnover failure."))

    low_liquidity_records = tuple(record for record in attribution.records if record.liquidity_score < 0.40 and record.allocation_weight > 0)
    if "low_liquidity" in causes or low_liquidity_records:
        recommendations.append(_mutation("low_liquidity_allocation_multiplier", 1.0, 0.5, "Reduce allocation to low-liquidity symbols."))

    if "concentration_risk" in causes:
        recommendations.append(_mutation("max_symbol_weight", 0.60, 0.45, "Reduce single-name concentration."))

    if not recommendations:
        recommendations.append(_mutation("shadow_variant", "baseline", "keep_parameters", "No failure threshold was breached."))

    return StrategyMutationPlan(
        recommendations=tuple(recommendations),
        reduce_low_liquidity_allocation=("low_liquidity" in causes or bool(low_liquidity_records)),
        reduce_concentration=("concentration_risk" in causes),
    )


def _performance_metrics(vectorbt_replay_result: Any | None) -> dict[str, float | int | str | None]:
    metrics = _to_mapping(vectorbt_replay_result)
    normalized: dict[str, float | int | str | None] = {}
    for key in (
        "total_return",
        "total_profit",
        "max_drawdown",
        "sharpe_ratio",
        "trade_count",
        "turnover_proxy",
        "turnover",
        "volatility",
        "annualized_volatility",
        "cost_drag",
        "status",
        "engine",
    ):
        if key in metrics:
            normalized[key] = metrics[key]
    return normalized


def _to_mapping(value: Any | None) -> Mapping[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return value
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    return {
        key: getattr(value, key)
        for key in (
            "total_return",
            "total_profit",
            "max_drawdown",
            "sharpe_ratio",
            "trade_count",
            "turnover_proxy",
            "turnover",
            "volatility",
            "annualized_volatility",
            "cost_drag",
            "status",
            "engine",
        )
        if hasattr(value, key)
    }


def _param(context: Mapping[str, Any], name: str, default: Any) -> Any:
    params = context.get("parameter_set")
    if isinstance(params, Mapping) and name in params:
        return params[name]
    return context.get(name, default)


def _numeric(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _mean(values: Any) -> float:
    items = tuple(values)
    if not items:
        return 0.0
    return round(sum(items) / len(items), 8)


def _cause(cause: str, severity: float, explanation: str) -> FailureCause:
    return FailureCause(
        cause=cause,
        severity=round(max(0.0, min(1.0, severity)), 8),
        explanation=explanation,
        evidence_refs=(f"evidence://quant-firm/learning/failure/{cause}",),
    )


def _mutation(parameter: str, current_value: Any, recommended_value: Any, reason: str) -> StrategyMutationRecommendation:
    return StrategyMutationRecommendation(
        parameter=parameter,
        current_value=current_value,
        recommended_value=recommended_value,
        reason=reason,
        evidence_refs=(f"evidence://quant-firm/learning/mutation/{parameter}",),
    )


def _regime_mismatch(
    market_regime: Any | None,
    information_signals: Any | None,
    portfolio_allocation_plan: PortfolioAllocationPlan | None,
) -> bool:
    if not isinstance(portfolio_allocation_plan, PortfolioAllocationPlan):
        return False
    regime_text = " ".join(str(item).lower() for item in (market_regime, information_signals) if item is not None)
    risk_off = any(marker in regime_text for marker in ("bear", "risk_off", "defensive", "liquidity_stress"))
    return risk_off and portfolio_allocation_plan.gross_exposure > 0.50
