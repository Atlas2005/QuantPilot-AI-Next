from __future__ import annotations

from dataclasses import replace

from quantpilot_core.qlib_offline_tradability_evaluation_fixture import (
    OfflineQlibCompatiblePlan,
    build_offline_tradability_evaluation_report,
    create_default_evaluation_window,
    create_default_qlib_compatible_plan,
    create_default_signal_fixture,
    create_default_tradability_dataset,
    create_zero_trade_signal_fixture,
    evaluate_offline_tradability_fixture,
    validate_qlib_compatible_plan,
)


def default_report():
    dataset = create_default_tradability_dataset()
    signals = create_default_signal_fixture()
    window = create_default_evaluation_window()
    plan = create_default_qlib_compatible_plan(dataset)
    return build_offline_tradability_evaluation_report(dataset, signals, window, plan)


def test_fixture_creates_deterministic_a_share_like_bars() -> None:
    dataset = create_default_tradability_dataset()

    assert dataset.dataset_uri == "fixtures/qlib_offline_tradability/a_share_daily"
    assert tuple(bar.symbol for bar in dataset.bars) == (
        "000001.SZ",
        "000001.SZ",
        "600000.SH",
        "600000.SH",
    )
    assert tuple(bar.trading_date for bar in dataset.bars) == (
        "2026-01-02",
        "2026-01-05",
        "2026-01-02",
        "2026-01-05",
    )


def test_fixture_creates_deterministic_signals() -> None:
    signals = create_default_signal_fixture()

    assert tuple(signal.signal_id for signal in signals.signals) == (
        "sig-buy-000001",
        "sig-sell-600000",
    )
    assert signals.expected_order_intent_count == 2
    assert signals.expected_simulated_fill_count == 1


def test_valid_evaluation_produces_order_intent() -> None:
    report = default_report()

    assert report.produced_signals is True
    assert report.produced_order_intents is True
    assert report.result.order_intent_count == 2


def test_valid_evaluation_produces_simulated_fill() -> None:
    report = default_report()

    assert report.produced_simulated_fills is True
    assert report.result.simulated_fill_count == 1
    assert report.result.fill_simulation.fills[0].order_id == "sig-buy-000001"


def test_cost_tax_slippage_are_included() -> None:
    report = default_report()
    fill = report.result.fill_simulation.fills[0]

    assert fill.commission == 5.0
    assert fill.stamp_duty == 0.0
    assert fill.slippage_cost == 0.5
    assert report.result.estimated_fee_slippage_tax == 5.5


def test_fill_rate_is_computed() -> None:
    report = default_report()

    assert report.result.fill_rate == 0.5
    assert report.fill_rate_positive is True


def test_zero_trade_scenario_reports_exact_reasons() -> None:
    dataset = create_default_tradability_dataset()
    signals = create_zero_trade_signal_fixture()
    window = create_default_evaluation_window()
    plan = create_default_qlib_compatible_plan(dataset)

    report = build_offline_tradability_evaluation_report(dataset, signals, window, plan)

    assert report.result.simulated_fill_count == 0
    assert report.result.zero_trade_reason_distribution == {"odd_lot": 1}
    assert report.next_improvement_target == "liquidity_tradability"


def test_local_only_dataset_uri_accepted() -> None:
    plan = create_default_qlib_compatible_plan()

    assert validate_qlib_compatible_plan(plan) == ()


def test_remote_dataset_uri_rejected() -> None:
    plan = replace(create_default_qlib_compatible_plan(), dataset_uri="https://example.invalid/dataset")

    assert validate_qlib_compatible_plan(plan) == ("dataset_uri_remote",)


def test_qlib_is_not_imported_or_required() -> None:
    report = default_report()

    assert "runtime_execution_disabled" in report.result.qlib_compatibility_notes
    assert report.qlib_plan.allow_runtime_execution is False


def test_no_qrun_default_runtime_execution() -> None:
    report = default_report()

    assert report.qlib_plan.allow_runtime_execution is False
    assert "runtime_execution_requested" not in report.result.qlib_compatibility_notes


def test_qlib_compatibility_metadata_includes_required_boundaries() -> None:
    report = default_report()

    assert "dataset_uri_local_only" in report.result.qlib_compatibility_notes
    assert "calendar_explicit" in report.result.qlib_compatibility_notes
    assert "benchmark_explicit" in report.result.qlib_compatibility_notes
    assert "factor_metric_handoff_explicit" in report.result.qlib_compatibility_notes
    assert report.qlib_plan.benchmark_symbol == "000300.SH"
    assert report.qlib_plan.factor_metric_handoff.decision == "pass"


def test_deterministic_report_ordering() -> None:
    report = default_report()

    assert tuple(intent.signal_id for intent in report.result.fill_simulation.order_intents) == (
        "sig-buy-000001",
        "sig-sell-600000",
    )
    assert tuple(note for note in report.result.qlib_compatibility_notes[:5]) == (
        "dataset_uri_local_only",
        "calendar_explicit",
        "benchmark_explicit",
        "factor_metric_handoff_explicit",
        "runtime_execution_disabled",
    )


def test_safety_barrier_stays_at_or_below_140() -> None:
    report = default_report()

    assert report.safety_barrier_percent <= 140.0
    assert report.suspected_overblocking is False


def test_no_broker_network_llm_behavior() -> None:
    report = default_report()

    assert report.result.raw_signal_count == 2
    assert report.result.net_pnl_after_cost == 14.51
    assert report.next_improvement_target == "alpha_quality"


def test_no_mutation_of_input_fixtures() -> None:
    dataset = create_default_tradability_dataset()
    signals = create_default_signal_fixture()
    window = create_default_evaluation_window()
    plan = create_default_qlib_compatible_plan(dataset)
    before_dataset = replace(dataset)
    before_signals = replace(signals)
    before_window = replace(window)
    before_plan = replace(plan)

    evaluate_offline_tradability_fixture(dataset, signals, window, plan)

    assert dataset == before_dataset
    assert signals == before_signals
    assert window == before_window
    assert plan == before_plan
