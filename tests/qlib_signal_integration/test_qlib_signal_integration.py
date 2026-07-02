from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from quantpilot_core.qlib_signal_integration import (
    qlib_signal_artifact_to_vbt3_signal_frame,
)


def normalized_ohlcv_fixture() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for date_value, stock_close, etf_close in (
        ("2026-01-02", 10.0, 2.0),
        ("2026-01-05", 10.2, 2.1),
        ("2026-01-06", 10.4, 2.2),
    ):
        rows.append(
            {
                "symbol": "000001.SZ",
                "date": date_value,
                "open": stock_close,
                "high": stock_close,
                "low": stock_close,
                "close": stock_close,
                "volume": 1_000_000.0,
                "amount": 10_000_000.0,
                "provider": "baostock",
                "adjustment": "qfq",
            }
        )
        rows.append(
            {
                "symbol": "510300.SH",
                "date": date_value,
                "open": etf_close,
                "high": etf_close,
                "low": etf_close,
                "close": etf_close,
                "volume": 5_000_000.0,
                "amount": 10_000_000.0,
                "provider": "baostock",
                "adjustment": "qfq",
            }
        )
    return pd.DataFrame(rows)


def qlib_prediction_fixture() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"datetime": "2026-01-02", "instrument": "000001.SZ", "score": 0.9},
            {"datetime": "2026-01-02", "instrument": "510300.SH", "score": 0.2},
            {"datetime": "2026-01-05", "instrument": "000001.SZ", "score": 0.1},
            {"datetime": "2026-01-05", "instrument": "510300.SH", "score": 0.8},
            {"datetime": "2026-01-06", "instrument": "000001.SZ", "score": 0.7},
            {"datetime": "2026-01-06", "instrument": "510300.SH", "score": 0.3},
        ]
    )


def test_top_n_entries_join_to_normalized_close_and_shape_fixed_holding_exits() -> None:
    frame = qlib_signal_artifact_to_vbt3_signal_frame(
        qlib_prediction_fixture(),
        normalized_ohlcv_fixture(),
        top_n=1,
        holding_period=1,
    )

    assert tuple(frame.columns) == ("date", "symbol", "close", "entry_signal", "exit_signal")
    stock = frame.query("symbol == '000001.SZ'").reset_index(drop=True)
    etf = frame.query("symbol == '510300.SH'").reset_index(drop=True)
    assert stock["close"].tolist() == [10.0, 10.2, 10.4]
    assert stock["entry_signal"].tolist() == [True, False, True]
    assert stock["exit_signal"].tolist() == [False, True, False]
    assert etf["entry_signal"].tolist() == [False, True, False]
    assert etf["exit_signal"].tolist() == [False, False, True]


def test_score_threshold_uses_configurable_artifact_columns() -> None:
    predictions = qlib_prediction_fixture().rename(
        columns={"datetime": "date", "instrument": "symbol", "score": "pred"}
    )

    frame = qlib_signal_artifact_to_vbt3_signal_frame(
        predictions,
        normalized_ohlcv_fixture(),
        date_col="date",
        symbol_col="symbol",
        score_col="pred",
        score_threshold=0.75,
    )

    selected = frame[frame["entry_signal"]]
    assert selected[["date", "symbol"]].to_dict("records") == [
        {"date": "2026-01-02", "symbol": "000001.SZ"},
        {"date": "2026-01-05", "symbol": "510300.SH"},
    ]
    assert frame["exit_signal"].tolist() == [False] * len(frame)


def test_explicit_exit_column_is_preserved_without_holding_period_logic() -> None:
    predictions = qlib_prediction_fixture()
    predictions["exit_now"] = predictions["datetime"].eq("2026-01-06")

    frame = qlib_signal_artifact_to_vbt3_signal_frame(
        predictions,
        normalized_ohlcv_fixture(),
        top_n=1,
        holding_period=1,
        exit_col="exit_now",
    )

    assert frame.query("date == '2026-01-06'")["exit_signal"].tolist() == [True, True]
    assert frame.query("date == '2026-01-05'")["exit_signal"].tolist() == [False, False]


def test_missing_provider_close_is_an_ordinary_input_error() -> None:
    predictions = pd.DataFrame(
        [{"datetime": "2026-01-02", "instrument": "600000.SH", "score": 1.0}]
    )

    with pytest.raises(ValueError, match="missing normalized OHLCV close"):
        qlib_signal_artifact_to_vbt3_signal_frame(
            predictions,
            normalized_ohlcv_fixture(),
            top_n=1,
        )


def test_module_has_no_fetch_training_qrun_or_forbidden_runtime_terms() -> None:
    package_root = Path(__file__).parents[2] / "src" / "quantpilot_core" / "qlib_signal_integration"
    source = "\n".join(path.read_text() for path in package_root.glob("*.py")).lower()

    forbidden_terms = (
        "requests",
        "urllib",
        "http://",
        "https://",
        "socket",
        "fetch",
        "download",
        "train",
        "qrun",
        "broker",
        "mod_ctp",
        "mod-vnpy",
        "vnpy",
        "deepseek",
        "multi_agent",
        "use_legacy_engine",
        "profitability",
        "production ready",
    )
    assert all(term not in source for term in forbidden_terms)
