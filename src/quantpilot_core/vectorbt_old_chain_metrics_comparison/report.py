"""Report helper for old-chain versus vectorbt metrics comparison."""

from __future__ import annotations

from quantpilot_core.vectorbt_old_chain_metrics_comparison.comparison import (
    compare_old_chain_to_vectorbt,
)
from quantpilot_core.vectorbt_old_chain_metrics_comparison.contracts import OldChainReplayMetrics
from quantpilot_core.vectorbt_replay_comparison import VectorbtReplayComparisonResult


def build_old_chain_vectorbt_metrics_report(
    old_metrics: OldChainReplayMetrics,
    vectorbt_result: VectorbtReplayComparisonResult,
) -> str:
    """Build a deterministic advisory comparison report."""

    result = compare_old_chain_to_vectorbt(old_metrics, vectorbt_result)
    old = result.old_metrics
    vectorbt = result.vectorbt_metrics
    old_lines = (
        (
            f"old_source_type: {old.source_type}",
            f"old_source_id: {old.source_id}",
            f"old_fill_rate: {old.fill_rate}",
            f"old_fills: {old.simulated_fill_count_total}",
            f"old_cost_tax_slippage: {old.cost_tax_slippage_total}",
            f"old_net_pnl_after_cost: {old.net_pnl_after_cost}",
            f"old_turnover: {old.turnover_estimate}",
            f"old_drawdown: {old.drawdown_estimate}",
        )
        if old is not None
        else ("old_metrics: none",)
    )
    delta_lines = tuple(
        f"delta:{delta.label}: old={delta.old_value}, vectorbt={delta.vectorbt_value}, delta={delta.delta}"
        for delta in result.deltas
    )
    return "\n".join(
        (
            "# Old Chain vs Vectorbt Metrics Comparison",
            "",
            "This is advisory comparison, not an execution gate.",
            f"status: {result.status}",
            f"reason: {result.reason}",
            *old_lines,
            f"vectorbt_status: {vectorbt.status}",
            f"vectorbt_total_return: {vectorbt.total_return}",
            f"vectorbt_max_drawdown: {vectorbt.max_drawdown}",
            f"vectorbt_trade_count: {vectorbt.trade_count}",
            f"vectorbt_turnover_proxy: {vectorbt.turnover_proxy}",
            f"vectorbt_equity_curve_points: {vectorbt.equity_curve_points}",
            *delta_lines,
            f"advisory_status: {result.replacement_readiness.advisory_status}",
            f"advisory_notes: {', '.join(result.replacement_readiness.notes)}",
        )
    )
