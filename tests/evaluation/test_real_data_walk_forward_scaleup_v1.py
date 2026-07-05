from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from quantpilot_core.evaluation import real_data_walk_forward_smoke as scaleup_module
from quantpilot_core.evaluation import (
    DEFAULT_REAL_DATA_SCALEUP_SYMBOLS,
    FACTOR_RANKING_SWEEP_BASELINE_REFERENCE,
    FACTOR_RANKING_SWEEP_INTEGRATION_MODES,
    FactorRankingSweepIntegrationConfig,
    FactorRankingSweepIntegrationReport,
    REAL_DATA_SCALEUP_RANKING_MODES,
    RealDataWalkForwardScaleupConfig,
    RealDataWalkForwardScaleupReport,
    RealDataWalkForwardScaleupSweepConfig,
    RealDataWalkForwardScaleupSweepReport,
    build_real_data_walk_forward_scaleup_sweep_grid,
    run_factor_ranking_sweep_integration_v1,
    run_real_data_walk_forward_scaleup_sweep,
    run_real_data_walk_forward_scaleup_v1,
)
from quantpilot_core.real_data_provider import (
    DailyBarRequest,
    NormalizedDailyBar,
    ProviderName,
)


FIXTURE_SYMBOLS = (
    "000001.SZ",
    "000002.SZ",
    "000063.SZ",
    "000100.SZ",
    "000333.SZ",
    "000338.SZ",
    "000538.SZ",
    "000568.SZ",
    "000596.SZ",
    "000651.SZ",
    "600000.SH",
    "601318.SH",
)


class ScaleupFixtureProvider:
    provider_name = ProviderName.BAOSTOCK

    def __init__(self, *, empty_symbols: set[str] | None = None) -> None:
        self.empty_symbols = set(empty_symbols or set())
        self.requests: list[DailyBarRequest] = []

    def fetch_daily_bars(self, request: DailyBarRequest) -> list[NormalizedDailyBar]:
        self.requests.append(request)
        canonical = _canonical_from_provider_symbol(request.symbol)
        if canonical in self.empty_symbols:
            return []
        symbol_index = FIXTURE_SYMBOLS.index(canonical) if canonical in FIXTURE_SYMBOLS else 0
        start = date(2026, 1, 1)
        rows: list[NormalizedDailyBar] = []
        for index in range(32):
            trade_date = start + timedelta(days=index)
            drift = 0.06 + (symbol_index % 5) * 0.025
            base = 8.0 + symbol_index * 0.45 + index * drift
            if symbol_index % 7 == 0:
                base -= index * 0.015
            rows.append(
                NormalizedDailyBar(
                    symbol=request.symbol,
                    trade_date=trade_date,
                    open=base,
                    high=base + 0.35,
                    low=base - 0.2,
                    close=base + (0.08 if symbol_index % 2 == 0 else -0.03),
                    volume=1_000_000 + symbol_index * 10_000 + index * 1_000,
                    amount=(base + 0.05) * 1_000_000,
                    provider=ProviderName.BAOSTOCK,
                )
            )
        return rows


class RotatingLeadershipProvider:
    provider_name = ProviderName.BAOSTOCK

    def fetch_daily_bars(self, request: DailyBarRequest) -> list[NormalizedDailyBar]:
        canonical = _canonical_from_provider_symbol(request.symbol)
        symbol_index = FIXTURE_SYMBOLS.index(canonical) if canonical in FIXTURE_SYMBOLS else 0
        leader_group = symbol_index < 6
        start = date(2026, 1, 1)
        rows: list[NormalizedDailyBar] = []
        for index in range(32):
            trade_date = start + timedelta(days=index)
            if leader_group:
                slope = 0.8 if index < 11 else -0.25
            else:
                slope = -0.05 if index < 11 else 0.9
            base = 10.0 + symbol_index * 0.35 + index * slope
            rows.append(
                NormalizedDailyBar(
                    symbol=request.symbol,
                    trade_date=trade_date,
                    open=base,
                    high=base + 0.3,
                    low=max(1.0, base - 0.2),
                    close=max(1.0, base + 0.1),
                    volume=2_000_000 + symbol_index * 10_000 + index * 1_000,
                    amount=max(1.0, base) * 2_000_000,
                    provider=ProviderName.BAOSTOCK,
                )
            )
        return rows


def scaleup_config(provider, **overrides) -> RealDataWalkForwardScaleupConfig:
    values = {
        "symbols": FIXTURE_SYMBOLS,
        "start_date": "2026-01-01",
        "end_date": "2026-02-01",
        "initial_cash": 120_000.0,
        "train_window_days": 6,
        "test_window_days": 5,
        "max_windows": 3,
        "min_symbols_required": 8,
        "artifact_path": None,
        "provider": provider,
    }
    values.update(overrides)
    return RealDataWalkForwardScaleupConfig(**values)


def _canonical_from_provider_symbol(symbol: str) -> str:
    if symbol.startswith(("sz.", "sh.")):
        exchange, code = symbol.split(".")
        return f"{code}.{exchange.upper()}"
    return symbol


def test_scaleup_config_defaults_are_stock_first_and_manual() -> None:
    config = RealDataWalkForwardScaleupConfig()

    assert len(config.symbols) == 40
    assert 20 <= len(config.symbols) <= 50
    assert config.provider == "tushare_primary_baostock_fallback"
    assert config.allow_partial_universe is True
    assert config.min_symbols_required == 20
    assert config.benchmark_mode == "equal_weight_close_to_close"
    assert config.advisory_mode == "disabled"
    assert config.max_position_weight == 0.10
    assert config.target_position_count == 10
    assert config.reserve_cash_weight == 0.02
    assert config.rebalance_each_window is True
    assert config.ranking_mode == "momentum_60d"
    assert config.min_order_lot == 100
    assert config.max_rejected_trade_ratio_warning == 0.20
    assert str(config.artifact_path).startswith("artifacts/real_data_walk_forward_scaleup/")
    assert not any(symbol.startswith(("510", "159")) for symbol in DEFAULT_REAL_DATA_SCALEUP_SYMBOLS)


def test_scaleup_sweep_grid_generation_matches_requested_medium_grid() -> None:
    grid = build_real_data_walk_forward_scaleup_sweep_grid(
        RealDataWalkForwardScaleupSweepConfig(provider=ScaleupFixtureProvider())
    )

    assert len(grid) == 72
    assert {config.target_position_count for config in grid} == {10, 15, 20}
    assert {config.max_position_weight for config in grid} == {0.05, 0.08, 0.10}
    assert {config.reserve_cash_weight for config in grid} == {0.02, 0.05}
    assert {config.ranking_mode for config in grid} == set(REAL_DATA_SCALEUP_RANKING_MODES)
    assert all(config.rebalance_each_window is True for config in grid)
    assert grid[0].metadata["parameter_set_id"] == "scaleup-sweep-001"
    assert grid[-1].metadata["parameter_set_id"] == "scaleup-sweep-072"
    assert all(config.artifact_path is None for config in grid)


def test_factor_modes_are_accepted_by_scaleup_sweep_grid_without_changing_default() -> None:
    default_grid = build_real_data_walk_forward_scaleup_sweep_grid(
        RealDataWalkForwardScaleupSweepConfig(provider=ScaleupFixtureProvider())
    )
    factor_grid = build_real_data_walk_forward_scaleup_sweep_grid(
        RealDataWalkForwardScaleupSweepConfig(
            provider=ScaleupFixtureProvider(),
            ranking_modes=FACTOR_RANKING_SWEEP_INTEGRATION_MODES,
            target_position_counts=(6,),
            max_position_weights=(0.08,),
            reserve_cash_weights=(0.02,),
        )
    )

    assert len(default_grid) == 72
    assert {config.ranking_mode for config in default_grid} == set(REAL_DATA_SCALEUP_RANKING_MODES)
    assert len(factor_grid) == len(FACTOR_RANKING_SWEEP_INTEGRATION_MODES)
    assert {config.ranking_mode for config in factor_grid} == set(FACTOR_RANKING_SWEEP_INTEGRATION_MODES)


def test_scaleup_aggregate_metrics_and_contributors_are_computed() -> None:
    report = run_real_data_walk_forward_scaleup_v1(scaleup_config(ScaleupFixtureProvider()))

    assert isinstance(report, RealDataWalkForwardScaleupReport)
    assert report.windows_run == 3
    assert report.valid_symbols == tuple(sorted(FIXTURE_SYMBOLS))
    assert report.skipped_symbols == ()
    assert report.total_return is not None
    assert report.benchmark_total_return is not None
    assert report.strategy_excess_return == round(report.total_return - report.benchmark_total_return, 6)
    assert report.win_rate_by_window is not None
    assert report.equity_window_return == tuple(
        round((metrics["ending_equity"] - metrics["starting_equity"]) / metrics["starting_equity"], 6)
        for metrics in report.per_window_metrics
    )
    assert report.average_window_return is not None
    assert report.median_window_return is not None
    assert report.worst_window_return is not None
    assert report.win_rate_by_window == round(
        sum(1 for value in report.equity_window_return if value > 0) / len(report.equity_window_return),
        6,
    )
    assert report.turnover > 0
    assert report.cost_total >= 0
    assert report.cost_to_turnover_ratio is not None
    assert report.filled_trades >= 1
    assert report.rejected_trade_ratio == 0.0
    assert report.rejection_reasons.get("insufficient_cash", 0) == 0
    assert min(report.actual_position_count_by_window) > 3
    assert max(weight for weight in report.largest_position_weight_by_window if weight is not None) <= 0.12
    assert all(
        target <= 0.10
        for metrics in report.per_window_metrics
        for target in metrics["target_weights"].values()
    )
    assert all(
        trade["shares"] % 100 == 0
        for metrics in report.per_window_metrics
        for trade in metrics["per_symbol_breakdown"]
        if trade["shares"] > 0
    )
    assert set(report.per_symbol_total_pnl) == set(FIXTURE_SYMBOLS)
    assert set(report.contribution_to_total_return) == set(FIXTURE_SYMBOLS)
    assert len(report.top_contributors) <= 5
    assert len(report.worst_contributors) <= 5
    assert report.top_contributors[0]["total_pnl"] >= report.top_contributors[-1]["total_pnl"]
    assert report.worst_contributors[0]["total_pnl"] <= report.worst_contributors[-1]["total_pnl"]
    assert "no_broker_live_execution" in report.notes
    assert "deepseek_live_disabled_by_default" in report.notes
    assert report.mature_framework_hooks["vectorbt_stats_adapter"] == "optional_not_required"


def test_scaleup_rebalance_sells_before_buys_when_leadership_rotates() -> None:
    report = run_real_data_walk_forward_scaleup_v1(
        scaleup_config(
            RotatingLeadershipProvider(),
            initial_cash=200_000.0,
            target_position_count=6,
            max_position_weight=0.10,
            train_window_days=6,
            test_window_days=5,
            max_windows=4,
            min_symbols_required=8,
        )
    )

    mixed_windows = [
        metrics for metrics in report.per_window_metrics
        if "sell" in metrics["rebalance_order_sides"] and "buy" in metrics["rebalance_order_sides"]
    ]

    assert report.rebalance_sell_count > 0
    assert report.rebalance_buy_count > 0
    assert mixed_windows
    for metrics in mixed_windows:
        sides = metrics["rebalance_order_sides"]
        assert max(index for index, side in enumerate(sides) if side == "sell") < min(
            index for index, side in enumerate(sides) if side == "buy"
        )


def test_scaleup_resizes_or_skips_buys_in_lot_sized_cash_aware_path() -> None:
    report = run_real_data_walk_forward_scaleup_v1(
        scaleup_config(
            ScaleupFixtureProvider(),
            initial_cash=18_000.0,
            target_position_count=10,
            max_position_weight=0.10,
            min_symbols_required=8,
        )
    )

    assert report.rejected_trade_ratio == 0.0
    assert report.rejection_reasons.get("insufficient_cash", 0) == 0
    assert report.skipped_below_lot_count > 0
    assert all(
        metrics["skipped_below_lot_count"] >= 0
        for metrics in report.per_window_metrics
    )


def test_scaleup_records_resized_buy_orders_before_cash_rejection() -> None:
    proposal, notes = scaleup_module._build_rebalance_proposal(
        account=scaleup_module.PaperAccount(cash=50_000.0),
        prices={"000001.SZ": 100.0},
        selected_symbols=("000001.SZ",),
        target_weights={"000001.SZ": 0.90},
        equity=100_000.0,
        config=RealDataWalkForwardScaleupConfig(
            symbols=FIXTURE_SYMBOLS,
            reserve_cash_weight=0.02,
            max_position_weight=0.90,
            target_position_count=1,
            artifact_path=None,
        ),
        cost_assumptions=scaleup_module.PaperFillCostAssumptions(lot_size=100),
        run_label="resize-test",
    )

    assert notes["resized_order_count"] == 1
    assert proposal.intents[0].target_shares == 400
    assert proposal.intents[0].metadata["resized_order"] is True


def test_turnover_aware_defaults_preserve_rebalance_builder_behavior() -> None:
    account = scaleup_module.PaperAccount(cash=50_000.0)
    prices = {"000001.SZ": 100.0}
    common = {
        "account": account,
        "prices": prices,
        "selected_symbols": ("000001.SZ",),
        "target_weights": {"000001.SZ": 0.90},
        "equity": 100_000.0,
        "cost_assumptions": scaleup_module.PaperFillCostAssumptions(lot_size=100),
        "run_label": "turnover-default-test",
    }

    baseline, baseline_notes = scaleup_module._build_rebalance_proposal(
        config=RealDataWalkForwardScaleupConfig(
            symbols=FIXTURE_SYMBOLS,
            reserve_cash_weight=0.02,
            max_position_weight=0.90,
            target_position_count=1,
            artifact_path=None,
        ),
        **common,
    )
    disabled, disabled_notes = scaleup_module._build_rebalance_proposal(
        config=RealDataWalkForwardScaleupConfig(
            symbols=FIXTURE_SYMBOLS,
            reserve_cash_weight=0.02,
            max_position_weight=0.90,
            target_position_count=1,
            artifact_path=None,
            turnover_aware_rebalance=scaleup_module.TurnoverAwareRebalanceConfig(enabled=False),
        ),
        **common,
    )

    assert tuple(intent.target_shares for intent in disabled.intents) == tuple(intent.target_shares for intent in baseline.intents)
    assert disabled_notes["orders_proposed_before_turnover_controls"] == baseline_notes["orders_proposed_before_turnover_controls"]
    assert disabled_notes["orders_retained"] == baseline_notes["orders_retained"]


def test_turnover_aware_minimum_order_value_skips_small_non_liquidation_orders() -> None:
    proposal, notes = scaleup_module._build_rebalance_proposal(
        account=scaleup_module.PaperAccount(
            cash=100_000.0,
            positions={"000001.SZ": 1000},
            average_costs={"000001.SZ": 10.0},
        ),
        prices={"000001.SZ": 10.0, "000002.SZ": 10.0},
        selected_symbols=("000001.SZ", "000002.SZ"),
        target_weights={"000001.SZ": 0.10, "000002.SZ": 0.10},
        equity=200_000.0,
        config=RealDataWalkForwardScaleupConfig(
            symbols=FIXTURE_SYMBOLS,
            reserve_cash_weight=0.02,
            max_position_weight=0.20,
            target_position_count=2,
            artifact_path=None,
            turnover_aware_rebalance=scaleup_module.TurnoverAwareRebalanceConfig(
                enabled=True,
                minimum_order_value=50_000.0,
            ),
        ),
        cost_assumptions=scaleup_module.PaperFillCostAssumptions(lot_size=100),
        run_label="minimum-order-test",
    )

    assert len(proposal.intents) == 0
    assert notes["raw_orders_before_controls"] == 2
    assert notes["orders_proposed_before_turnover_controls"] == 2
    assert notes["orders_after_minimum_order_value"] == 0
    assert notes["final_orders_retained"] == 0
    assert notes["orders_retained"] == 0
    assert notes["orders_skipped_by_minimum_order_value"] == 2
    assert notes["direct_filter_estimated_cost_avoided"] > 0
    assert notes["direct_filter_estimated_turnover_avoided"] > 0


def test_turnover_aware_order_construction_reports_zero_delta_domain() -> None:
    proposal, notes = scaleup_module._build_rebalance_proposal(
        account=scaleup_module.PaperAccount(
            cash=90_000.0,
            positions={"000001.SZ": 1000},
            average_costs={"000001.SZ": 10.0},
        ),
        prices={"000001.SZ": 10.0},
        selected_symbols=("000001.SZ",),
        target_weights={"000001.SZ": 0.10},
        equity=100_000.0,
        config=RealDataWalkForwardScaleupConfig(
            symbols=FIXTURE_SYMBOLS,
            reserve_cash_weight=0.02,
            max_position_weight=0.20,
            target_position_count=1,
            artifact_path=None,
            turnover_aware_rebalance=scaleup_module.TurnoverAwareRebalanceConfig(enabled=True),
        ),
        cost_assumptions=scaleup_module.PaperFillCostAssumptions(lot_size=100),
        run_label="zero-delta-test",
    )

    attribution = scaleup_module._turnover_attribution_from_notes(notes)

    assert proposal.intents == ()
    assert attribution["order_construction_attribution"]["raw_target_weight_deltas"] == 1
    assert attribution["order_construction_attribution"]["orders_removed_as_zero_delta"] == 1
    assert attribution["order_construction_attribution"]["final_order_intents"] == 0


def test_turnover_aware_invalid_rank_hysteresis_fails_locally() -> None:
    with pytest.raises(ValueError, match="exit_rank_threshold"):
        scaleup_module._validate_scaleup_config(
            RealDataWalkForwardScaleupConfig(
                turnover_aware_rebalance=scaleup_module.TurnoverAwareRebalanceConfig(
                    enabled=True,
                    entry_rank_threshold=10,
                    exit_rank_threshold=5,
                )
            )
        )


def test_scaleup_skips_empty_symbols_when_partial_universe_allowed() -> None:
    provider = ScaleupFixtureProvider(empty_symbols={"000538.SZ", "600000.SH"})

    report = run_real_data_walk_forward_scaleup_v1(
        scaleup_config(provider, min_symbols_required=8)
    )

    assert report.windows_run == 3
    assert report.skipped_symbols == ("000538.SZ", "600000.SH")
    assert "missing_symbols:000538.SZ,600000.SH" in report.data_quality_warnings
    assert "empty_provider_rows:sz.000538" in report.data_quality_warnings
    assert "empty_provider_rows:sh.600000" in report.data_quality_warnings
    assert len(report.valid_symbols) == len(FIXTURE_SYMBOLS) - 2


def test_scaleup_requires_min_symbols_without_hard_failing_one_bad_symbol() -> None:
    provider = ScaleupFixtureProvider(empty_symbols=set(FIXTURE_SYMBOLS[:5]))

    report = run_real_data_walk_forward_scaleup_v1(
        scaleup_config(provider, min_symbols_required=8)
    )

    assert report.notes[0] == "real_data_walk_forward_scaleup_v1_unavailable"
    assert report.windows_run == 0
    assert report.final_equity is None
    assert report.skipped_symbols == FIXTURE_SYMBOLS[:5]
    assert report.valid_symbols == tuple(sorted(FIXTURE_SYMBOLS[5:]))
    assert any(warning.startswith("empty_provider_rows:") for warning in report.data_quality_warnings)


def test_scaleup_artifact_json_serialization_works_with_temp_path(tmp_path: Path) -> None:
    artifact_path = tmp_path / "scaleup" / "latest_report.json"

    report = run_real_data_walk_forward_scaleup_v1(
        scaleup_config(ScaleupFixtureProvider(), artifact_path=artifact_path)
    )

    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert report.artifact_path == str(artifact_path)
    assert payload["artifact_path"] == str(artifact_path)
    assert payload["provider"] == "baostock"
    assert payload["windows_run"] == 3
    assert payload["top_contributors"] == list(report.top_contributors)
    assert payload["equity_window_return"] == list(report.equity_window_return)
    assert payload["actual_position_count_by_window"] == list(report.actual_position_count_by_window)
    assert payload["largest_position_weight_by_window"] == list(report.largest_position_weight_by_window)
    assert payload["rejected_trade_ratio"] == report.rejected_trade_ratio
    assert payload["resized_order_count"] == report.resized_order_count
    assert payload["skipped_below_lot_count"] == report.skipped_below_lot_count
    assert payload["rebalance_sell_count"] == report.rebalance_sell_count
    assert payload["rebalance_buy_count"] == report.rebalance_buy_count
    assert payload["contribution_to_total_return"] == report.contribution_to_total_return
    assert payload["per_window_metrics"][0]["total_pnl"] == report.per_window_metrics[0]["total_pnl"]


def test_scaleup_sweep_ranks_parameter_sets_and_serializes_json(tmp_path: Path) -> None:
    artifact_path = tmp_path / "sweep" / "latest_report.json"

    report = run_real_data_walk_forward_scaleup_sweep(
        RealDataWalkForwardScaleupSweepConfig(
            symbols=FIXTURE_SYMBOLS,
            start_date="2026-01-01",
            end_date="2026-02-01",
            initial_cash=120_000.0,
            train_window_days=6,
            test_window_days=5,
            max_windows=3,
            min_symbols_required=8,
            provider=ScaleupFixtureProvider(),
            artifact_path=artifact_path,
            target_position_counts=(6, 8),
            max_position_weights=(0.08,),
            reserve_cash_weights=(0.02,),
            ranking_modes=("momentum_20d", "low_volatility"),
            top_n=3,
        )
    )

    payload = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert isinstance(report, RealDataWalkForwardScaleupSweepReport)
    assert report.artifact_path == str(artifact_path)
    assert report.parameter_set_count == 4
    assert len(report.parameter_sets) == 4
    assert len(report.top_parameter_sets_by_excess) == 3
    assert len(report.top_parameter_sets_by_return) == 3
    assert len(report.top_parameter_sets_by_drawdown_adjusted) == 3
    assert "no_profitability_claim" in report.notes
    assert payload["artifact_path"] == str(artifact_path)
    assert payload["parameter_set_count"] == 4
    assert payload["top_parameter_sets_by_excess"] == list(report.top_parameter_sets_by_excess)
    assert payload["top_parameter_sets_by_return"] == list(report.top_parameter_sets_by_return)
    assert payload["top_parameter_sets_by_drawdown_adjusted"] == list(report.top_parameter_sets_by_drawdown_adjusted)
    assert all(
        {
            "parameter_set_id",
            "ranking_mode",
            "target_position_count",
            "max_position_weight",
            "reserve_cash_weight",
            "total_return",
            "benchmark_total_return",
            "strategy_excess_return",
            "max_drawdown",
            "win_rate_by_window",
            "average_window_return",
            "median_window_return",
            "worst_window_return",
            "turnover",
            "cost_total",
            "cost_to_turnover_ratio",
            "rejected_trade_ratio",
            "average_position_count",
            "average_largest_position_weight",
            "top_contributors",
            "worst_contributors",
        }
        <= set(row)
        for row in report.parameter_sets
    )
    excess_values = [row["strategy_excess_return"] for row in report.top_parameter_sets_by_excess]
    assert excess_values == sorted(excess_values, reverse=True)


def test_factor_mode_sweep_report_serializes_baseline_and_per_mode_summary(tmp_path: Path) -> None:
    artifact_path = tmp_path / "factor_sweep" / "latest_report.json"

    report = run_factor_ranking_sweep_integration_v1(
        FactorRankingSweepIntegrationConfig(
            symbols=FIXTURE_SYMBOLS,
            start_date="2026-01-01",
            end_date="2026-02-01",
            initial_cash=120_000.0,
            train_window_days=6,
            test_window_days=5,
            max_windows=2,
            min_symbols_required=8,
            provider=ScaleupFixtureProvider(),
            artifact_path=artifact_path,
            target_position_counts=(6,),
            max_position_weights=(0.08,),
            reserve_cash_weights=(0.02,),
            factor_ranking_modes=(
                "low_volatility_v1",
                "defensive_composite_v1",
                "momentum_reversal_guarded",
            ),
            top_n=2,
        )
    )

    payload = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert isinstance(report, FactorRankingSweepIntegrationReport)
    assert report.artifact_path == str(artifact_path)
    assert report.provider == "baostock"
    assert report.symbols_requested == FIXTURE_SYMBOLS
    assert report.valid_symbols == tuple(sorted(FIXTURE_SYMBOLS))
    assert report.factor_ranking_modes == (
        "low_volatility_v1",
        "defensive_composite_v1",
        "momentum_reversal_guarded",
    )
    assert report.parameter_set_count == 3
    assert report.baseline_reference == FACTOR_RANKING_SWEEP_BASELINE_REFERENCE
    assert {row["ranking_mode"] for row in report.per_mode_summary} == set(report.factor_ranking_modes)
    assert len(report.top_parameter_sets_by_excess) == 2
    assert len(report.top_parameter_sets_by_return) == 2
    assert len(report.top_parameter_sets_by_drawdown_adjusted) == 2
    assert "no_profitability_claim" in report.notes
    assert payload["artifact_path"] == str(artifact_path)
    assert payload["provider"] == "baostock"
    assert payload["date_range"] == ["2026-01-01", "2026-02-01"]
    assert payload["symbols_requested"] == list(FIXTURE_SYMBOLS)
    assert payload["valid_symbols"] == sorted(FIXTURE_SYMBOLS)
    assert payload["factor_ranking_modes"] == list(report.factor_ranking_modes)
    assert payload["baseline_reference"] == FACTOR_RANKING_SWEEP_BASELINE_REFERENCE
    assert payload["per_mode_summary"] == list(report.per_mode_summary)
    assert all(
        {
            "rejected_trade_ratio",
            "turnover",
            "cost_total",
            "cost_to_turnover_ratio",
            "max_drawdown",
            "total_return",
            "benchmark_total_return",
            "strategy_excess_return",
        }
        <= set(row)
        for row in payload["parameter_sets"]
    )


def test_factor_mode_sweep_reuses_loaded_provider_data_across_parameter_sets() -> None:
    provider = ScaleupFixtureProvider()

    report = run_factor_ranking_sweep_integration_v1(
        FactorRankingSweepIntegrationConfig(
            symbols=FIXTURE_SYMBOLS,
            start_date="2026-01-01",
            end_date="2026-02-01",
            initial_cash=120_000.0,
            train_window_days=6,
            test_window_days=5,
            max_windows=2,
            min_symbols_required=8,
            provider=provider,
            artifact_path=None,
            target_position_counts=(6, 8),
            max_position_weights=(0.08,),
            reserve_cash_weights=(0.02,),
            factor_ranking_modes=("low_volatility_v1", "defensive_composite_v1"),
        )
    )

    assert report.parameter_set_count == 4
    assert len(provider.requests) == len(FIXTURE_SYMBOLS)
    assert {(request.symbol, request.start_date, request.end_date) for request in provider.requests} == {
        (f"{symbol[-2:].lower()}.{symbol[:6]}", date(2026, 1, 1), date(2026, 2, 1))
        for symbol in FIXTURE_SYMBOLS
    }


def test_scaleup_ranking_modes_change_candidate_ranking() -> None:
    frame = scaleup_module._bars_to_price_frame(
        ScaleupFixtureProvider().fetch_daily_bars(
            DailyBarRequest(
                symbol="sz.000001",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 2, 1),
            )
        )
        + ScaleupFixtureProvider().fetch_daily_bars(
            DailyBarRequest(
                symbol="sz.000002",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 2, 1),
            )
        )
    )
    start_prices = {"000001.SZ": 10.0, "000002.SZ": 10.0}

    momentum_selected = scaleup_module._select_scaleup_candidates(
        frame,
        start_prices,
        RealDataWalkForwardScaleupConfig(
            symbols=FIXTURE_SYMBOLS,
            target_position_count=1,
            ranking_mode="momentum_20d",
            artifact_path=None,
        ),
    )
    baseline_selected = scaleup_module._select_scaleup_candidates(
        frame,
        start_prices,
        RealDataWalkForwardScaleupConfig(
            symbols=FIXTURE_SYMBOLS,
            target_position_count=1,
            ranking_mode="equal_weight_baseline",
            artifact_path=None,
        ),
    )

    assert momentum_selected == ("000002.SZ",)
    assert baseline_selected == ("000001.SZ",)


def test_scaleup_fixture_run_uses_no_external_network_llm_or_broker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_provider_constructor(*args, **kwargs):
        raise AssertionError("real provider constructor must not be used")

    def fail_deepseek(*args, **kwargs):
        raise AssertionError("DeepSeek advisory must not run in scale-up tests")

    monkeypatch.setattr(
        "quantpilot_core.evaluation.real_data_walk_forward_smoke.BaoStockDailyBarProvider",
        fail_provider_constructor,
    )
    monkeypatch.setattr(
        "quantpilot_core.evaluation.real_data_walk_forward_smoke.AkShareDailyBarProvider",
        fail_provider_constructor,
    )
    monkeypatch.setattr(
        "quantpilot_core.evaluation.real_data_walk_forward_smoke.import_module",
        fail_provider_constructor,
    )
    monkeypatch.setattr("quantpilot_core.walk_forward.engine.run_deepseek_advisory_fallback", fail_deepseek)

    report = run_real_data_walk_forward_scaleup_v1(scaleup_config(ScaleupFixtureProvider()))

    assert report.windows_run == 3
    assert "no_broker_live_execution" in report.notes
    assert "advisory_mode:disabled" in report.notes


def test_scaleup_sweep_fixture_run_uses_no_external_network_llm_or_broker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_provider_constructor(*args, **kwargs):
        raise AssertionError("real provider constructor must not be used")

    def fail_deepseek(*args, **kwargs):
        raise AssertionError("DeepSeek advisory must not run in sweep tests")

    monkeypatch.setattr(
        "quantpilot_core.evaluation.real_data_walk_forward_smoke.BaoStockDailyBarProvider",
        fail_provider_constructor,
    )
    monkeypatch.setattr(
        "quantpilot_core.evaluation.real_data_walk_forward_smoke.AkShareDailyBarProvider",
        fail_provider_constructor,
    )
    monkeypatch.setattr(
        "quantpilot_core.evaluation.real_data_walk_forward_smoke.import_module",
        fail_provider_constructor,
    )
    monkeypatch.setattr("quantpilot_core.walk_forward.engine.run_deepseek_advisory_fallback", fail_deepseek)

    report = run_real_data_walk_forward_scaleup_sweep(
        RealDataWalkForwardScaleupSweepConfig(
            symbols=FIXTURE_SYMBOLS,
            start_date="2026-01-01",
            end_date="2026-02-01",
            initial_cash=120_000.0,
            train_window_days=6,
            test_window_days=5,
            max_windows=2,
            min_symbols_required=8,
            provider=ScaleupFixtureProvider(),
            artifact_path=None,
            target_position_counts=(6,),
            max_position_weights=(0.08,),
            reserve_cash_weights=(0.02,),
            ranking_modes=("momentum_60d", "equal_weight_baseline"),
        )
    )

    assert report.parameter_set_count == 2
    assert "no_broker_live_execution" in report.notes
    assert "deepseek_live_disabled_by_default" in report.notes


def test_factor_sweep_fixture_run_uses_no_external_network_llm_or_broker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_provider_constructor(*args, **kwargs):
        raise AssertionError("real provider constructor must not be used")

    def fail_deepseek(*args, **kwargs):
        raise AssertionError("DeepSeek advisory must not run in factor sweep tests")

    monkeypatch.setattr(
        "quantpilot_core.evaluation.real_data_walk_forward_smoke.BaoStockDailyBarProvider",
        fail_provider_constructor,
    )
    monkeypatch.setattr(
        "quantpilot_core.evaluation.real_data_walk_forward_smoke.AkShareDailyBarProvider",
        fail_provider_constructor,
    )
    monkeypatch.setattr(
        "quantpilot_core.evaluation.real_data_walk_forward_smoke.import_module",
        fail_provider_constructor,
    )
    monkeypatch.setattr("quantpilot_core.walk_forward.engine.run_deepseek_advisory_fallback", fail_deepseek)

    report = run_factor_ranking_sweep_integration_v1(
        FactorRankingSweepIntegrationConfig(
            symbols=FIXTURE_SYMBOLS,
            start_date="2026-01-01",
            end_date="2026-02-01",
            initial_cash=120_000.0,
            train_window_days=6,
            test_window_days=5,
            max_windows=2,
            min_symbols_required=8,
            provider=ScaleupFixtureProvider(),
            artifact_path=None,
            target_position_counts=(6,),
            max_position_weights=(0.08,),
            reserve_cash_weights=(0.02,),
            factor_ranking_modes=("low_volatility_v1", "defensive_composite_v1"),
        )
    )

    assert report.parameter_set_count == 2
    assert report.baseline_reference["ranking_mode"] == "low_volatility"
    assert report.per_mode_summary
    assert "no_broker_live_execution" in report.notes
    assert "deepseek_live_disabled_by_default" in report.notes
