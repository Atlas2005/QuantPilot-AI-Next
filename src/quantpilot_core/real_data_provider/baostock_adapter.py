"""Optional BaoStock daily bar adapter for A-share data."""

from __future__ import annotations

import importlib
from enum import Enum
from typing import Any, Callable, Mapping, Sequence

from quantpilot_core.real_data_provider.contracts import (
    Adjustment,
    DailyBarProvider,
    DailyBarRequest,
    NormalizedDailyBar,
    ProviderDataError,
    ProviderName,
    parse_yyyymmdd,
    require_columns,
    to_float,
)


class BaoStockDependencyStatus(str, Enum):
    AVAILABLE = "available"
    MISSING = "missing"


CORE_COLUMNS = {"date", "open", "high", "low", "close", "volume"}
DEFAULT_FIELDS = "date,code,open,high,low,close,volume,amount"
ADJUSTMENT_FLAGS = {
    Adjustment.NONE: "3",
    Adjustment.QFQ: "2",
    Adjustment.HFQ: "1",
}


def detect_baostock_dependency(
    importer: Callable[[str], object] | None = None,
) -> BaoStockDependencyStatus:
    package_importer = importer or importlib.import_module
    try:
        package_importer("bao" + "stock")
    except ImportError:
        return BaoStockDependencyStatus.MISSING
    return BaoStockDependencyStatus.AVAILABLE


class BaoStockDailyBarProvider(DailyBarProvider):
    provider_name = ProviderName.BAOSTOCK

    def __init__(
        self,
        baostock_client: Any | None = None,
        importer: Callable[[str], object] | None = None,
    ) -> None:
        self._client = baostock_client
        self._importer = importer

    def fetch_daily_bars(self, request: DailyBarRequest) -> list[NormalizedDailyBar]:
        client = self._get_client()
        if not hasattr(client, "query_history_k_data_plus"):
            raise RuntimeError(
                "BaoStock-compatible client must expose query_history_k_data_plus."
            )
        raw = client.query_history_k_data_plus(
            code=request.symbol,
            fields=DEFAULT_FIELDS,
            start_date=request.start_date.isoformat(),
            end_date=request.end_date.isoformat(),
            frequency="d",
            adjustflag=ADJUSTMENT_FLAGS[request.adjustment],
        )
        return normalize_baostock_daily_bars(_rows_from_result(raw), request.symbol)

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if detect_baostock_dependency(self._importer) is BaoStockDependencyStatus.MISSING:
            raise RuntimeError(
                "BaoStock is an optional dependency and is missing. Inject a "
                "BaoStock-compatible client for tests or install it for real fetches."
            )
        package_importer = self._importer or importlib.import_module
        self._client = package_importer("bao" + "stock")
        return self._client


def normalize_baostock_daily_bars(
    rows: Any,
    symbol: str,
) -> list[NormalizedDailyBar]:
    records = _rows_from_result(rows)
    if not records:
        raise ProviderDataError("BaoStock daily bar rows must be non-empty")
    return [_normalize_row(row, symbol) for row in records]


def _rows_from_result(value: Any) -> list[Mapping[str, Any]]:
    if hasattr(value, "get_data"):
        value = value.get_data()
    if hasattr(value, "to_dict"):
        value = value.to_dict("records")
    if not isinstance(value, list):
        raise ProviderDataError("BaoStock output must be row records")
    return [_row_to_mapping(row) for row in value]


def _row_to_mapping(row: Any) -> Mapping[str, Any]:
    if isinstance(row, Mapping):
        return row
    if isinstance(row, Sequence) and not isinstance(row, (str, bytes)):
        fields = ("date", "code", "open", "high", "low", "close", "volume", "amount")
        if len(row) < 7:
            raise ProviderDataError("BaoStock tuple rows must include OHLCV fields")
        return {field: row[index] for index, field in enumerate(fields[: len(row)])}
    raise ProviderDataError("BaoStock rows must be mappings or records")


def _normalize_row(row: Mapping[str, Any], fallback_symbol: str) -> NormalizedDailyBar:
    try:
        require_columns(row, CORE_COLUMNS)
        trade_date = parse_yyyymmdd(str(row["date"]).replace("-", ""))
        return NormalizedDailyBar(
            symbol=str(row.get("code") or fallback_symbol),
            trade_date=trade_date,
            open=to_float(row["open"], "open"),
            close=to_float(row["close"], "close"),
            high=to_float(row["high"], "high"),
            low=to_float(row["low"], "low"),
            volume=to_float(row["volume"], "volume"),
            amount=_optional_float(row, "amount"),
            provider=ProviderName.BAOSTOCK,
        )
    except ProviderDataError:
        raise
    except (KeyError, ValueError) as exc:
        raise ProviderDataError("BaoStock row could not be normalized") from exc


def _optional_float(row: Mapping[str, Any], field_name: str) -> float | None:
    if field_name not in row or row[field_name] is None:
        return None
    if isinstance(row[field_name], str) and not row[field_name].strip():
        return None
    return to_float(row[field_name], field_name)
