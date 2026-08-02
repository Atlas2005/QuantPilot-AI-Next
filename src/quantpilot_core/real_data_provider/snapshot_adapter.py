"""Offline DailyBarProvider adapter for validated all-A-share snapshots."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from quantpilot_core.all_a_share_snapshot import SnapshotLoader, validate_snapshot
from quantpilot_core.real_data_provider.contracts import (
    Adjustment, DailyBarRequest, NormalizedDailyBar, ProviderDataError,
    ProviderError, ProviderName,
)


class SnapshotDailyBarProvider:
    """Read PR #118 daily partitions only; this class has no network boundary."""

    provider_name = ProviderName.SNAPSHOT

    def __init__(self, root: str | Path, *, validation_result: Any | None = None) -> None:
        self.root = Path(root)
        result = validation_result or validate_snapshot(self.root)
        if not result.ok or result.manifest.get("status") != "completed":
            details = "; ".join(result.errors) or str(result.manifest.get("status", "missing"))
            raise ProviderError(f"invalid all-A-share snapshot: {details}")
        self._loader = SnapshotLoader(self.root)
        self._manifest = dict(result.manifest)
        # The validator has already proved the calendar partition safe; retain
        # only its small session index, never the daily partitions.
        self._sessions_cache = tuple(self._loader.sessions())

    def snapshot_provenance(self, *, requested_symbols: int | None = None) -> dict[str, Any]:
        manifest = self._manifest
        value: dict[str, Any] = {
            "provider": self.provider_name.value,
            "snapshot_digest": manifest.get("digest"),
            "format_version": manifest.get("format_version"),
            "schema_version": manifest.get("schema_version"),
            "requested_date_range": dict(manifest.get("requested_date_range", {})),
            "actual_date_range": dict(manifest.get("actual_date_range", {})),
            "snapshot_session_count": manifest.get("official_session_count"),
            "snapshot_scope": manifest.get("scope"),
            "canonical": manifest.get("canonical"),
            "artifact_status": manifest.get("status"),
            "capabilities": dict(manifest.get("capabilities", {})),
            "snapshot_root": str(self.root),
            "external_calls_occurred": False,
        }
        if requested_symbols is not None:
            value["requested_symbols"] = requested_symbols
        return value

    def daily_symbol_union(self, start_date, end_date) -> tuple[str, ...]:
        return tuple(sorted({str(row["ts_code"]) for day in self._sessions(start_date, end_date)
                             for row in self._loader.daily(day)}))

    def tradability_metadata(self, start_date, end_date) -> dict[str, Any]:
        """Return optional persisted suspend/limit rows in the existing override shape."""
        capabilities = self._manifest.get("capabilities", {})
        overrides: list[dict[str, Any]] = []
        for day in self._sessions(start_date, end_date):
            suspended = {str(row["ts_code"]) for row in self._loader.optional("suspend", day)} if capabilities.get("suspend") == "available" else set()
            limits = {str(row["ts_code"]): row for row in self._loader.optional("limits", day)} if capabilities.get("limits") == "available" else {}
            for symbol in sorted(suspended | set(limits)):
                limit = limits.get(symbol, {})
                overrides.append({"trade_date": day, "symbol": symbol, "is_suspended": symbol in suspended,
                                  "upper_limit": limit.get("up_limit"), "lower_limit": limit.get("down_limit"),
                                  "source": self.provider_name.value, "data_quality": "snapshot"})
        return {"a_share_tradability_metadata": {"enabled": bool(overrides),
                "primary_price_provider": self.provider_name.value,
                "fetched_at": self._manifest.get("completed_at"),
                "tradability_overrides": overrides}}

    def fetch_daily_bars(self, request: DailyBarRequest) -> list[NormalizedDailyBar]:
        return self.fetch_many_daily_bars((request,))

    def fetch_many_daily_bars(self, requests: Sequence[DailyBarRequest]) -> list[NormalizedDailyBar]:
        bars, _ = self.fetch_many_daily_bars_with_empty_symbols(requests)
        return bars

    def fetch_many_daily_bars_with_empty_symbols(self, requests: Sequence[DailyBarRequest]):
        requests = tuple(requests)
        if any(request.adjustment is not Adjustment.NONE for request in requests):
            raise ProviderError("snapshot daily bars support Adjustment.NONE only")
        wanted = {request.symbol for request in requests}
        by_symbol: dict[str, list[NormalizedDailyBar]] = {symbol: [] for symbol in wanted}
        # Each partition is loaded once for the whole request batch.
        for day in sorted({day for request in requests for day in self._sessions(request.start_date, request.end_date)}):
            active = {request.symbol for request in requests if self._in_range(day, request)}
            for row in self._loader.daily(day):
                symbol = str(row.get("ts_code", ""))
                if symbol in active:
                    by_symbol[symbol].append(self._bar(row))
        output = [bar for symbol in sorted(by_symbol) for bar in sorted(by_symbol[symbol], key=lambda item: item.trade_date)]
        return output, tuple(symbol for symbol in sorted(wanted) if not by_symbol[symbol])

    def _sessions(self, start_date, end_date) -> tuple[str, ...]:
        start, end = self._date(start_date), self._date(end_date)
        return tuple(day for day in self._sessions_cache if start <= day <= end)

    @staticmethod
    def _date(value) -> str:
        return value.strftime("%Y%m%d") if hasattr(value, "strftime") else str(value).replace("-", "")

    def _in_range(self, day: str, request: DailyBarRequest) -> bool:
        return self._date(request.start_date) <= day <= self._date(request.end_date)

    def _bar(self, row: dict[str, Any]) -> NormalizedDailyBar:
        required = ("ts_code", "trade_date", "open", "high", "low", "close", "vol", "amount")
        if any(row.get(key) is None for key in required):
            raise ProviderDataError(f"snapshot daily row missing required fields: {row.get('ts_code')}")
        try:
            trade_date = datetime.strptime(str(row["trade_date"]), "%Y%m%d").date()
            return NormalizedDailyBar(symbol=str(row["ts_code"]), trade_date=trade_date,
                open=float(row["open"]), high=float(row["high"]), low=float(row["low"]), close=float(row["close"]),
                volume=float(row["vol"]), amount=float(row["amount"]), previous_close=self._optional(row.get("pre_close")),
                pct_change=self._optional(row.get("pct_chg")), adjustment_flag=Adjustment.NONE.value,
                provider=self.provider_name)
        except (TypeError, ValueError) as exc:
            raise ProviderDataError(f"invalid snapshot daily row: {row.get('ts_code')}") from exc

    @staticmethod
    def _optional(value):
        return None if value is None else float(value)
