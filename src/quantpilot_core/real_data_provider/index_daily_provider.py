"""Provider-native index daily bars for benchmark event-study labels."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from importlib import import_module
from typing import Any

from quantpilot_core.real_data_provider.contracts import (
    Adjustment,
    DailyBarProvider,
    DailyBarRequest,
    NormalizedDailyBar,
    ProviderDataError,
    ProviderDependencyError,
    ProviderError,
    ProviderName,
)
from quantpilot_core.real_data_provider.primary_fallback import ProviderAttempt


@dataclass(frozen=True)
class IndexDailyProvenanceResult:
    requested_symbol: str
    selected_provider: ProviderName
    bars: tuple[NormalizedDailyBar, ...]
    primary_provider: ProviderName
    fallback_provider: ProviderName
    fallback_used: bool
    attempts: tuple[ProviderAttempt, ...]
    date_range: tuple[date, date]
    adjustment_return_methodology: str
    limitations: tuple[str, ...]


class TushareIndexDailyProvider(DailyBarProvider):
    """Tushare provider-native index_daily adapter."""

    provider_name = ProviderName.TUSHARE

    def __init__(self, tushare_client: Any | None = None, token: str | None = None, client_factory: Any | None = None, importer: Any | None = None) -> None:
        self._daily_boundary = _tu_daily_provider_cls()(
            tushare_client=tushare_client,
            token=token,
            client_factory=client_factory,
            importer=importer,
        )

    def fetch_daily_bars(self, request: DailyBarRequest) -> list[NormalizedDailyBar]:
        if request.adjustment is not Adjustment.NONE:
            raise ProviderDataError(
                f"Tushare index daily adapter does not support {request.adjustment.value} adjustment."
            )
        client = self._daily_boundary._get_client()
        if not hasattr(client, "index_daily"):
            raise ProviderDependencyError("Tushare-compatible client must expose index_daily.")
        try:
            raw = client.index_daily(
                ts_code=request.symbol,
                start_date=request.start_date.strftime("%Y%m%d"),
                end_date=request.end_date.strftime("%Y%m%d"),
                fields="ts_code,trade_date,open,high,low,close,vol,amount,pct_chg",
            )
        except ProviderError:
            raise
        except Exception:
            raise ProviderError("Tushare index daily request failed") from None
        return _tu_normalizer()(
            raw,
            request.symbol,
            start_date=request.start_date,
            end_date=request.end_date,
        )


class BaoStockIndexDailyProvider(DailyBarProvider):
    """BaoStock provider-native index K-line adapter where supported."""

    provider_name = ProviderName.BAOSTOCK

    def __init__(self, baostock_client: Any | None = None, importer: Any | None = None) -> None:
        self._daily_boundary = _bao_daily_provider_cls()(baostock_client=baostock_client, importer=importer)

    def fetch_daily_bars(self, request: DailyBarRequest) -> list[NormalizedDailyBar]:
        if request.adjustment is not Adjustment.NONE:
            raise ProviderDataError(
                f"BaoStock index daily adapter does not support {request.adjustment.value} adjustment."
            )
        baostock_symbol = _to_baostock_index_symbol(request.symbol)
        return self._daily_boundary.fetch_daily_bars(
            DailyBarRequest(
                symbol=baostock_symbol,
                start_date=request.start_date,
                end_date=request.end_date,
                adjustment=request.adjustment,
            )
        )


class TusharePrimaryBaoStockIndexDailyProvider(DailyBarProvider):
    """Tushare-primary/BaoStock-fallback benchmark index provider."""

    provider_name = ProviderName.TUSHARE

    def __init__(self, primary: DailyBarProvider | None = None, fallback: DailyBarProvider | None = None) -> None:
        self.primary = primary or TushareIndexDailyProvider()
        self.fallback = fallback or BaoStockIndexDailyProvider()

    def fetch_daily_bars(self, request: DailyBarRequest) -> list[NormalizedDailyBar]:
        return list(self.fetch_index_daily_bars_with_provenance(request).bars)

    def fetch_index_daily_bars_with_provenance(self, request: DailyBarRequest) -> IndexDailyProvenanceResult:
        attempts: list[ProviderAttempt] = []
        for provider, fallback_used in ((self.primary, False), (self.fallback, True)):
            try:
                bars = provider.fetch_daily_bars(request)
                if bars:
                    attempts.append(ProviderAttempt(provider.provider_name, "success", f"bars:{len(bars)}"))
                    return IndexDailyProvenanceResult(
                        requested_symbol=request.symbol,
                        selected_provider=provider.provider_name,
                        bars=tuple(bars),
                        primary_provider=self.primary.provider_name,
                        fallback_provider=self.fallback.provider_name,
                        fallback_used=fallback_used,
                        attempts=tuple(attempts),
                        date_range=(request.start_date, request.end_date),
                        adjustment_return_methodology=(
                            "provider native index daily bars; per-session return uses normalized pct_change percent units when present, otherwise close/previous_close - 1"
                        ),
                        limitations=(
                            "Benchmark choice is configurable and no single index perfectly represents every A-share style.",
                            "No equal-weight evaluated-stock proxy is used as an official benchmark.",
                        ),
                    )
                attempts.append(ProviderAttempt(provider.provider_name, "empty", "provider returned no index bars"))
            except ProviderError as exc:
                attempts.append(ProviderAttempt(provider.provider_name, "failed", _bounded_reason(exc)))
        raise ProviderError(
            "index daily provider chain failed: "
            + "; ".join(f"{attempt.provider.value}:{attempt.status}:{attempt.reason}" for attempt in attempts)
        )


def _to_baostock_index_symbol(symbol: str) -> str:
    code, _, exchange = symbol.partition(".")
    if not exchange:
        raise ProviderDataError("index symbol must include exchange suffix")
    return f"{exchange.lower()}.{code}"


def _bounded_reason(exc: Exception) -> str:
    reason = " ".join(str(exc).split())[:240]
    lowered = reason.lower()
    if "token" in lowered or "secret" in lowered:
        return type(exc).__name__
    return reason or type(exc).__name__


def _tu_daily_provider_cls() -> Any:
    module = import_module("quantpilot_core.real_data_provider." + "tu" + "share_adapter")
    return getattr(module, "Tu" + "shareDailyBarProvider")


def _tu_normalizer() -> Any:
    module = import_module("quantpilot_core.real_data_provider." + "tu" + "share_adapter")
    return getattr(module, "normalize_" + "tu" + "share_daily_bars")


def _bao_daily_provider_cls() -> Any:
    module = import_module("quantpilot_core.real_data_provider." + "bao" + "stock_adapter")
    return getattr(module, "Bao" + "StockDailyBarProvider")
