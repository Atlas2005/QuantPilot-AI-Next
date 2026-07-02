from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import pytest

from quantpilot_core.data_provider_normalization import (
    NORMALIZED_OHLCV_COLUMNS,
    ProviderKey,
    cross_check_normalized_provider_frames,
    normalize_baostock_history_k_frame,
    normalize_tushare_daily_frame,
    normalized_ohlcv_to_vbt3_signal_frame,
)
from quantpilot_core.vectorbt_integration import provider_signals_to_vectorbt_inputs


def baostock_fixture() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": "2026-01-02",
                "code": "sz.000001",
                "open": "10.00",
                "high": "10.40",
                "low": "9.90",
                "close": "10.20",
                "volume": "1000000",
                "amount": "10200000",
            },
            {
                "date": "2026-01-03",
                "code": "sz.000001",
                "open": "10.20",
                "high": "10.60",
                "low": "10.10",
                "close": "10.50",
                "volume": "1100000",
                "amount": "11400000",
            },
        ]
    )


def tushare_fixture() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "20260102",
                "ts_code": "000001.SZ",
                "open": 10.00,
                "high": 10.40,
                "low": 9.90,
                "close": 10.21,
                "vol": 10000.0,
                "amount": 10200.0,
            },
            {
                "trade_date": "20260106",
                "ts_code": "000001.SZ",
                "open": 10.60,
                "high": 10.80,
                "low": 10.50,
                "close": 10.70,
                "vol": 12000.0,
                "amount": 12840.0,
            },
        ]
    )


def test_baostock_history_k_frame_normalizes_to_common_schema() -> None:
    normalized = normalize_baostock_history_k_frame(baostock_fixture(), adjustment="qfq")

    assert tuple(normalized.columns) == NORMALIZED_OHLCV_COLUMNS
    assert normalized.to_dict("records")[0] == {
        "symbol": "000001.SZ",
        "date": "2026-01-02",
        "open": 10.0,
        "high": 10.4,
        "low": 9.9,
        "close": 10.2,
        "volume": 1_000_000.0,
        "amount": 10_200_000.0,
        "provider": "baostock",
        "adjustment": "qfq",
    }


def test_tushare_daily_frame_normalizes_units_and_schema() -> None:
    normalized = normalize_tushare_daily_frame(tushare_fixture(), adjustment="none")

    assert tuple(normalized.columns) == NORMALIZED_OHLCV_COLUMNS
    assert normalized.iloc[0].to_dict() == {
        "symbol": "000001.SZ",
        "date": "2026-01-02",
        "open": 10.0,
        "high": 10.4,
        "low": 9.9,
        "close": 10.21,
        "volume": 1_000_000.0,
        "amount": 10_200_000.0,
        "provider": "tushare",
        "adjustment": "none",
    }


def test_normalizers_require_in_memory_pandas_frames() -> None:
    with pytest.raises(TypeError, match="pandas DataFrame"):
        normalize_baostock_history_k_frame([{"date": "2026-01-02"}])  # type: ignore[arg-type]


def test_missing_required_columns_are_reported() -> None:
    with pytest.raises(ValueError, match="missing required columns"):
        normalize_tushare_daily_frame(pd.DataFrame({"trade_date": ["20260102"]}))


def test_cross_check_report_is_advisory_and_captures_coverage_and_differences() -> None:
    left = normalize_baostock_history_k_frame(baostock_fixture())
    right = normalize_tushare_daily_frame(tushare_fixture())

    report = cross_check_normalized_provider_frames(left, right)

    assert report.advisory_only is True
    assert report.left_provider == "baostock"
    assert report.right_provider == "tushare"
    assert report.left_rows == 2
    assert report.right_rows == 2
    assert report.common_symbol_dates == 1
    assert report.coverage_ratio == pytest.approx(1 / 3)
    assert report.left_missing_dates == (ProviderKey("000001.SZ", "2026-01-06"),)
    assert report.right_missing_dates == (ProviderKey("000001.SZ", "2026-01-03"),)
    assert len(report.close_differences) == 1
    assert report.close_differences[0].absolute_difference == pytest.approx(0.01)
    assert report.max_close_pct_difference == pytest.approx(0.01 / 10.2)
    assert report.volume_differences == ()


def test_cross_check_reports_duplicate_symbol_date_rows() -> None:
    left = normalize_baostock_history_k_frame(baostock_fixture())
    duplicated = pd.concat([left, left.iloc[[0]]], ignore_index=True)
    right = normalize_tushare_daily_frame(tushare_fixture())

    report = cross_check_normalized_provider_frames(duplicated, right)

    assert report.left_rows == 3
    assert report.left_unique_symbol_dates == 2
    assert report.left_duplicate_symbol_dates == (ProviderKey("000001.SZ", "2026-01-02"),)
    assert report.right_duplicate_symbol_dates == ()


def test_volume_difference_is_reported_separately_from_close_difference() -> None:
    left = normalize_baostock_history_k_frame(baostock_fixture())
    right = normalize_tushare_daily_frame(tushare_fixture())
    right.loc[right["date"] == "2026-01-02", "volume"] = 1_100_000.0

    report = cross_check_normalized_provider_frames(left, right)

    assert len(report.volume_differences) == 1
    assert report.volume_differences[0].field_name == "volume"
    assert report.volume_differences[0].pct_difference == pytest.approx(0.1)
    assert math.isfinite(report.volume_differences[0].absolute_difference)


def test_normalized_output_can_be_shaped_for_vbt3_signal_bridge() -> None:
    normalized = normalize_baostock_history_k_frame(baostock_fixture())
    signal_frame = normalized_ohlcv_to_vbt3_signal_frame(normalized)
    signal_frame.loc[signal_frame.index[0], "entry_signal"] = True
    signal_frame.loc[signal_frame.index[-1], "exit_signal"] = True

    (converted,) = provider_signals_to_vectorbt_inputs(signal_frame)

    assert tuple(signal_frame.columns) == ("date", "symbol", "close", "entry_signal", "exit_signal")
    assert converted.symbol == "000001.SZ"
    assert converted.close.tolist() == [10.2, 10.5]
    assert converted.entries.tolist() == [True, False]
    assert converted.exits.tolist() == [False, True]


def test_module_has_no_fetch_download_or_forbidden_runtime_terms() -> None:
    package_root = Path(__file__).parents[2] / "src" / "quantpilot_core" / "data_provider_normalization"
    source = "\n".join(path.read_text() for path in package_root.glob("*.py"))

    forbidden_terms = (
        "requests",
        "urllib",
        "http://",
        "https://",
        "socket",
        "fetch",
        "download",
        "broker",
        "mod_ctp",
        "mod-vnpy",
        "vnpy",
        "deepseek",
        "multi_agent",
        "USE_LEGACY_ENGINE",
    )
    assert all(term not in source.lower() for term in forbidden_terms)

