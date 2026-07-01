from __future__ import annotations

import importlib.util

from quantpilot_core.gate_pruning_tradability_fill_loop import (
    TradeSide,
    TradeSignalCandidate,
)
from quantpilot_core.vectorbt_replay_adapter import (
    VectorbtReplayInput,
    VectorbtReplayResult,
    VectorbtReplayStatus,
)
from quantpilot_core.vectorbt_replay_comparison import (
    SignalReplaySample,
    VectorbtComparisonStatus,
    build_vectorbt_signal_replay_comparison_report,
    run_vectorbt_signal_replay_comparison,
    signal_sample_to_vectorbt_input,
)


def signal(
    signal_id: str,
    symbol: str,
    side: str,
    price: float,
) -> TradeSignalCandidate:
    return TradeSignalCandidate(
        signal_id=signal_id,
        symbol=symbol,
        side=side,
        quantity=100,
        reference_price=price,
        limit_price=price,
        expected_return=0.01,
        confidence=0.8,
        evidence_refs=("fixture:signal",),
    )


def sample() -> SignalReplaySample:
    return SignalReplaySample(
        sample_id="mixed-stock-etf-r3b",
        symbols=("000001.SZ", "510300.SH"),
        dates=("2026-01-02", "2026-01-05", "2026-01-06"),
        prices_by_symbol={
            "000001.SZ": (10.0, 10.2, 10.3),
            "510300.SH": (2.0, 2.02, 2.04),
        },
        signals_by_date={
            "2026-01-02": (
                signal("stock-buy-day1", "000001.SZ", TradeSide.BUY.value, 10.0),
                signal("etf-buy-day1", "510300.SH", TradeSide.BUY.value, 2.0),
            ),
            "2026-01-05": (
                signal("etf-buy-day2", "510300.SH", TradeSide.BUY.value, 2.02),
            ),
            "2026-01-06": (
                signal("etf-sell-day3", "510300.SH", TradeSide.SELL.value, 2.04),
            ),
        },
    )


def test_converter_builds_entries_and_exits_from_buy_sell_signals() -> None:
    converted = signal_sample_to_vectorbt_input(sample())

    assert converted.prices == {
        "000001.SZ": (10.0, 10.2, 10.3),
        "510300.SH": (2.0, 2.02, 2.04),
    }
    assert converted.entries["000001.SZ"] == (True, False, False)
    assert converted.exits["000001.SZ"] == (False, False, False)
    assert converted.entries["510300.SH"] == (True, True, False)
    assert converted.exits["510300.SH"] == (False, False, True)


def test_invalid_sample_returns_invalid_input() -> None:
    invalid = SignalReplaySample(
        sample_id="bad",
        symbols=("000001.SZ",),
        dates=("2026-01-02", "2026-01-03"),
        prices_by_symbol={"000001.SZ": (10.0,)},
        signals_by_date={},
    )

    result = run_vectorbt_signal_replay_comparison(invalid)

    assert result.status == VectorbtComparisonStatus.INVALID_INPUT.value
    assert result.reason == "price_length_mismatch:000001.SZ"


def test_missing_vectorbt_propagates_as_framework_missing() -> None:
    def missing_runner(_input_data: VectorbtReplayInput) -> VectorbtReplayResult:
        return VectorbtReplayResult(
            status=VectorbtReplayStatus.FRAMEWORK_MISSING.value,
            reason="vectorbt_not_installed",
            equity_curve=(),
            total_return=None,
            max_drawdown=None,
            trade_count=None,
            turnover_proxy=None,
            warnings=("optional replay framework missing",),
        )

    result = run_vectorbt_signal_replay_comparison(sample(), replay_runner=missing_runner)

    assert result.status == VectorbtComparisonStatus.FRAMEWORK_MISSING.value
    assert result.vectorbt_status == VectorbtReplayStatus.FRAMEWORK_MISSING.value
    assert result.reason == "vectorbt_not_installed"
    assert result.warnings == ("optional replay framework missing",)


def test_completed_comparison_returns_metrics_when_vectorbt_installed() -> None:
    if importlib.util.find_spec("vectorbt") is None:
        result = run_vectorbt_signal_replay_comparison(sample())
        assert result.status == VectorbtComparisonStatus.FRAMEWORK_MISSING.value
        return

    result = run_vectorbt_signal_replay_comparison(sample())

    assert result.status == VectorbtComparisonStatus.COMPLETED.value
    assert result.equity_curve
    assert result.total_return is not None
    assert result.max_drawdown is not None


def test_package_exports_are_correct() -> None:
    report = build_vectorbt_signal_replay_comparison_report(
        sample(),
        old_chain_reference="paper_replay_baseline",
    )

    assert "R3B connects QuantPilot signal fixtures to vectorbt" in report
    assert "old_chain_reference: paper_replay_baseline" in report
