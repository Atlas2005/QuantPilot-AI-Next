from __future__ import annotations

import sys
from pathlib import Path

from quantpilot_core.alpha_sizing_etf_universe_tuning_loop import InstrumentType
from quantpilot_core.mixed_stock_etf_daily_paper_evaluation import (
    EvaluationScenarioType,
    build_mixed_stock_etf_comparison_report,
    compare_scenario_results,
    create_default_scenarios,
    create_mixed_stock_etf_scenario,
    create_stock_only_scenario,
    evaluate_capital_path_suitability,
    evaluate_scenario,
    validate_comparison_pair,
)


def test_deterministic_stock_only_scenario() -> None:
    scenario = create_stock_only_scenario()

    assert scenario.scenario_type == EvaluationScenarioType.STOCK_ONLY.value
    assert scenario.paper_input.initial_cash == 100_000.0
    assert scenario.paper_input.trading_days == ("2026-01-02", "2026-01-05", "2026-01-06")
    assert tuple(item.instrument_type for item in scenario.instruments) == (
        InstrumentType.STOCK.value,
        InstrumentType.STOCK.value,
    )


def test_deterministic_mixed_stock_etf_scenario() -> None:
    scenario = create_mixed_stock_etf_scenario()

    assert scenario.scenario_type == EvaluationScenarioType.MIXED_STOCK_ETF.value
    assert scenario.paper_input.initial_cash == 100_000.0
    assert scenario.paper_input.trading_days == ("2026-01-02", "2026-01-05", "2026-01-06")
    assert any(item.instrument_type == InstrumentType.ETF.value for item in scenario.instruments)


def test_same_initial_capital_and_window_across_scenarios() -> None:
    stock, mixed = create_default_scenarios()

    assert validate_comparison_pair(stock, mixed) == ()
    assert stock.paper_input.initial_cash == mixed.paper_input.initial_cash
    assert stock.paper_input.trading_days == mixed.paper_input.trading_days


def test_mixed_scenario_has_etf_candidates() -> None:
    result = evaluate_scenario(create_mixed_stock_etf_scenario())

    assert result.etf_candidate_count == 1
    assert result.etf_symbols == ("510300.SH",)


def test_stock_only_scenario_has_no_etf_candidates() -> None:
    result = evaluate_scenario(create_stock_only_scenario())

    assert result.stock_candidate_count == 2
    assert result.etf_candidate_count == 0
    assert result.etf_symbols == ()


def test_comparison_computes_fill_rate_delta() -> None:
    report = build_mixed_stock_etf_comparison_report()

    assert report.etf_impact.fill_rate_delta == 0.666667
    assert report.mixed_outperformed_on_fillability is True


def test_comparison_computes_zero_trade_day_delta() -> None:
    report = build_mixed_stock_etf_comparison_report()

    assert report.etf_impact.zero_trade_day_delta == -2
    assert report.mixed_reduced_zero_trade_days is True


def test_comparison_computes_capital_usage_delta() -> None:
    report = build_mixed_stock_etf_comparison_report()

    assert report.etf_impact.capital_usage_delta == 0.00677
    assert report.mixed_improved_capital_usage is True


def test_comparison_computes_cost_drag_delta() -> None:
    report = build_mixed_stock_etf_comparison_report()

    assert report.etf_impact.cost_drag_delta == -0.004205
    assert report.etf_impact.improves_cost_drag is True
    assert report.etf_created_excessive_cost_drag is False


def test_comparison_computes_net_pnl_after_cost_delta() -> None:
    report = build_mixed_stock_etf_comparison_report()

    assert report.etf_impact.net_pnl_after_cost_delta == 32.5738
    assert report.mixed_improved_net_pnl_after_cost is True


def test_etf_impact_summary_identifies_small_capital_improvement() -> None:
    stock_result = evaluate_scenario(create_stock_only_scenario())
    mixed_result = evaluate_scenario(create_mixed_stock_etf_scenario())
    impact = compare_scenario_results(stock_result, mixed_result)

    assert impact.diversification_proxy_delta == 1
    assert impact.improves_small_capital_suitability is True


def test_capital_path_suitability_reports_all_stages() -> None:
    report = build_mixed_stock_etf_comparison_report()

    assert tuple(item.stage_capital_cny for item in report.capital_path_suitability) == (
        1_000,
        10_000,
        100_000,
    )
    assert all(item.etf_inclusion_helps for item in report.capital_path_suitability)
    assert all(item.stock_only_viable for item in report.capital_path_suitability)


def test_mixed_universe_can_be_recommended_as_next_default_when_metrics_improve() -> None:
    report = build_mixed_stock_etf_comparison_report()

    assert report.mixed_should_be_next_default is True
    assert all(item.recommend_mixed_default for item in report.capital_path_suitability)


def test_stock_only_remains_viable_if_metrics_do_not_improve() -> None:
    stock = create_stock_only_scenario()
    report = build_mixed_stock_etf_comparison_report(stock, stock)

    assert report.stock_only_remains_viable is True
    assert report.mixed_should_be_next_default is False


def test_safety_barrier_remains_at_or_below_140() -> None:
    report = build_mixed_stock_etf_comparison_report(safety_barrier_percent=185.0)

    assert report.safety_barrier_percent <= 140.0
    assert report.stock_only_result.metrics.safety_barrier_percent <= 140.0
    assert report.mixed_result.metrics.safety_barrier_percent <= 140.0


def test_deterministic_report_ordering() -> None:
    stock, mixed = create_default_scenarios()
    report = build_mixed_stock_etf_comparison_report(stock, mixed)

    assert report.stock_only_result.scenario_id == "p38-stock-only"
    assert report.mixed_result.scenario_id == "p38-mixed-stock-etf"
    assert tuple(item.stage_capital_cny for item in report.capital_path_suitability) == (
        1_000,
        10_000,
        100_000,
    )
    assert report.evidence_refs == (
        "evidence://p38/scenario/mixed-stock-etf",
        "evidence://p38/scenario/stock-only",
    )


def test_capital_path_helper_can_be_called_directly() -> None:
    stock_result = evaluate_scenario(create_stock_only_scenario())
    mixed_result = evaluate_scenario(create_mixed_stock_etf_scenario())
    impact = compare_scenario_results(stock_result, mixed_result)

    suitability = evaluate_capital_path_suitability(stock_result, mixed_result, impact)

    assert suitability[0].stage_capital_cny == 1_000
    assert suitability[0].mixed_universe_viable is True


def test_no_forbidden_runtime_behavior() -> None:
    package_root = Path("src/quantpilot_core/mixed_stock_etf_daily_paper_evaluation")
    source_text = "\n".join(path.read_text() for path in sorted(package_root.glob("*.py")))

    forbidden_fragments = (
        "requests.",
        "connect_broker(",
        "place_order(",
        "send_order(",
        "submit_order(",
        "execute_order(",
        "api_key",
        "access_token",
        "qrun",
    )
    assert not any(fragment in source_text for fragment in forbidden_fragments)
    assert "qlib" not in sys.modules
