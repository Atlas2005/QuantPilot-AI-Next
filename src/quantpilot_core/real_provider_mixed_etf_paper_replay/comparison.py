"""Compare P39 provider-like replay with the P38 mixed baseline."""

from __future__ import annotations

from quantpilot_core.mixed_stock_etf_daily_paper_evaluation import (
    CapitalPathSuitability,
    build_mixed_stock_etf_comparison_report,
)
from quantpilot_core.real_provider_mixed_etf_paper_replay.contracts import (
    ProviderReplayResult,
)


CAPITAL_STAGES = (1_000, 10_000, 100_000)


def compare_provider_replay_to_p38_baseline(
    provider_replay: ProviderReplayResult,
) -> tuple[str, ...]:
    """Return concise notes comparing provider replay to the P38 mixed baseline."""

    baseline = build_mixed_stock_etf_comparison_report()
    mixed_metrics = baseline.mixed_result.metrics
    notes = [
        _delta_note("fill_rate_delta_vs_p38", provider_replay.fill_rate - mixed_metrics.fill_rate, 6),
        _delta_note(
            "zero_trade_day_delta_vs_p38",
            provider_replay.zero_trade_day_count - mixed_metrics.zero_trade_day_count,
            0,
        ),
        _delta_note(
            "cost_drag_delta_vs_p38",
            _provider_cost_drag(provider_replay) - _baseline_cost_drag(),
            6,
        ),
        _delta_note(
            "capital_usage_delta_vs_p38",
            provider_replay.capital_used_average - mixed_metrics.capital_used_average,
            6,
        ),
        _delta_note(
            "net_pnl_after_cost_delta_vs_p38",
            provider_replay.net_pnl_after_cost - mixed_metrics.net_pnl_after_cost,
            4,
        ),
    ]
    notes.append(
        "data_quality_blockers_present"
        if provider_replay.validation.blockers
        else "data_quality_no_blockers"
    )
    return tuple(notes)


def evaluate_provider_capital_path_suitability(
    provider_replay: ProviderReplayResult,
) -> tuple[CapitalPathSuitability, ...]:
    """Evaluate provider replay suitability for 1k/10k/100k CNY stages."""

    return tuple(_stage_suitability(stage, provider_replay) for stage in CAPITAL_STAGES)


def _stage_suitability(stage: int, provider_replay: ProviderReplayResult) -> CapitalPathSuitability:
    has_fills = provider_replay.simulated_fill_count_total > 0
    etf_unit_notional = 200.0
    mixed_viable = stage >= etf_unit_notional and has_fills and not provider_replay.validation.blockers
    stock_viable = stage >= 1_000 and has_fills
    etf_helps = mixed_viable and provider_replay.etf_candidate_count > 0 and provider_replay.fill_rate > 0
    return CapitalPathSuitability(
        stage_capital_cny=stage,
        etf_inclusion_helps=etf_helps,
        stock_only_viable=stock_viable,
        mixed_universe_viable=mixed_viable,
        recommend_mixed_default=etf_helps and provider_replay.net_pnl_after_cost > 0,
        reason=(
            f"provider_mixed_etf_replay_supports_{stage}_cny_stage"
            if etf_helps
            else f"provider_replay_not_sufficient_for_{stage}_cny_stage"
        ),
    )


def _provider_cost_drag(provider_replay: ProviderReplayResult) -> float:
    if provider_replay.capital_used_average <= 0:
        return 1.0
    approximate_trade_value = provider_replay.capital_used_average * 100_000
    return round(provider_replay.cost_tax_slippage_total / approximate_trade_value, 6)


def _baseline_cost_drag() -> float:
    baseline = build_mixed_stock_etf_comparison_report()
    gross_trade_value = sum(
        fill.gross_notional
        for day in baseline.mixed_result.daily_report.day_results
        for fill in day.fill_report.fills
    )
    return round(baseline.mixed_result.metrics.cost_tax_slippage_total / gross_trade_value, 6)


def _delta_note(label: str, value: float, decimals: int) -> str:
    if decimals == 0:
        rendered = str(int(value))
    else:
        rendered = str(round(value, decimals))
    return f"{label}:{rendered}"
