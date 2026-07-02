"""In-memory BaoStock/Tushare daily bar normalization."""

from __future__ import annotations

from typing import Any

import pandas as pd

from quantpilot_core.data_provider_normalization.contracts import (
    NORMALIZED_OHLCV_COLUMNS,
)


BAOSTOCK_REQUIRED_COLUMNS = ("date", "open", "high", "low", "close", "volume")
TUSHARE_REQUIRED_COLUMNS = ("trade_date", "open", "high", "low", "close", "vol")


def normalize_baostock_history_k_frame(
    frame: pd.DataFrame,
    *,
    adjustment: str = "none",
    fallback_symbol: str | None = None,
) -> pd.DataFrame:
    """Normalize BaoStock-style historical K data already loaded in memory."""

    source = _require_frame(frame, "BaoStock")
    _require_columns(source, BAOSTOCK_REQUIRED_COLUMNS, "BaoStock")
    symbols = _symbol_series(source, primary_col="code", fallback_symbol=fallback_symbol)
    normalized = pd.DataFrame(
        {
            "symbol": symbols.map(canonicalize_a_share_symbol),
            "date": _date_series(source["date"]),
            "open": _numeric_series(source["open"], "open"),
            "high": _numeric_series(source["high"], "high"),
            "low": _numeric_series(source["low"], "low"),
            "close": _numeric_series(source["close"], "close"),
            "volume": _numeric_series(source["volume"], "volume"),
            "amount": _optional_numeric_series(source, "amount"),
            "provider": "baostock",
            "adjustment": str(adjustment),
        }
    )
    return _ordered_normalized_frame(normalized)


def normalize_tushare_daily_frame(
    frame: pd.DataFrame,
    *,
    adjustment: str = "none",
    fallback_symbol: str | None = None,
    scale_volume_from_hands: bool = True,
    scale_amount_from_thousand_cny: bool = True,
) -> pd.DataFrame:
    """Normalize Tushare-style daily data already loaded in memory."""

    source = _require_frame(frame, "Tushare")
    _require_columns(source, TUSHARE_REQUIRED_COLUMNS, "Tushare")
    symbols = _symbol_series(source, primary_col="ts_code", fallback_symbol=fallback_symbol)
    volume = _numeric_series(source["vol"], "vol")
    amount = _optional_numeric_series(source, "amount")
    if scale_volume_from_hands:
        volume = volume * 100.0
    if scale_amount_from_thousand_cny:
        amount = amount * 1000.0
    normalized = pd.DataFrame(
        {
            "symbol": symbols.map(canonicalize_a_share_symbol),
            "date": _date_series(source["trade_date"]),
            "open": _numeric_series(source["open"], "open"),
            "high": _numeric_series(source["high"], "high"),
            "low": _numeric_series(source["low"], "low"),
            "close": _numeric_series(source["close"], "close"),
            "volume": volume,
            "amount": amount,
            "provider": "tushare",
            "adjustment": str(adjustment),
        }
    )
    return _ordered_normalized_frame(normalized)


def normalized_ohlcv_to_vbt3_signal_frame(
    frame: pd.DataFrame,
    *,
    entry_signal: bool = False,
    exit_signal: bool = False,
) -> pd.DataFrame:
    """Create the narrow VBT3 signal-frame shape without strategy logic."""

    normalized = _require_normalized_frame(frame)
    return pd.DataFrame(
        {
            "date": normalized["date"],
            "symbol": normalized["symbol"],
            "close": normalized["close"],
            "entry_signal": bool(entry_signal),
            "exit_signal": bool(exit_signal),
        }
    )


def canonicalize_a_share_symbol(symbol: Any) -> str:
    """Normalize common A-share provider symbol forms to code.exchange."""

    cleaned = str(symbol).strip().upper()
    if not cleaned:
        raise ValueError("symbol must be non-empty")
    if cleaned.startswith("SZ."):
        return f"{cleaned[3:]}.SZ"
    if cleaned.startswith("SH."):
        return f"{cleaned[3:]}.SH"
    return cleaned


def _require_frame(frame: pd.DataFrame, provider_label: str) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"{provider_label} input must be a pandas DataFrame")
    if frame.empty:
        raise ValueError(f"{provider_label} input must be non-empty")
    return frame.copy()


def _require_columns(frame: pd.DataFrame, columns: tuple[str, ...], provider_label: str) -> None:
    missing = tuple(column for column in columns if column not in frame.columns)
    if missing:
        raise ValueError(f"{provider_label} input missing required columns: {', '.join(missing)}")


def _require_normalized_frame(frame: pd.DataFrame) -> pd.DataFrame:
    source = _require_frame(frame, "normalized OHLCV")
    _require_columns(source, NORMALIZED_OHLCV_COLUMNS, "normalized OHLCV")
    return source


def _symbol_series(
    frame: pd.DataFrame,
    *,
    primary_col: str,
    fallback_symbol: str | None,
) -> pd.Series:
    if primary_col in frame.columns:
        values = frame[primary_col]
    elif fallback_symbol is not None:
        values = pd.Series([fallback_symbol] * len(frame), index=frame.index)
    else:
        raise ValueError(f"input missing required symbol column: {primary_col}")
    if values.isna().any():
        raise ValueError("symbol must not contain missing values")
    return values.astype(str)


def _date_series(values: pd.Series) -> pd.Series:
    dates = pd.to_datetime(values, errors="raise").dt.strftime("%Y-%m-%d")
    if dates.isna().any():
        raise ValueError("date must not contain missing values")
    return dates


def _numeric_series(values: pd.Series, field_name: str) -> pd.Series:
    numeric = pd.to_numeric(values, errors="raise").astype(float)
    if numeric.isna().any():
        raise ValueError(f"{field_name} must not contain missing values")
    return numeric


def _optional_numeric_series(frame: pd.DataFrame, field_name: str) -> pd.Series:
    if field_name not in frame.columns:
        return pd.Series([pd.NA] * len(frame), index=frame.index, dtype="Float64")
    return pd.to_numeric(frame[field_name].replace("", pd.NA), errors="raise").astype("Float64")


def _ordered_normalized_frame(frame: pd.DataFrame) -> pd.DataFrame:
    ordered = frame.loc[:, NORMALIZED_OHLCV_COLUMNS].copy()
    ordered = ordered.sort_values(["symbol", "date"], kind="stable").reset_index(drop=True)
    return ordered

