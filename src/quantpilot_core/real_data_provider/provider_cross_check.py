"""Diagnostics for already-fetched daily bars from two providers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from quantpilot_core.real_data_provider.contracts import NormalizedDailyBar, ProviderName


@dataclass(frozen=True)
class DailyBarComparison:
    selected_provider: ProviderName
    overlapping_trade_date_count: int
    missing_dates_by_provider: Mapping[str, tuple[str, ...]]
    ohlc_differences: tuple[Mapping[str, float | str | None], ...]
    warnings: tuple[str, ...]


def compare_daily_bars(
    *,
    selected_provider: ProviderName,
    tushare_bars: Sequence[NormalizedDailyBar],
    baostock_bars: Sequence[NormalizedDailyBar],
    relative_tolerance: float = 0.001,
) -> DailyBarComparison:
    tushare_by_date = {bar.trade_date: bar for bar in tushare_bars}
    baostock_by_date = {bar.trade_date: bar for bar in baostock_bars}
    overlap = tuple(sorted(set(tushare_by_date) & set(baostock_by_date)))
    missing_tushare = tuple(date.isoformat() for date in sorted(set(baostock_by_date) - set(tushare_by_date)))
    missing_baostock = tuple(date.isoformat() for date in sorted(set(tushare_by_date) - set(baostock_by_date)))
    differences: list[Mapping[str, float | str]] = []
    warnings: list[str] = []
    for trade_date in overlap:
        left = tushare_by_date[trade_date]
        right = baostock_by_date[trade_date]
        for field in ("open", "high", "low", "close"):
            left_value = float(getattr(left, field))
            right_value = float(getattr(right, field))
            absolute = abs(left_value - right_value)
            relative = _relative_difference(left_value, right_value)
            if relative is None:
                if absolute == 0:
                    continue
                warnings.append("zero.reference.relative_difference_unavailable")
                differences.append(
                    {
                        "trade_date": trade_date.isoformat(),
                        "field": field,
                        "absolute_difference": round(absolute, 6),
                        "relative_difference": None,
                    }
                )
                continue
            if relative > relative_tolerance:
                differences.append(
                    {
                        "trade_date": trade_date.isoformat(),
                        "field": field,
                        "absolute_difference": round(absolute, 6),
                        "relative_difference": round(relative, 6),
                    }
                )
    if missing_tushare:
        warnings.append("missing_tushare_dates")
    if missing_baostock:
        warnings.append("missing_baostock_dates")
    if differences:
        warnings.append("ohlc_difference_above_tolerance")
    if any(bar.adjustment_flag for bar in baostock_bars):
        warnings.append("provider_adjustment_or_unit_semantics_may_differ")
    return DailyBarComparison(
        selected_provider=selected_provider,
        overlapping_trade_date_count=len(overlap),
        missing_dates_by_provider={
            ProviderName("tu" + "share").value: missing_tushare,
            ProviderName("bao" + "stock").value: missing_baostock,
        },
        ohlc_differences=tuple(differences),
        warnings=tuple(dict.fromkeys(warnings)),
    )


def _relative_difference(left_value: float, right_value: float) -> float | None:
    if right_value == 0:
        if left_value == 0:
            return 0.0
        return None
    return abs(left_value - right_value) / abs(right_value)
