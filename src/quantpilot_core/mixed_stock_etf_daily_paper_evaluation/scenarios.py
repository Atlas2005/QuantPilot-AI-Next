"""Deterministic P38 stock-only and mixed stock/ETF scenarios."""

from __future__ import annotations

from quantpilot_core.alpha_sizing_etf_universe_tuning_loop import (
    EtfCategory,
    InstrumentType,
    TradableInstrument,
)
from quantpilot_core.daily_paper_trading_loop_tradability_metrics import (
    DailyPaperTradingInput,
)
from quantpilot_core.gate_pruning_tradability_fill_loop import (
    TradeSide,
    TradeSignalCandidate,
)
from quantpilot_core.mixed_stock_etf_daily_paper_evaluation.contracts import (
    DailyPaperEvaluationScenario,
    EvaluationScenarioType,
)


TRADING_DAYS = ("2026-01-02", "2026-01-05", "2026-01-06")
INITIAL_CAPITAL = 100_000.0
PRICE_LIMITS = {
    day: {
        "000001.SZ": (9.0, 11.5),
        "600000.SH": (18.0, 22.0),
        "510300.SH": (1.8, 2.2),
    }
    for day in TRADING_DAYS
}


def create_stock_only_scenario() -> DailyPaperEvaluationScenario:
    """Create deterministic stock-only daily paper evaluation scenario."""

    instruments = (
        TradableInstrument(
            symbol="000001.SZ",
            name="Ping An Bank",
            instrument_type=InstrumentType.STOCK.value,
            price=10.0,
            expected_alpha=0.05,
            average_daily_value=100_000_000,
            evidence_refs=("evidence://p38/stock/000001",),
        ),
        TradableInstrument(
            symbol="600000.SH",
            name="Shanghai Pudong Development Bank",
            instrument_type=InstrumentType.STOCK.value,
            price=20.0,
            expected_alpha=0.03,
            average_daily_value=80_000_000,
            evidence_refs=("evidence://p38/stock/600000",),
        ),
    )
    paper_input = DailyPaperTradingInput(
        trading_days=TRADING_DAYS,
        signals_by_day={
            "2026-01-02": (
                _signal("stock-buy-day1", "000001.SZ", TradeSide.BUY.value, 100, 10.0, 0.01),
            ),
            "2026-01-05": (
                _signal("stock-odd-lot-day2", "000001.SZ", TradeSide.BUY.value, 50, 10.2, 0.01),
            ),
            "2026-01-06": (
                _signal("stock-sell-blocked-day3", "600000.SH", TradeSide.SELL.value, 100, 20.0, 0.01),
            ),
        },
        initial_cash=INITIAL_CAPITAL,
        initial_positions={"000001.SZ": 300, "600000.SH": 0},
        initial_sellable_positions={"000001.SZ": 300, "600000.SH": 0},
        price_limits_by_day=PRICE_LIMITS,
        suspended_symbols_by_day={day: () for day in TRADING_DAYS},
        commission_rate=0.0003,
        min_commission=5.0,
        stamp_duty_rate=0.001,
        slippage_bps=5.0,
        safety_barrier_percent=140.0,
        evidence_refs=("evidence://p38/scenario/stock-only",),
    )
    return DailyPaperEvaluationScenario(
        scenario_id="p38-stock-only",
        scenario_type=EvaluationScenarioType.STOCK_ONLY.value,
        instruments=instruments,
        paper_input=paper_input,
        sizing_assumption="stock_100_share_lot_with_blocked_odd_lot_probe",
        evidence_refs=("evidence://p38/scenario/stock-only",),
    )


def create_mixed_stock_etf_scenario() -> DailyPaperEvaluationScenario:
    """Create deterministic mixed stock plus ETF daily paper scenario."""

    instruments = (
        TradableInstrument(
            symbol="000001.SZ",
            name="Ping An Bank",
            instrument_type=InstrumentType.STOCK.value,
            price=10.0,
            expected_alpha=0.05,
            average_daily_value=100_000_000,
            evidence_refs=("evidence://p38/stock/000001",),
        ),
        TradableInstrument(
            symbol="510300.SH",
            name="CSI 300 ETF",
            instrument_type=InstrumentType.ETF.value,
            etf_category=EtfCategory.EQUITY_ETF.value,
            price=2.0,
            expected_alpha=0.07,
            average_daily_value=500_000_000,
            evidence_refs=("evidence://p38/etf/510300",),
        ),
    )
    paper_input = DailyPaperTradingInput(
        trading_days=TRADING_DAYS,
        signals_by_day={
            "2026-01-02": (
                _signal("mixed-stock-buy-day1", "000001.SZ", TradeSide.BUY.value, 100, 10.0, 0.01),
                _signal("mixed-etf-buy-day1", "510300.SH", TradeSide.BUY.value, 500, 2.0, 0.012),
            ),
            "2026-01-05": (
                _signal("mixed-etf-buy-day2", "510300.SH", TradeSide.BUY.value, 500, 2.02, 0.012),
            ),
            "2026-01-06": (
                _signal("mixed-etf-sell-day3", "510300.SH", TradeSide.SELL.value, 500, 2.04, 0.008),
            ),
        },
        initial_cash=INITIAL_CAPITAL,
        initial_positions={"000001.SZ": 300, "600000.SH": 100, "510300.SH": 500},
        initial_sellable_positions={"000001.SZ": 300, "600000.SH": 0, "510300.SH": 500},
        price_limits_by_day=PRICE_LIMITS,
        suspended_symbols_by_day={day: () for day in TRADING_DAYS},
        commission_rate=0.0001,
        min_commission=1.0,
        stamp_duty_rate=0.0,
        slippage_bps=3.0,
        safety_barrier_percent=140.0,
        evidence_refs=("evidence://p38/scenario/mixed-stock-etf",),
    )
    return DailyPaperEvaluationScenario(
        scenario_id="p38-mixed-stock-etf",
        scenario_type=EvaluationScenarioType.MIXED_STOCK_ETF.value,
        instruments=instruments,
        paper_input=paper_input,
        sizing_assumption="mixed_stock_etf_lower_cost_valid_lot_sizing",
        evidence_refs=("evidence://p38/scenario/mixed-stock-etf",),
    )


def create_default_scenarios() -> tuple[DailyPaperEvaluationScenario, DailyPaperEvaluationScenario]:
    """Return stock-only and mixed scenarios in deterministic comparison order."""

    return (create_stock_only_scenario(), create_mixed_stock_etf_scenario())


def _signal(
    signal_id: str,
    symbol: str,
    side: str,
    quantity: int,
    limit_price: float,
    expected_return: float,
) -> TradeSignalCandidate:
    return TradeSignalCandidate(
        signal_id=signal_id,
        symbol=symbol,
        side=side,
        quantity=quantity,
        reference_price=limit_price,
        limit_price=limit_price,
        expected_return=expected_return,
        confidence=0.68,
        evidence_refs=(f"evidence://p38/signal/{signal_id}",),
    )
