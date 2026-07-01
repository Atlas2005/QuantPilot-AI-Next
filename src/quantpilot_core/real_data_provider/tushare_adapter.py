"""Optional Tushare daily bar adapter and normalizer for A-share data."""

from __future__ import annotations

import importlib
from enum import Enum
from typing import Any, Callable, Mapping, Sequence

from quantpilot_core.real_data_provider.contracts import (
    DailyBarProvider,
    DailyBarRequest,
    NormalizedDailyBar,
    ProviderDataError,
    ProviderName,
    parse_yyyymmdd,
    require_columns,
    to_float,
)


class TushareDependencyStatus(str, Enum):
    AVAILABLE = "available"
    MISSING = "missing"


CORE_COLUMNS = {"ts_code", "trade_date", "open", "high", "low", "close", "vol"}


def detect_tushare_dependency(
    importer: Callable[[str], object] | None = None,
) -> TushareDependencyStatus:
    package_importer = importer or importlib.import_module
    try:
        package_importer("tushare")
    except ImportError:
        return TushareDependencyStatus.MISSING
    return TushareDependencyStatus.AVAILABLE


class TushareDailyBarProvider(DailyBarProvider):
    provider_name = ProviderName.TUSHARE

    def __init__(
        self,
        tushare_client: Any | None = None,
        importer: Callable[[str], object] | None = None,
    ) -> None:
        self._client = tushare_client
        self._importer = importer

    def fetch_daily_bars(self, request: DailyBarRequest) -> list[NormalizedDailyBar]:
        client = self._get_client()
        if not hasattr(client, "daily"):
            raise RuntimeError("Tushare-compatible client must expose daily.")

        raw = client.daily(
            ts_code=request.symbol,
            start_date=request.start_date.strftime("%Y%m%d"),
            end_date=request.end_date.strftime("%Y%m%d"),
            fields="ts_code,trade_date,open,high,low,close,vol,amount,pct_chg",
        )
        return normalize_tushare_daily_bars(raw, request.symbol)

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if detect_tushare_dependency(self._importer) is TushareDependencyStatus.MISSING:
            raise RuntimeError(
                "Tushare is an optional dependency and is missing. Inject a "
                "Tushare-compatible client for tests or install/configure it for real fetches."
            )
        package_importer = self._importer or importlib.import_module
        tushare = package_importer("tushare")
        if not hasattr(tushare, "pro_api"):
            raise RuntimeError("Tushare package must expose pro_api.")
        self._client = tushare.pro_api()
        return self._client


def normalize_tushare_daily_bars(
    rows: Any,
    symbol: str,
) -> list[NormalizedDailyBar]:
    records = _rows_from_result(rows)
    if not records:
        raise ProviderDataError("Tushare daily bar rows must be non-empty")
    return [_normalize_row(row, symbol) for row in records]


def _rows_from_result(value: Any) -> list[Mapping[str, Any]]:
    if hasattr(value, "to_dict"):
        value = value.to_dict("records")
    if not isinstance(value, list):
        raise ProviderDataError("Tushare output must be row records")
    return [_row_to_mapping(row) for row in value]


def _row_to_mapping(row: Any) -> Mapping[str, Any]:
    if isinstance(row, Mapping):
        return row
    if isinstance(row, Sequence) and not isinstance(row, (str, bytes)):
        fields = (
            "ts_code",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "vol",
            "amount",
            "pct_chg",
        )
        if len(row) < 7:
            raise ProviderDataError("Tushare tuple rows must include OHLCV fields")
        return {field: row[index] for index, field in enumerate(fields[: len(row)])}
    raise ProviderDataError("Tushare rows must be mappings or records")


def _normalize_row(row: Mapping[str, Any], fallback_symbol: str) -> NormalizedDailyBar:
    try:
        require_columns(row, CORE_COLUMNS)
        return NormalizedDailyBar(
            symbol=str(row.get("ts_code") or fallback_symbol),
            trade_date=parse_yyyymmdd(str(row["trade_date"])),
            open=to_float(row["open"], "open"),
            close=to_float(row["close"], "close"),
            high=to_float(row["high"], "high"),
            low=to_float(row["low"], "low"),
            # Tushare vol is commonly reported in hands. Convert to shares
            # for compatibility with BaoStock volume semantics.
            volume=to_float(row["vol"], "vol") * 100.0,
            # Tushare amount is commonly reported in thousand CNY.
            # Convert to CNY-level notional for cross-provider comparison.
            amount=_optional_float_scaled(row, "amount", scale=1000.0),
            pct_change=_optional_float(row, "pct_chg"),
            provider=ProviderName.TUSHARE,
        )
    except ProviderDataError:
        raise
    except (KeyError, ValueError) as exc:
        raise ProviderDataError("Tushare row could not be normalized") from exc


def _optional_float(row: Mapping[str, Any], field_name: str) -> float | None:
    if field_name not in row or row[field_name] is None:
        return None
    if isinstance(row[field_name], str) and not row[field_name].strip():
        return None
    return to_float(row[field_name], field_name)


def _optional_float_scaled(
    row: Mapping[str, Any],
    field_name: str,
    scale: float,
) -> float | None:
    value = _optional_float(row, field_name)
    if value is None:
        return None
    return value * scale
