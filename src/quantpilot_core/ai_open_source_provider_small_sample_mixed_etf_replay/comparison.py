"""Comparison and open-source handoff helpers for P40."""

from __future__ import annotations

from quantpilot_core.ai_open_source_provider_small_sample_mixed_etf_replay.contracts import (
    AIAdjustedReplayResult,
    ApprovedProviderSampleValidationResult,
    OpenSourceBacktestHandoff,
    OpenSourceProviderExportSpec,
)


def build_open_source_backtest_handoffs(
    spec: OpenSourceProviderExportSpec,
    validation: ApprovedProviderSampleValidationResult,
) -> tuple[OpenSourceBacktestHandoff, OpenSourceBacktestHandoff]:
    """Create metadata handoffs for future offline Qlib and RQAlpha work."""

    stock_symbols = tuple(
        sorted({item.symbol for item in validation.normalized_records if item.instrument_type == "stock"})
    )
    etf_symbols = tuple(
        sorted({item.symbol for item in validation.normalized_records if item.instrument_type == "etf"})
    )
    coverage = tuple(sorted({*stock_symbols, *etf_symbols}))
    common = dict(
        local_sample_identifier=spec.source_uri,
        provider_name=spec.provider_name,
        instrument_coverage=coverage,
        stock_count=len(stock_symbols),
        etf_count=len(etf_symbols),
        field_mapping=dict(sorted(spec.provider_schema_mapping.items())),
        calendar_assumptions=(
            "local_export_trade_dates_define_calendar",
            f"window:{spec.evaluation_start}:{spec.evaluation_end}",
        ),
        cost_model_assumptions=(
            "paper_replay_commission_slippage_only",
            "etf_stamp_duty_zero_in_fixture_model",
        ),
        benchmark_candidate="000300.SH",
        alpha_feature_candidates=("close_return", "volume_change", "etf_relative_strength"),
        execution_assumptions=(
            "daily_bar_paper_replay_only",
            "no_live_order_route",
            "a_share_etf_rules_preserved",
        ),
        known_limitations=(
            "small_sample_only",
            "no_runtime_framework_execution",
            "no_live_provider_fetch",
        ),
        runtime_disabled_by_default=True,
    )
    return (
        OpenSourceBacktestHandoff(target="qlib_offline_ai_quant_backtest", **common),
        OpenSourceBacktestHandoff(target="rqalpha_later_event_driven_backtest", **common),
    )


def summarize_ai_adjusted_replay_impact(
    adjusted: AIAdjustedReplayResult,
) -> tuple[str, ...]:
    """Summarize deterministic adjusted replay deltas."""

    return (
        f"fill_rate_delta:{adjusted.fill_rate_delta}",
        f"zero_trade_day_delta:{adjusted.zero_trade_day_delta}",
        f"capital_usage_delta:{adjusted.capital_usage_delta}",
        f"cost_drag_delta:{adjusted.cost_drag_delta}",
        f"net_pnl_after_cost_delta:{adjusted.net_pnl_after_cost_delta}",
        f"turnover_delta:{adjusted.turnover_delta}",
        f"etf_weight_change:{adjusted.etf_weight_change}",
    )
