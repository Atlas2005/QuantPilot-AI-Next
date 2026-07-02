"""Narrow Qlib-style prediction artifact adapter for VBT3 signal frames."""

from __future__ import annotations

import pandas as pd

from quantpilot_core.data_provider_normalization.contracts import NORMALIZED_OHLCV_COLUMNS
from quantpilot_core.data_provider_normalization.normalization import canonicalize_a_share_symbol


VBT3_SIGNAL_COLUMNS = ("date", "symbol", "close", "entry_signal", "exit_signal")


def qlib_signal_artifact_to_vbt3_signal_frame(
    predictions: pd.DataFrame,
    normalized_ohlcv: pd.DataFrame,
    *,
    date_col: str = "datetime",
    symbol_col: str = "instrument",
    score_col: str = "score",
    top_n: int | None = None,
    score_threshold: float | None = None,
    holding_period: int | None = None,
    exit_col: str | None = None,
) -> pd.DataFrame:
    """Join Qlib-style scores to normalized OHLCV and emit VBT3 signal rows.

    The adapter is deliberately limited to deterministic ranking/threshold entry
    flags plus explicit or fixed-period exit flags.
    """

    signals = _normalized_prediction_frame(
        predictions,
        date_col=date_col,
        symbol_col=symbol_col,
        score_col=score_col,
        exit_col=exit_col,
    )
    closes = _normalized_ohlcv_frame(normalized_ohlcv)

    joined = signals.merge(closes, on=("date", "symbol"), how="left", validate="many_to_one")
    missing_close = joined[joined["close"].isna()]
    if not missing_close.empty:
        keys = _key_sample(missing_close)
        raise ValueError(f"signal rows missing normalized OHLCV close: {keys}")

    joined["entry_signal"] = _entry_flags(joined, top_n=top_n, score_threshold=score_threshold)
    if exit_col is not None:
        joined["exit_signal"] = joined["_explicit_exit"].astype(bool)
    else:
        joined["exit_signal"] = _fixed_holding_exits(joined, holding_period=holding_period)

    output = joined.loc[:, VBT3_SIGNAL_COLUMNS].copy()
    return output.sort_values(["symbol", "date"], kind="stable").reset_index(drop=True)


def _normalized_prediction_frame(
    frame: pd.DataFrame,
    *,
    date_col: str,
    symbol_col: str,
    score_col: str,
    exit_col: str | None,
) -> pd.DataFrame:
    _require_frame(frame, "Qlib signal artifact")
    required = (date_col, symbol_col, score_col) + ((exit_col,) if exit_col is not None else ())
    _require_columns(frame, required, "Qlib signal artifact")
    if frame[symbol_col].isna().any():
        raise ValueError("Qlib signal artifact symbol must not contain missing values")

    normalized = pd.DataFrame(
        {
            "date": _date_series(frame[date_col]),
            "symbol": frame[symbol_col].map(canonicalize_a_share_symbol),
            "score": pd.to_numeric(frame[score_col], errors="raise").astype(float),
        }
    )
    if normalized["score"].isna().any():
        raise ValueError("Qlib signal artifact score must not contain missing values")
    if exit_col is not None:
        normalized["_explicit_exit"] = frame[exit_col].astype(bool).to_numpy()
    if normalized[["date", "symbol"]].duplicated().any():
        raise ValueError("Qlib signal artifact contains duplicate symbol/date rows")
    return normalized


def _normalized_ohlcv_frame(frame: pd.DataFrame) -> pd.DataFrame:
    _require_frame(frame, "normalized OHLCV")
    _require_columns(frame, NORMALIZED_OHLCV_COLUMNS, "normalized OHLCV")
    if frame["symbol"].isna().any():
        raise ValueError("normalized OHLCV symbol must not contain missing values")
    normalized = pd.DataFrame(
        {
            "date": _date_series(frame["date"]),
            "symbol": frame["symbol"].map(canonicalize_a_share_symbol),
            "close": pd.to_numeric(frame["close"], errors="raise").astype(float),
        }
    )
    if normalized["close"].isna().any():
        raise ValueError("normalized OHLCV close must not contain missing values")
    if (normalized["close"] <= 0).any():
        raise ValueError("normalized OHLCV close prices must be positive")
    if normalized[["date", "symbol"]].duplicated().any():
        raise ValueError("normalized OHLCV contains duplicate symbol/date rows")
    return normalized


def _entry_flags(frame: pd.DataFrame, *, top_n: int | None, score_threshold: float | None) -> pd.Series:
    if top_n is None and score_threshold is None:
        raise ValueError("entry rule required: provide top_n or score_threshold")
    if top_n is not None and top_n <= 0:
        raise ValueError("top_n must be positive")

    selected = pd.Series(False, index=frame.index)
    if score_threshold is not None:
        selected = selected | (frame["score"] >= float(score_threshold))
    if top_n is not None:
        ranked = frame.sort_values(["date", "score", "symbol"], ascending=[True, False, True], kind="stable")
        top_index = ranked.groupby("date", sort=False).head(top_n).index
        selected.loc[top_index] = True
    return selected.astype(bool)


def _fixed_holding_exits(frame: pd.DataFrame, *, holding_period: int | None) -> pd.Series:
    exits = pd.Series(False, index=frame.index)
    if holding_period is None:
        return exits
    if holding_period <= 0:
        raise ValueError("holding_period must be positive")

    ordered = frame.sort_values(["symbol", "date"], kind="stable")
    for _symbol, group in ordered.groupby("symbol", sort=False):
        group_indices = tuple(group.index)
        for position, row_index in enumerate(group_indices):
            if not bool(frame.loc[row_index, "entry_signal"]):
                continue
            exit_position = position + holding_period
            if exit_position < len(group_indices):
                exits.loc[group_indices[exit_position]] = True
    return exits.astype(bool)


def _require_frame(frame: pd.DataFrame, label: str) -> None:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"{label} must be a pandas DataFrame")
    if frame.empty:
        raise ValueError(f"{label} must be non-empty")


def _require_columns(frame: pd.DataFrame, columns: tuple[str, ...], label: str) -> None:
    missing = tuple(column for column in columns if column not in frame.columns)
    if missing:
        raise ValueError(f"{label} missing required columns: {', '.join(missing)}")


def _date_series(values: pd.Series) -> pd.Series:
    dates = pd.to_datetime(values, errors="raise").dt.strftime("%Y-%m-%d")
    if dates.isna().any():
        raise ValueError("date must not contain missing values")
    return dates


def _key_sample(frame: pd.DataFrame) -> str:
    keys = tuple(f"{row.symbol}:{row.date}" for row in frame.loc[:, ["symbol", "date"]].itertuples())
    return ", ".join(keys[:5])
