"""Report helpers for advisory cost-after-fill profitability evaluation."""

from __future__ import annotations

from quantpilot_core.cost_after_fill_profitability.contracts import (
    CostAfterFillReport,
    CostAfterFillRequest,
    CostAfterFillResult,
    CostAfterFillStatus,
)
from quantpilot_core.cost_after_fill_profitability.evaluation import (
    evaluate_cost_after_fill,
)


def build_cost_after_fill_report(
    requests: tuple[CostAfterFillRequest, ...],
) -> CostAfterFillReport:
    """Evaluate fills and expose a compact advisory report summary."""

    results = tuple(evaluate_cost_after_fill(request) for request in requests)
    evaluated = tuple(result for result in results if result.status == CostAfterFillStatus.EVALUATED.value)
    rejected = tuple(result for result in results if result.status == CostAfterFillStatus.REJECTED.value)
    warnings = tuple(warning for result in results for warning in result.warnings)
    net_values = tuple(result.net_pnl_after_cost for result in evaluated if result.net_pnl_after_cost is not None)
    net_total = round(sum(net_values), 6) if len(net_values) == len(evaluated) and evaluated else None
    gross_notional_total = round(sum(result.gross_notional for result in evaluated), 6)
    total_cost = round(sum(result.cost_breakdown.total_cost for result in evaluated), 6)
    cost_drag_total = round(sum(result.cost_drag for result in evaluated), 6)
    report = CostAfterFillReport(
        evaluated_count=len(evaluated),
        rejected_count=len(rejected),
        missing_pnl_input_count=sum(1 for result in results if result.missing_pnl_inputs),
        gross_notional_total=gross_notional_total,
        total_cost=total_cost,
        net_pnl_after_cost_total=net_total,
        cost_drag_total=cost_drag_total,
        advisory_warnings=warnings,
        results=results,
        summary={},
    )
    return CostAfterFillReport(
        evaluated_count=report.evaluated_count,
        rejected_count=report.rejected_count,
        missing_pnl_input_count=report.missing_pnl_input_count,
        gross_notional_total=report.gross_notional_total,
        total_cost=report.total_cost,
        net_pnl_after_cost_total=report.net_pnl_after_cost_total,
        cost_drag_total=report.cost_drag_total,
        advisory_warnings=report.advisory_warnings,
        results=report.results,
        summary={"cost_after_fill": cost_after_fill_summary(report.results)},
    )


def cost_after_fill_summary(results: tuple[CostAfterFillResult, ...]) -> dict[str, object]:
    """Return stable report fields for the profit-first advisory path."""

    evaluated = tuple(result for result in results if result.status == CostAfterFillStatus.EVALUATED.value)
    net_values = tuple(result.net_pnl_after_cost for result in evaluated if result.net_pnl_after_cost is not None)
    return {
        "evaluated_count": len(evaluated),
        "rejected_count": sum(1 for result in results if result.status == CostAfterFillStatus.REJECTED.value),
        "missing_pnl_input_count": sum(1 for result in results if result.missing_pnl_inputs),
        "gross_notional_total": round(sum(result.gross_notional for result in evaluated), 6),
        "total_cost": round(sum(result.cost_breakdown.total_cost for result in evaluated), 6),
        "net_pnl_after_cost_total": round(sum(net_values), 6) if len(net_values) == len(evaluated) and evaluated else None,
        "cost_drag_total": round(sum(result.cost_drag for result in evaluated), 6),
        "profitability_gate": False,
    }
