from quantpilot_core.daily_paper_trading_loop_tradability_metrics import (
    DailyTradabilityMetrics,
)
from quantpilot_core.mixed_stock_etf_daily_paper_evaluation import (
    EvaluationScenarioType,
    ScenarioEvaluationResult,
)
from quantpilot_core.real_provider_mixed_etf_paper_replay import (
    ProviderMixedUniverseSample,
    ProviderReplayResult,
    ProviderSampleSourceType,
    ProviderSampleValidationResult,
)
from quantpilot_core.vectorbt_old_chain_metrics_comparison import (
    MetricsComparisonStatus,
    OldChainMetricSourceType,
    OldChainReplayMetrics,
    build_old_chain_vectorbt_metrics_report,
    compare_old_chain_to_vectorbt,
    old_metrics_from_daily_tradability,
    old_metrics_from_provider_replay,
    old_metrics_from_scenario_result,
)
from quantpilot_core.vectorbt_replay_adapter import VectorbtReplayStatus
from quantpilot_core.vectorbt_replay_comparison import (
    VectorbtComparisonStatus,
    VectorbtReplayComparisonResult,
)


def daily_metrics(
    *,
    fill_rate: float = 0.5,
    fills: int = 2,
    zero_trade_days: int = 1,
    cost: float = 12.5,
    pnl: float = 88.0,
    capital_used_average: float = 0.35,
    turnover: float = 0.1,
    drawdown: float = 0.02,
) -> DailyTradabilityMetrics:
    return DailyTradabilityMetrics(
        trading_day_count=3,
        raw_signal_count_total=4,
        order_intent_count_total=3,
        simulated_fill_count_total=fills,
        fill_rate=fill_rate,
        zero_trade_day_count=zero_trade_days,
        zero_trade_reason_distribution={"no_signal": zero_trade_days},
        cost_tax_slippage_total=cost,
        gross_pnl_estimate=pnl + cost,
        net_pnl_after_cost=pnl,
        capital_used_average=capital_used_average,
        capital_used_max=0.5,
        turnover_estimate=turnover,
        drawdown_estimate=drawdown,
        suspected_overblocking_days=0,
        safety_barrier_percent=128.0,
    )


def vectorbt_result(
    *,
    status: str = VectorbtComparisonStatus.COMPLETED.value,
    reason: str = "completed",
    trade_count: int | None = 3,
    turnover_proxy: float | None = 0.25,
    max_drawdown: float | None = 0.03,
) -> VectorbtReplayComparisonResult:
    return VectorbtReplayComparisonResult(
        status=status,
        reason=reason,
        sample_id="mixed-stock-etf-fixture",
        vectorbt_status=status,
        equity_curve=(100000.0, 100250.0, 100180.0),
        total_return=0.0018,
        max_drawdown=max_drawdown,
        trade_count=trade_count,
        turnover_proxy=turnover_proxy,
        warnings=("optional_framework_path",) if status != VectorbtComparisonStatus.COMPLETED.value else (),
        old_chain_reference="p38_mixed_stock_etf_fixture",
    )


def provider_replay_result() -> ProviderReplayResult:
    sample = ProviderMixedUniverseSample(
        sample_source_type=ProviderSampleSourceType.FIXTURE.value,
        sample_source_uri="fixtures/mixed_stock_etf_sample.json",
        evaluation_start="2026-06-01",
        evaluation_end="2026-06-03",
        stock_symbols=("000001.SZ",),
        etf_symbols=("510300.SH",),
        etf_categories=("broad_market",),
        records=(
            {"symbol": "000001.SZ", "date": "2026-06-01", "close": 10.0},
            {"symbol": "510300.SH", "date": "2026-06-01", "close": 4.0},
        ),
        trading_days=("2026-06-01", "2026-06-02", "2026-06-03"),
        evidence_refs=("fixture:provider_sample",),
    )
    validation = ProviderSampleValidationResult(
        ok=True,
        quality_flags=(),
        blockers=(),
        sample=sample,
    )
    return ProviderReplayResult(
        validation=validation,
        trading_day_count=3,
        stock_candidate_count=1,
        etf_candidate_count=1,
        order_intent_count_total=3,
        simulated_fill_count_total=2,
        fill_rate=0.66,
        zero_trade_day_count=1,
        zero_trade_reason_distribution={"no_signal": 1},
        cost_tax_slippage_total=9.5,
        capital_used_average=0.22,
        capital_used_max=0.3,
        net_pnl_after_cost=42.0,
        provider_sample_quality_flags=(),
        etf_impact_notes=("etf_improved_fillability",),
        small_capital_suitability_notes=("small_capital_path_supported",),
    )


def test_builds_old_metrics_from_daily_tradability() -> None:
    old_metrics = old_metrics_from_daily_tradability(daily_metrics(), source_id="daily-fixture")

    assert old_metrics.source_type == OldChainMetricSourceType.DAILY_TRADABILITY.value
    assert old_metrics.source_id == "daily-fixture"
    assert old_metrics.fill_rate == 0.5
    assert old_metrics.turnover_estimate == 0.1
    assert old_metrics.drawdown_estimate == 0.02


def test_builds_old_metrics_from_scenario_result() -> None:
    scenario = ScenarioEvaluationResult(
        scenario_id="mixed-stock-etf",
        scenario_type=EvaluationScenarioType.MIXED_STOCK_ETF.value,
        stock_candidate_count=1,
        etf_candidate_count=1,
        etf_symbols=("510300.SH",),
        daily_report=None,
        metrics=daily_metrics(),
    )

    old_metrics = old_metrics_from_scenario_result(scenario)

    assert old_metrics.source_type == OldChainMetricSourceType.SCENARIO_EVALUATION.value
    assert old_metrics.source_id == "mixed-stock-etf"
    assert old_metrics.simulated_fill_count_total == 2


def test_builds_old_metrics_from_provider_replay() -> None:
    old_metrics = old_metrics_from_provider_replay(provider_replay_result())

    assert old_metrics.source_type == OldChainMetricSourceType.PROVIDER_REPLAY.value
    assert old_metrics.source_id == "fixtures/mixed_stock_etf_sample.json"
    assert old_metrics.fill_rate == 0.66
    assert old_metrics.turnover_estimate is None
    assert old_metrics.drawdown_estimate is None


def test_completed_comparison_produces_advisory_deltas() -> None:
    result = compare_old_chain_to_vectorbt(
        old_metrics_from_daily_tradability(daily_metrics()),
        vectorbt_result(),
    )
    deltas = {delta.label: delta for delta in result.deltas}

    assert result.status == MetricsComparisonStatus.COMPLETED.value
    assert deltas["trade_count_delta"].delta == 1
    assert deltas["turnover_delta"].delta == 0.15
    assert deltas["drawdown_delta"].delta == 0.01
    assert result.replacement_readiness.advisory_status == "ready_for_side_by_side_trials"


def test_framework_missing_is_advisory_not_project_blocking() -> None:
    result = compare_old_chain_to_vectorbt(
        old_metrics_from_daily_tradability(daily_metrics()),
        vectorbt_result(
            status=VectorbtReplayStatus.FRAMEWORK_MISSING.value,
            reason="vectorbt_not_installed",
            trade_count=None,
            turnover_proxy=None,
            max_drawdown=None,
        ),
    )

    assert result.status == MetricsComparisonStatus.VECTORBT_FRAMEWORK_MISSING.value
    assert result.replacement_readiness.advisory_status == "framework_missing"
    assert "install optional replay framework" in result.replacement_readiness.notes


def test_vectorbt_invalid_input_is_reported_without_replacing_old_chain() -> None:
    result = compare_old_chain_to_vectorbt(
        old_metrics_from_daily_tradability(daily_metrics()),
        vectorbt_result(
            status=VectorbtReplayStatus.INVALID_INPUT.value,
            reason="price_length_mismatch",
            trade_count=None,
            turnover_proxy=None,
            max_drawdown=None,
        ),
    )

    assert result.status == MetricsComparisonStatus.VECTORBT_INVALID_INPUT.value
    assert result.reason == "price_length_mismatch"
    assert result.replacement_readiness.advisory_status == "invalid_vectorbt_input"


def test_old_chain_zero_trade_but_vectorbt_traded_is_visible() -> None:
    result = compare_old_chain_to_vectorbt(
        old_metrics_from_daily_tradability(daily_metrics(fill_rate=0.0, fills=0)),
        vectorbt_result(trade_count=2),
    )

    assert result.replacement_readiness.advisory_status == "old_chain_zero_trade_but_vectorbt_traded"
    assert "overblocking" in result.replacement_readiness.notes[0]


def test_vectorbt_no_trade_but_old_chain_traded_is_visible() -> None:
    result = compare_old_chain_to_vectorbt(
        old_metrics_from_daily_tradability(daily_metrics(fills=2)),
        vectorbt_result(trade_count=0),
    )

    assert result.replacement_readiness.advisory_status == "vectorbt_no_trade_but_old_chain_traded"


def test_invalid_old_chain_metrics_do_not_raise() -> None:
    result = compare_old_chain_to_vectorbt(
        OldChainReplayMetrics(
            source_type="daily_tradability",
            source_id="bad-fill-rate",
            fill_rate=1.5,
            simulated_fill_count_total=1,
            zero_trade_day_count=0,
            cost_tax_slippage_total=1.0,
            net_pnl_after_cost=2.0,
            capital_used_average=0.1,
            turnover_estimate=0.1,
            drawdown_estimate=0.0,
        ),
        vectorbt_result(),
    )

    assert result.status == MetricsComparisonStatus.OLD_CHAIN_INVALID_INPUT.value
    assert result.reason == "fill_rate_invalid"
    assert result.old_metrics is None


def test_report_includes_advisory_not_gate_language() -> None:
    report = build_old_chain_vectorbt_metrics_report(
        old_metrics_from_daily_tradability(daily_metrics()),
        vectorbt_result(),
    )

    assert "This is advisory comparison, not an execution gate." in report
    assert "old_fill_rate: 0.5" in report
    assert "vectorbt_trade_count: 3" in report


def test_package_exports_are_available() -> None:
    assert MetricsComparisonStatus.COMPLETED.value == "completed"
    assert OldChainMetricSourceType.PROVIDER_REPLAY.value == "provider_replay"
