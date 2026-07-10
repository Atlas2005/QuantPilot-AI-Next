"""Direct, lazy Tushare implementation of the all-A-share provider protocol."""
from __future__ import annotations

import importlib
import os
from typing import Any, Mapping, Sequence

from quantpilot_core.all_a_share_snapshot.contracts import AllAShareProvider


def _records(value: Any) -> list[Mapping[str, Any]]:
    if hasattr(value, "to_dict"):
        value = value.to_dict("records")
    if not isinstance(value, list):
        raise ValueError("Tushare endpoint must return row records")
    return [dict(row) for row in value]


class TushareAllAShareProvider(AllAShareProvider):
    """No-fallback direct Tushare client; it is never created at import time."""
    provider_name = "tushare"

    def __init__(self, client: Any | None = None, importer=importlib.import_module) -> None:
        self._client, self._importer = client, importer

    def _api(self) -> Any:
        if self._client is not None:
            return self._client
        token = os.environ.get("TUSHARE_TOKEN")
        if not token or not token.strip():
            raise RuntimeError("TUSHARE_TOKEN is required for real all-A-share snapshot builds.")
        package = self._importer("tushare")
        self._client = package.pro_api(token.strip())
        return self._client

    def _call(self, endpoint: str, **kwargs: Any) -> list[Mapping[str, Any]]:
        method = getattr(self._api(), endpoint, None)
        if method is None:
            raise NotImplementedError(f"Tushare endpoint unavailable: {endpoint}")
        return _records(method(**kwargs))

    def fetch_stock_basic(self, list_statuses: Sequence[str]) -> Sequence[Mapping[str, Any]]:
        return [row for status in list_statuses for row in self._call("stock_basic", exchange="", list_status=status,
            fields="ts_code,symbol,name,area,industry,market,exchange,list_status,list_date,delist_date")]
    def fetch_trade_cal(self, start_date: str, end_date: str) -> Sequence[Mapping[str, Any]]:
        return self._call("trade_cal", exchange="SSE", start_date=start_date, end_date=end_date, fields="exchange,cal_date,is_open")
    def fetch_daily_by_trade_date(self, trade_date: str) -> Sequence[Mapping[str, Any]]:
        return self._call("daily", trade_date=trade_date, fields="ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount")
    def fetch_adj_factor_by_trade_date(self, trade_date: str) -> Sequence[Mapping[str, Any]]:
        return self._call("adj_factor", trade_date=trade_date, fields="ts_code,trade_date,adj_factor")
    def fetch_index_daily(self, symbol: str, start_date: str, end_date: str) -> Sequence[Mapping[str, Any]]:
        return self._call("index_daily", ts_code=symbol, start_date=start_date, end_date=end_date,
            fields="ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount")
    def fetch_optional(self, dataset: str, trade_date: str | None = None) -> Sequence[Mapping[str, Any]]:
        if dataset == "namechange":
            raise ValueError("namechange is acquired per symbol to prove completeness")
        endpoint = {"daily_basic": "daily_basic", "suspend": "suspend_d", "limits": "stk_limit"}[dataset]
        fields = {
            "daily_basic": "ts_code,trade_date,close,turnover_rate,pe,pb,total_mv",
            # suspend_d is a daily event table, not a suspension interval table.
            "suspend": "ts_code,trade_date,suspend_timing,suspend_type",
            "limits": "ts_code,trade_date,up_limit,down_limit",
        }[dataset]
        return self._call(endpoint, trade_date=trade_date, fields=fields)

    def fetch_namechange_by_ts_code(self, ts_code: str) -> Sequence[Mapping[str, Any]]:
        # Tushare supports ts_code filtering.  A per-symbol query avoids the
        # endpoint's unbounded-query response cap and returns the full history.
        return self._call("namechange", ts_code=ts_code,
                          fields="ts_code,name,start_date,end_date,ann_date,change_reason")
