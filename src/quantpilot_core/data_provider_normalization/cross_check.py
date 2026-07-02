"""Advisory cross-checks for normalized provider DataFrames."""

from __future__ import annotations

import math

import pandas as pd

from quantpilot_core.data_provider_normalization.contracts import (
    NORMALIZED_OHLCV_COLUMNS,
    ProviderCrossCheckReport,
    ProviderKey,
    ProviderValueDifference,
)


def cross_check_normalized_provider_frames(
    left: pd.DataFrame,
    right: pd.DataFrame,
) -> ProviderCrossCheckReport:
    """Compare two normalized frames by symbol/date and return advisory evidence."""

    left_frame = _validated_frame(left, "left")
    right_frame = _validated_frame(right, "right")
    left_duplicates = _duplicate_keys(left_frame)
    right_duplicates = _duplicate_keys(right_frame)
    left_deduped = left_frame.drop_duplicates(["symbol", "date"], keep="first")
    right_deduped = right_frame.drop_duplicates(["symbol", "date"], keep="first")
    left_keys = _key_set(left_deduped)
    right_keys = _key_set(right_deduped)
    common_keys = sorted(left_keys & right_keys)
    left_missing = tuple(ProviderKey(symbol, date) for symbol, date in sorted(right_keys - left_keys))
    right_missing = tuple(ProviderKey(symbol, date) for symbol, date in sorted(left_keys - right_keys))

    merged = left_deduped.merge(
        right_deduped,
        on=["symbol", "date"],
        how="inner",
        suffixes=("_left", "_right"),
    )
    close_differences = _value_differences(merged, "close")
    volume_differences = _value_differences(merged, "volume")

    denominator = len(left_keys | right_keys)
    coverage_ratio = 1.0 if denominator == 0 else len(common_keys) / denominator
    return ProviderCrossCheckReport(
        left_provider=_provider_name(left_frame),
        right_provider=_provider_name(right_frame),
        left_rows=len(left_frame),
        right_rows=len(right_frame),
        left_unique_symbol_dates=len(left_keys),
        right_unique_symbol_dates=len(right_keys),
        common_symbol_dates=len(common_keys),
        coverage_ratio=coverage_ratio,
        left_missing_dates=left_missing,
        right_missing_dates=right_missing,
        left_duplicate_symbol_dates=left_duplicates,
        right_duplicate_symbol_dates=right_duplicates,
        close_differences=close_differences,
        volume_differences=volume_differences,
        max_close_pct_difference=_max_pct_difference(close_differences),
        advisory_only=True,
    )


def _validated_frame(frame: pd.DataFrame, label: str) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"{label} frame must be a pandas DataFrame")
    missing = tuple(column for column in NORMALIZED_OHLCV_COLUMNS if column not in frame.columns)
    if missing:
        raise ValueError(f"{label} frame missing normalized columns: {', '.join(missing)}")
    source = frame.loc[:, NORMALIZED_OHLCV_COLUMNS].copy()
    if source[["symbol", "date"]].isna().any().any():
        raise ValueError(f"{label} frame symbol/date must not contain missing values")
    source["symbol"] = source["symbol"].astype(str)
    source["date"] = source["date"].astype(str)
    for field in ("close", "volume"):
        source[field] = pd.to_numeric(source[field], errors="raise").astype(float)
    return source


def _provider_name(frame: pd.DataFrame) -> str:
    values = tuple(str(value) for value in frame["provider"].dropna().unique())
    if len(values) == 1:
        return values[0]
    if not values:
        return "unknown"
    return "mixed"


def _duplicate_keys(frame: pd.DataFrame) -> tuple[ProviderKey, ...]:
    duplicate_rows = frame.loc[frame.duplicated(["symbol", "date"], keep=False), ["symbol", "date"]]
    keys = sorted(set(tuple(item) for item in duplicate_rows.itertuples(index=False, name=None)))
    return tuple(ProviderKey(symbol, date) for symbol, date in keys)


def _key_set(frame: pd.DataFrame) -> set[tuple[str, str]]:
    return set(tuple(item) for item in frame[["symbol", "date"]].itertuples(index=False, name=None))


def _value_differences(
    merged: pd.DataFrame,
    field_name: str,
) -> tuple[ProviderValueDifference, ...]:
    differences: list[ProviderValueDifference] = []
    left_col = f"{field_name}_left"
    right_col = f"{field_name}_right"
    for row in merged.itertuples(index=False):
        left_value = getattr(row, left_col)
        right_value = getattr(row, right_col)
        if _both_missing(left_value, right_value):
            continue
        absolute = _absolute_difference(left_value, right_value)
        if absolute is None or math.isclose(absolute, 0.0, rel_tol=0.0, abs_tol=0.0):
            continue
        differences.append(
            ProviderValueDifference(
                symbol=str(getattr(row, "symbol")),
                date=str(getattr(row, "date")),
                field_name=field_name,
                left_value=_optional_float(left_value),
                right_value=_optional_float(right_value),
                absolute_difference=absolute,
                pct_difference=_pct_difference(left_value, right_value),
            )
        )
    return tuple(differences)


def _both_missing(left_value: object, right_value: object) -> bool:
    return pd.isna(left_value) and pd.isna(right_value)


def _absolute_difference(left_value: object, right_value: object) -> float | None:
    if pd.isna(left_value) or pd.isna(right_value):
        return None
    return abs(float(left_value) - float(right_value))


def _pct_difference(left_value: object, right_value: object) -> float | None:
    if pd.isna(left_value) or pd.isna(right_value):
        return None
    base = abs(float(left_value))
    if base == 0:
        return None
    return abs(float(left_value) - float(right_value)) / base


def _optional_float(value: object) -> float | None:
    if pd.isna(value):
        return None
    return float(value)


def _max_pct_difference(differences: tuple[ProviderValueDifference, ...]) -> float | None:
    values = tuple(item.pct_difference for item in differences if item.pct_difference is not None)
    if not values:
        return None
    return max(values)

