from pathlib import Path

from quantpilot_core.gate_pruning_tradability_fill_loop import TradeSide
from quantpilot_core.provider_vectorbt_replay import (
    ProviderVectorbtReplayStatus,
    provider_replay_input_to_signal_sample,
    replay_provider_mixed_etf_sample_with_vectorbt,
)
from quantpilot_core.real_provider_mixed_etf_paper_replay import (
    ProviderSampleSourceType,
    RealProviderReplayInput,
)
from quantpilot_core.vectorbt_replay_adapter import VectorbtReplayResult, VectorbtReplayStatus


PACKAGE_ROOT = Path("src/quantpilot_core/provider_vectorbt_replay")


def sample_records() -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    for trade_date, stock_close, etf_close in (
        ("2026-01-02", 10.0, 2.0),
        ("2026-01-05", 10.2, 2.02),
        ("2026-01-06", 10.3, 2.04),
    ):
        rows.append(
            {
                "symbol": "000001.SZ",
                "trade_date": trade_date,
                "instrument_type": "stock",
                "open": stock_close,
                "high": round(stock_close * 1.02, 4),
                "low": round(stock_close * 0.98, 4),
                "close": stock_close,
                "volume": 1_000_000,
            }
        )
        rows.append(
            {
                "symbol": "510300.SH",
                "trade_date": trade_date,
                "instrument_type": "etf",
                "etf_category": "equity_etf",
                "open": etf_close,
                "high": round(etf_close * 1.02, 4),
                "low": round(etf_close * 0.98, 4),
                "close": etf_close,
                "volume": 5_000_000,
            }
        )
    return tuple(rows)


def valid_input(records: tuple[dict[str, object], ...] | None = None) -> RealProviderReplayInput:
    return RealProviderReplayInput(
        sample_source_type=ProviderSampleSourceType.FIXTURE.value,
        sample_source_uri="fixtures/r3d/provider_mixed_sample",
        evaluation_start="2026-01-02",
        evaluation_end="2026-01-06",
        initial_cash=100_000.0,
        records=records or sample_records(),
        evidence_refs=("evidence://r3d/sample",),
    )


def missing_runner(_input_data) -> VectorbtReplayResult:
    return VectorbtReplayResult(
        status=VectorbtReplayStatus.FRAMEWORK_MISSING.value,
        reason="vectorbt_not_installed",
        equity_curve=(),
        total_return=None,
        max_drawdown=None,
        trade_count=None,
        turnover_proxy=None,
        warnings=("install optional replay extra to enable vectorbt replay",),
    )


def completed_runner(_input_data) -> VectorbtReplayResult:
    return VectorbtReplayResult(
        status=VectorbtReplayStatus.COMPLETED.value,
        reason="completed",
        equity_curve=(100_000.0, 100_300.0, 100_250.0),
        total_return=0.0025,
        max_drawdown=0.0005,
        trade_count=3,
        turnover_proxy=0.5,
        warnings=(),
    )


def test_valid_provider_sample_converts_to_signal_sample_with_aligned_closes() -> None:
    sample = provider_replay_input_to_signal_sample(valid_input())

    assert sample.sample_id == "fixtures/r3d/provider_mixed_sample"
    assert sample.symbols == ("000001.SZ", "510300.SH")
    assert sample.dates == ("2026-01-02", "2026-01-05", "2026-01-06")
    assert sample.prices_by_symbol["000001.SZ"] == (10.0, 10.2, 10.3)
    assert sample.prices_by_symbol["510300.SH"] == (2.0, 2.02, 2.04)
    assert tuple(signal.side for signal in sample.signals_by_date["2026-01-02"]) == (
        TradeSide.BUY.value,
        TradeSide.BUY.value,
    )
    day2_etf_signal = sample.signals_by_date["2026-01-05"][0]
    day3_etf_signal = sample.signals_by_date["2026-01-06"][0]
    assert day2_etf_signal.quantity == 500
    assert day2_etf_signal.reference_price == 2.02
    assert day2_etf_signal.limit_price == 2.02
    assert day3_etf_signal.side == TradeSide.SELL.value
    assert day3_etf_signal.reference_price == 2.04
    assert day3_etf_signal.limit_price == 2.04


def test_primary_vectorbt_replay_returns_framework_missing_cleanly() -> None:
    result = replay_provider_mixed_etf_sample_with_vectorbt(
        valid_input(),
        replay_runner=missing_runner,
    )

    assert result.status == ProviderVectorbtReplayStatus.VECTORBT_FRAMEWORK_MISSING.value
    assert result.engine == "vectorbt"
    assert result.provider_validation.ok is True
    assert result.vectorbt_replay_result is not None
    assert result.trade_count is None


def test_primary_vectorbt_replay_completed_copies_metrics() -> None:
    result = replay_provider_mixed_etf_sample_with_vectorbt(
        valid_input(),
        replay_runner=completed_runner,
    )

    assert result.status == ProviderVectorbtReplayStatus.COMPLETED.value
    assert result.total_return == 0.0025
    assert result.max_drawdown == 0.0005
    assert result.trade_count == 3
    assert result.turnover_proxy == 0.5
    assert result.equity_curve_points == 3
    assert result.evidence_refs == ("evidence://r3d/sample",)


def test_invalid_provider_sample_returns_invalid_without_crashing() -> None:
    rows = tuple(row for row in sample_records() if row["instrument_type"] == "stock")

    result = replay_provider_mixed_etf_sample_with_vectorbt(
        valid_input(rows),
        replay_runner=completed_runner,
    )

    assert result.status == ProviderVectorbtReplayStatus.PROVIDER_SAMPLE_INVALID.value
    assert "etf_sample_missing" in result.reason
    assert result.vectorbt_replay_result is None
    assert result.equity_curve_points == 0


def test_new_primary_path_does_not_call_old_provider_replay(monkeypatch) -> None:
    def forbidden_old_replay(_replay_input):
        raise AssertionError("old replay path should not be called")

    monkeypatch.setattr(
        "quantpilot_core.real_provider_mixed_etf_paper_replay.replay_provider_mixed_etf_sample",
        forbidden_old_replay,
    )

    result = replay_provider_mixed_etf_sample_with_vectorbt(
        valid_input(),
        replay_runner=completed_runner,
    )

    assert result.status == ProviderVectorbtReplayStatus.COMPLETED.value


def test_package_has_no_hard_imports_for_optional_framework_stack() -> None:
    forbidden = (
        "import vectorbt",
        "from vectorbt",
        "import pandas",
        "from pandas",
        "import numpy",
        "from numpy",
    )
    lines = tuple(
        line.strip()
        for path in PACKAGE_ROOT.glob("*.py")
        for line in path.read_text(encoding="utf-8").lower().splitlines()
    )

    for pattern in forbidden:
        assert pattern not in lines


def test_package_exports_are_correct() -> None:
    assert ProviderVectorbtReplayStatus.COMPLETED.value == "completed"
    assert callable(provider_replay_input_to_signal_sample)
    assert callable(replay_provider_mixed_etf_sample_with_vectorbt)
