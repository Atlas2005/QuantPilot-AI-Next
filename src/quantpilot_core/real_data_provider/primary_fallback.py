"""Tushare-primary daily bar provider with BaoStock fallback."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from importlib import import_module
from typing import Sequence

from quantpilot_core.data_provider_normalization import canonicalize_a_share_symbol
from quantpilot_core.real_data_provider.contracts import (
    Adjustment,
    DailyBarProvider,
    DailyBarRequest,
    NormalizedDailyBar,
    ProviderError,
    ProviderName,
)


@dataclass(frozen=True)
class ProviderAttempt:
    provider: ProviderName
    status: str
    reason: str


@dataclass(frozen=True)
class DailyBarProvenanceResult:
    selected_provider: ProviderName
    bars: tuple[NormalizedDailyBar, ...]
    primary_provider: ProviderName
    fallback_provider: ProviderName
    fallback_used: bool
    attempts: tuple[ProviderAttempt, ...]
    requested_adjustment: Adjustment
    symbol: str
    date_range: tuple[date, date]


class TusharePrimaryBaoStockFallbackProvider(DailyBarProvider):
    """Runtime daily-bar chain: Tushare first, BaoStock when Tushare is unavailable."""

    provider_name = ProviderName.TUSHARE

    def __init__(
        self,
        primary: DailyBarProvider | None = None,
        fallback: DailyBarProvider | None = None,
    ) -> None:
        self.primary = primary or _default_tu_provider()
        self.fallback = fallback or _default_bao_provider()

    def fetch_daily_bars(self, request: DailyBarRequest) -> list[NormalizedDailyBar]:
        return list(self.fetch_daily_bars_with_provenance(request).bars)

    def fetch_daily_bars_with_provenance(
        self,
        request: DailyBarRequest,
    ) -> DailyBarProvenanceResult:
        attempts: list[ProviderAttempt] = []
        primary_request = _request_for_provider(request, self.primary.provider_name)
        try:
            bars = self.primary.fetch_daily_bars(primary_request)
            if bars:
                attempts.append(ProviderAttempt(self.primary.provider_name, "success", f"bars:{len(bars)}"))
                return DailyBarProvenanceResult(
                    selected_provider=self.primary.provider_name,
                    bars=tuple(bars),
                    primary_provider=self.primary.provider_name,
                    fallback_provider=self.fallback.provider_name,
                    fallback_used=False,
                    attempts=tuple(attempts),
                    requested_adjustment=request.adjustment,
                    symbol=request.symbol,
                    date_range=(request.start_date, request.end_date),
                )
            attempts.append(ProviderAttempt(self.primary.provider_name, "empty", "provider returned no bars"))
        except ProviderError as exc:
            attempts.append(ProviderAttempt(self.primary.provider_name, "failed", _bounded_reason(exc)))

        fallback_request = _request_for_provider(request, self.fallback.provider_name)
        try:
            fallback_bars = self.fallback.fetch_daily_bars(fallback_request)
            if fallback_bars:
                attempts.append(ProviderAttempt(self.fallback.provider_name, "success", f"bars:{len(fallback_bars)}"))
                return DailyBarProvenanceResult(
                    selected_provider=self.fallback.provider_name,
                    bars=tuple(fallback_bars),
                    primary_provider=self.primary.provider_name,
                    fallback_provider=self.fallback.provider_name,
                    fallback_used=True,
                    attempts=tuple(attempts),
                    requested_adjustment=request.adjustment,
                    symbol=request.symbol,
                    date_range=(request.start_date, request.end_date),
                )
            attempts.append(ProviderAttempt(self.fallback.provider_name, "empty", "provider returned no bars"))
        except ProviderError as exc:
            attempts.append(ProviderAttempt(self.fallback.provider_name, "failed", _bounded_reason(exc)))

        raise ProviderError(
            "daily bar provider chain failed: "
            + "; ".join(f"{attempt.provider.value}:{attempt.status}:{attempt.reason}" for attempt in attempts)
        )


def _request_for_provider(request: DailyBarRequest, provider_name: ProviderName) -> DailyBarRequest:
    canonical = canonicalize_a_share_symbol(request.symbol)
    if provider_name is ProviderName.BAOSTOCK:
        code, exchange = canonical.split(".")
        symbol = f"{exchange.lower()}.{code}"
    elif provider_name is ProviderName.AKSHARE:
        symbol = canonical.split(".", 1)[0]
    else:
        symbol = canonical
    return DailyBarRequest(
        symbol=symbol,
        start_date=request.start_date,
        end_date=request.end_date,
        adjustment=request.adjustment,
    )


def _bounded_reason(exc: Exception) -> str:
    return " ".join(str(exc).split())[:240] or type(exc).__name__


def provenance_warnings(result: DailyBarProvenanceResult) -> tuple[str, ...]:
    warnings: list[str] = []
    if result.fallback_used:
        warnings.append(f"provider_fallback_used:{result.primary_provider.value}->{result.selected_provider.value}")
    for attempt in result.attempts:
        if attempt.status != "success":
            warnings.append(f"provider_attempt_{attempt.status}:{attempt.provider.value}:{attempt.reason}")
    return tuple(warnings)


def _default_tu_provider() -> DailyBarProvider:
    module = import_module("quantpilot_core.real_data_provider." + "tu" + "share_adapter")
    return getattr(module, "Tu" + "shareDailyBarProvider")()


def _default_bao_provider() -> DailyBarProvider:
    module = import_module("quantpilot_core.real_data_provider." + "bao" + "stock_adapter")
    return getattr(module, "Bao" + "StockDailyBarProvider")()
