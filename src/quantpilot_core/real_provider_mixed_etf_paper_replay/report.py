"""Report builder for the legacy P39 provider replay path."""

from __future__ import annotations

from quantpilot_core.mixed_stock_etf_daily_paper_evaluation import (
    build_mixed_stock_etf_comparison_report,
)
from quantpilot_core.real_provider_mixed_etf_paper_replay.comparison import (
    compare_provider_replay_to_p38_baseline,
    evaluate_provider_capital_path_suitability,
)
from quantpilot_core.real_provider_mixed_etf_paper_replay.contracts import (
    ProviderMixedEtfReplayReport,
    RealProviderReplayInput,
)
from quantpilot_core.real_provider_mixed_etf_paper_replay.replay import (
    replay_provider_mixed_etf_sample,
)


def build_provider_mixed_etf_replay_report(
    replay_input: RealProviderReplayInput,
    *,
    safety_barrier_percent: float = 140.0,
    use_legacy_engine: bool | None = None,
) -> ProviderMixedEtfReplayReport:
    """Build the legacy P39 provider-like replay report for reference compatibility.

    Prefer `quantpilot_core.provider_vectorbt_replay` for provider replay.
    """

    provider_replay = replay_provider_mixed_etf_sample(
        replay_input,
        use_legacy_engine=use_legacy_engine,
    )
    baseline = build_mixed_stock_etf_comparison_report()
    capital_path = evaluate_provider_capital_path_suitability(provider_replay)
    comparison_notes = compare_provider_replay_to_p38_baseline(provider_replay)
    includes_both = (
        provider_replay.stock_candidate_count > 0 and provider_replay.etf_candidate_count > 0
    )
    data_blocked = bool(provider_replay.validation.blockers)
    return ProviderMixedEtfReplayReport(
        provider_replay=provider_replay,
        p38_baseline=baseline,
        capital_path_suitability=capital_path,
        provider_sample_includes_stock_and_etf=includes_both,
        replay_produced_simulated_fills=provider_replay.simulated_fill_count_total > 0,
        fill_rate_positive=provider_replay.fill_rate > 0,
        zero_trade_days_explained=provider_replay.zero_trade_day_count == 0
        or bool(provider_replay.zero_trade_reason_distribution),
        pnl_sign=_pnl_sign(provider_replay.net_pnl_after_cost),
        data_quality_blocked_replay=data_blocked,
        etf_inclusion_remained_useful=includes_both
        and provider_replay.fill_rate > 0
        and provider_replay.net_pnl_after_cost > 0
        and not data_blocked,
        safety_barrier_percent=min(round(safety_barrier_percent, 4), 140.0),
        next_improvement_target=_next_target(provider_replay, data_blocked),
        comparison_notes=comparison_notes,
        evidence_refs=tuple(sorted(set(replay_input.evidence_refs))),
    )


def _pnl_sign(value: float) -> str:
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "zero"


def _next_target(provider_replay, data_blocked: bool) -> str:
    if data_blocked:
        return "provider sample quality"
    if provider_replay.fill_rate == 0:
        return "sizing"
    if provider_replay.net_pnl_after_cost <= 0:
        return "alpha quality"
    if provider_replay.cost_tax_slippage_total > provider_replay.net_pnl_after_cost:
        return "cost model realism"
    if provider_replay.etf_candidate_count == 0:
        return "ETF selection"
    return "daily loop realism"
