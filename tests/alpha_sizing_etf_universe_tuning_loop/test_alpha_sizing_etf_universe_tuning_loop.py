from __future__ import annotations

import sys
from pathlib import Path

import pytest

from quantpilot_core.alpha_sizing_etf_universe_tuning_loop import (
    AlphaSignalQuality,
    EtfCategory,
    InstrumentType,
    TradableInstrument,
    build_alpha_sizing_etf_universe_report,
    build_instrument_rule_profile,
    recommend_sizing_candidates,
    select_tradable_universe,
    tune_alpha_sizing_candidates,
)
from quantpilot_core.daily_paper_trading_loop_tradability_metrics import (
    DailyTradabilityMetrics,
)


def stock_candidate(symbol: str = "000001.SZ") -> TradableInstrument:
    return TradableInstrument(
        symbol=symbol,
        name="Ping An Bank",
        instrument_type=InstrumentType.STOCK.value,
        price=12.0,
        expected_alpha=0.08,
        average_daily_value=100_000_000,
        evidence_refs=("evidence://p37/stock",),
    )


def etf_candidate(
    symbol: str = "510300.SH",
    category: str = EtfCategory.EQUITY_ETF.value,
    *,
    t0_allowed_declared: bool = False,
) -> TradableInstrument:
    return TradableInstrument(
        symbol=symbol,
        name="CSI 300 ETF",
        instrument_type=InstrumentType.ETF.value,
        etf_category=category,
        t0_allowed_declared=t0_allowed_declared,
        price=2.0,
        expected_alpha=0.09,
        average_daily_value=500_000_000,
        evidence_refs=("evidence://p37/etf",),
    )


def daily_metrics_with_odd_lot_zero_trade() -> DailyTradabilityMetrics:
    return DailyTradabilityMetrics(
        trading_day_count=3,
        raw_signal_count_total=4,
        order_intent_count_total=4,
        simulated_fill_count_total=2,
        fill_rate=0.5,
        zero_trade_day_count=1,
        zero_trade_reason_distribution={"odd_lot": 1},
        cost_tax_slippage_total=12.1345,
        gross_pnl_estimate=30.9045,
        net_pnl_after_cost=18.77,
        capital_used_average=0.003335,
        capital_used_max=0.010005,
        turnover_estimate=0.0209,
        drawdown_estimate=0.0,
        suspected_overblocking_days=0,
        safety_barrier_percent=140.0,
    )


def alpha_quality() -> dict[str, AlphaSignalQuality]:
    return {
        "000001.SZ": AlphaSignalQuality("000001.SZ", 0.70, 0.58, 0.05, 0.025, 0.68),
        "510300.SH": AlphaSignalQuality("510300.SH", 0.82, 0.64, 0.08, 0.018, 0.74),
    }


def test_stock_candidate_accepted() -> None:
    selection = select_tradable_universe((stock_candidate(),))

    assert selection.stock_candidate_count == 1
    assert selection.etf_candidate_count == 0
    assert selection.rejected == {}


def test_etf_candidate_accepted() -> None:
    selection = select_tradable_universe((etf_candidate(),))

    assert selection.stock_candidate_count == 0
    assert selection.etf_candidate_count == 1
    assert selection.etf_categories_present == (EtfCategory.EQUITY_ETF.value,)


def test_etf_with_missing_category_rejected() -> None:
    missing = TradableInstrument(
        symbol="510050.SH",
        name="Missing Category ETF",
        instrument_type=InstrumentType.ETF.value,
        price=2.5,
        expected_alpha=0.05,
    )

    selection = select_tradable_universe((missing,))

    assert selection.accepted == ()
    assert selection.rejected["510050.SH"] == ("etf_category_missing",)


def test_etf_cannot_be_silently_treated_as_stock() -> None:
    missing = TradableInstrument(
        symbol="510050.SH",
        name="Missing Category ETF",
        instrument_type=InstrumentType.ETF.value,
        price=2.5,
        expected_alpha=0.05,
    )

    with pytest.raises(ValueError, match="etf_category_missing"):
        build_instrument_rule_profile(missing)


def test_equity_etf_uses_t_plus_one() -> None:
    profile = build_instrument_rule_profile(etf_candidate())

    assert profile.settlement == "T+1"


@pytest.mark.parametrize(
    "category",
    (
        EtfCategory.BOND_ETF.value,
        EtfCategory.GOLD_ETF.value,
        EtfCategory.CROSS_BORDER_ETF.value,
        EtfCategory.MONEY_MARKET_ETF.value,
    ),
)
def test_declared_t0_etf_categories_use_t_zero(category: str) -> None:
    profile = build_instrument_rule_profile(
        etf_candidate(symbol=f"{category}.ETF", category=category, t0_allowed_declared=True)
    )

    assert profile.settlement == "T+0"


def test_etf_min_trade_unit_and_tick_size() -> None:
    profile = build_instrument_rule_profile(etf_candidate())

    assert profile.min_trade_unit == 100
    assert profile.min_tick == 0.001


def test_etf_fee_model_is_separate_from_stock_stamp_duty() -> None:
    stock_profile = build_instrument_rule_profile(stock_candidate())
    etf_profile = build_instrument_rule_profile(etf_candidate())

    assert stock_profile.stamp_duty_rate > 0
    assert etf_profile.stamp_duty_rate == 0
    assert stock_profile.fee_model != etf_profile.fee_model


def test_universe_reports_stock_and_etf_counts_separately() -> None:
    selection = select_tradable_universe((stock_candidate(), etf_candidate()))

    assert selection.stock_candidate_count == 1
    assert selection.etf_candidate_count == 1
    assert selection.small_capital_priority_symbols == ("510300.SH",)


def test_small_capital_recommendation_can_prefer_etf() -> None:
    report = build_alpha_sizing_etf_universe_report(
        (stock_candidate(), etf_candidate()),
        alpha_quality(),
        available_cash=50_000.0,
        daily_metrics=daily_metrics_with_odd_lot_zero_trade(),
    )

    assert report.includes_stocks_and_etfs is True
    assert report.etfs_improve_small_capital_tradability is True
    assert any(
        decision.recommended_action == "prefer_etf_for_small_capital"
        for decision in report.tuning_decisions
    )


def test_sizing_reduces_zero_trade_risk() -> None:
    sizing = recommend_sizing_candidates(
        (stock_candidate(), etf_candidate()),
        available_cash=50_000.0,
        daily_metrics=daily_metrics_with_odd_lot_zero_trade(),
    )

    assert all(candidate.recommended_quantity % 100 == 0 for candidate in sizing)
    assert all(candidate.zero_trade_risk_reduced for candidate in sizing)


def test_cost_drag_is_considered() -> None:
    sizing = recommend_sizing_candidates(
        (stock_candidate(), etf_candidate()),
        available_cash=50_000.0,
        daily_metrics=daily_metrics_with_odd_lot_zero_trade(),
    )
    decisions = tune_alpha_sizing_candidates(sizing, alpha_quality())
    by_symbol = {decision.symbol: decision for decision in decisions}

    assert by_symbol["510300.SH"].cost_after_fill_score > by_symbol["000001.SZ"].cost_after_fill_score


def test_safety_barrier_remains_at_or_below_140() -> None:
    report = build_alpha_sizing_etf_universe_report(
        (stock_candidate(), etf_candidate()),
        alpha_quality(),
        available_cash=50_000.0,
        daily_metrics=daily_metrics_with_odd_lot_zero_trade(),
        safety_barrier_percent=185.0,
    )

    assert report.safety_barrier_percent <= 140.0


def test_deterministic_report_ordering() -> None:
    report = build_alpha_sizing_etf_universe_report(
        (etf_candidate(), stock_candidate()),
        alpha_quality(),
        available_cash=50_000.0,
        daily_metrics=daily_metrics_with_odd_lot_zero_trade(),
    )

    assert tuple(item.symbol for item in report.universe.accepted) == ("510300.SH", "000001.SZ")
    assert tuple(item.symbol for item in report.sizing_candidates) == ("510300.SH", "000001.SZ")
    assert tuple(item.symbol for item in report.tuning_decisions) == ("510300.SH", "000001.SZ")


def test_unknown_instrument_type_rejected() -> None:
    unknown = TradableInstrument(
        symbol="UNKNOWN",
        name="Unknown",
        instrument_type="future",
        price=10.0,
        expected_alpha=0.1,
    )

    selection = select_tradable_universe((unknown,))

    assert selection.rejected["UNKNOWN"] == ("unknown_instrument_type",)


def test_no_forbidden_runtime_behavior() -> None:
    package_root = Path("src/quantpilot_core/alpha_sizing_etf_universe_tuning_loop")
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
