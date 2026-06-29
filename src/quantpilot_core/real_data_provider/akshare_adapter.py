"""Optional AkShare daily bar adapter for A-share data.

The adapter is intentionally thin: it normalizes provider output but does not
make AkShare a required project dependency.
"""

from __future__ import annotations

import importlib
from typing import Any, Mapping

from quantpilot_core.real_data_provider.contracts import (
    Adjustment,
    DailyBarRequest,
    DailyBarProvider,
    NormalizedDailyBar,
    ProviderDataError,
    ProviderDependencyError,
    ProviderName,
    parse_yyyymmdd,
    require_columns,
    to_float,
    to_yyyymmdd,
)


CORE_COLUMNS = {"日期", "开盘", "收盘", "最高", "最低", "成交量"}
ADJUSTMENT_TO_PROVIDER_VALUE = {
    Adjustment.NONE: "",
    Adjustment.QFQ: "qfq",
    Adjustment.HFQ: "hfq",
}


class AkShareDailyBarProvider(DailyBarProvider):
    provider_name = ProviderName.AKSHARE

    def __init__(self, akshare_client: Any | None = None) -> None:
        self._client = akshare_client

    def fetch_daily_bars(self, request: DailyBarRequest) -> list[NormalizedDailyBar]:
        client = self._get_client()
        try:
            raw = client.stock_zh_a_hist(
                symbol=request.symbol,
                period="daily",
                start_date=to_yyyymmdd(request.start_date),
                end_date=to_yyyymmdd(request.end_date),
                adjust=ADJUSTMENT_TO_PROVIDER_VALUE[request.adjustment],
            )
        except AttributeError as exc:
            raise ProviderDependencyError(
                "AkShare-compatible client must expose stock_zh_a_hist."
            ) from exc
        except Exception as exc:
            raise ProviderDataError("provider daily bar request failed") from exc

        bars = [_normalize_row(request.symbol, row) for row in _rows_from_frame(raw)]
        return sorted(bars, key=lambda bar: bar.trade_date)

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            self._client = importlib.import_module("ak" + "share")
        except ImportError as exc:
            raise ProviderDependencyError(
                "AkShare is an optional dependency. Install it before using "
                "AkShareDailyBarProvider without an injected client."
            ) from exc
        return self._client


def _rows_from_frame(frame: Any) -> list[Mapping[str, Any]]:
    if hasattr(frame, "to_dict"):
        records = frame.to_dict("records")
    else:
        records = frame
    if not isinstance(records, list):
        raise ProviderDataError("provider output must be convertible to row records")
    if not all(isinstance(row, Mapping) for row in records):
        raise ProviderDataError("provider output rows must be mappings")
    return records


def _normalize_row(symbol: str, row: Mapping[str, Any]) -> NormalizedDailyBar:
    try:
        require_columns(row, CORE_COLUMNS)
        return NormalizedDailyBar(
            symbol=symbol,
            trade_date=parse_yyyymmdd(str(row["日期"]).replace("-", "")),
            open=to_float(row["开盘"], "open"),
            close=to_float(row["收盘"], "close"),
            high=to_float(row["最高"], "high"),
            low=to_float(row["最低"], "low"),
            volume=to_float(row["成交量"], "volume"),
            amount=_optional_float(row, "成交额", "amount"),
            pct_change=_optional_float(row, "涨跌幅", "pct_change"),
            turnover=_optional_float(row, "换手率", "turnover"),
            provider=ProviderName.AKSHARE,
        )
    except ProviderDataError:
        raise
    except (KeyError, ValueError) as exc:
        raise ProviderDataError("provider row could not be normalized") from exc


def _optional_float(
    row: Mapping[str, Any],
    source_field: str,
    normalized_field: str,
) -> float | None:
    if source_field not in row or row[source_field] is None:
        return None
    if isinstance(row[source_field], str) and not row[source_field].strip():
        return None
    return to_float(row[source_field], normalized_field)
