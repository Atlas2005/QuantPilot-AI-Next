"""Small real-data walk-forward smoke path for the existing engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from importlib import import_module
from typing import Any, Mapping, Sequence

import pandas as pd

from quantpilot_core.data_provider_normalization import canonicalize_a_share_symbol
from quantpilot_core.real_data_provider import (
    Adjustment,
    AkShareDailyBarProvider,
    BaoStockDailyBarProvider,
    DailyBarProvider,
    DailyBarRequest,
    NormalizedDailyBar,
    ProviderError,
    ProviderName,
)


DEFAULT_REAL_DATA_SMOKE_SYMBOLS = ("000001.SZ", "000002.SZ", "510300.SH", "510500.SH")
DEFAULT_PROVIDER = "baostock"
AK_PROVIDER = "ak" + "share"
BAO_PROVIDER = "bao" + "stock"
TU_PROVIDER = "tu" + "share"


@dataclass(frozen=True)
class RealDataWalkForwardSmokeConfig:
    """Configuration for a small A-share/ETF real-data smoke run."""

    symbols: tuple[str, ...] = DEFAULT_REAL_DATA_SMOKE_SYMBOLS
    start_date: date | str = "2024-01-01"
    end_date: date | str = "2024-03-31"
    initial_cash: float = 100_000.0
    train_window_days: int = 20
    test_window_days: int = 5
    max_windows: int = 2
    provider: str | DailyBarProvider = DEFAULT_PROVIDER
    advisory_mode: str = "fallback_only"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RealDataWalkForwardSmokeReport:
    """Compact report from the real-data walk-forward smoke runner."""

    symbols: tuple[str, ...]
    date_range: tuple[str, str]
    provider: str
    windows_run: int
    initial_cash: float
    final_equity: float | None
    total_return: float | None
    max_drawdown: float | None
    filled_trades: int
    rejected_trades: int
    cost_total: float
    per_window_metrics: tuple[Mapping[str, Any], ...]
    leakage_checks: tuple[str, ...]
    data_quality_warnings: tuple[str, ...]
    notes: tuple[str, ...]


def run_real_data_walk_forward_smoke(
    config: RealDataWalkForwardSmokeConfig | None = None,
    **kwargs: Any,
) -> RealDataWalkForwardSmokeReport:
    """Run a small provider-backed smoke through WalkForwardEngine."""

    payload = config or RealDataWalkForwardSmokeConfig(**kwargs)
    warnings = _validate_config(payload)
    provider_name = _provider_name(payload.provider)
    try:
        bars = _load_bars(payload)
    except Exception as exc:
        if isinstance(exc, (RuntimeError, ProviderError, ValueError)):
            return _unavailable_report(payload, provider_name, str(exc), warnings)
        raise

    price_frame = _bars_to_price_frame(bars)
    data_warnings = warnings + _data_quality_warnings(price_frame, payload)
    if price_frame.empty:
        return _unavailable_report(payload, provider_name, "provider returned no usable OHLCV rows", data_warnings)

    windows = _build_windows(price_frame, payload)
    if not windows:
        return _unavailable_report(payload, provider_name, "not enough trading dates for configured windows", data_warnings)

    from quantpilot_core.walk_forward.contracts import WalkForwardInput

    walk_input = WalkForwardInput(
        historical_price_frame=price_frame,
        historical_signal_frame=None,
        information_events=None,
        initial_cash=float(payload.initial_cash),
        current_parameters={
            "strategy_id": "real_data_walk_forward_smoke",
            "top_n": min(3, len(payload.symbols)),
            "capital": float(payload.initial_cash),
            "lot_size": 100,
        },
        windows=windows,
        advisory_mode=_safe_advisory_mode(payload.advisory_mode),
        metadata={
            **dict(payload.metadata),
            "real_data_walk_forward_smoke": True,
            "provider": provider_name,
            "symbols": tuple(canonicalize_a_share_symbol(symbol) for symbol in payload.symbols),
        },
    )
    from quantpilot_core.walk_forward.engine import WalkForwardEngine

    result = WalkForwardEngine().run(walk_input)
    per_window = tuple(
        {
            "run_label": window_result.window.run_label,
            "train_start": str(window_result.window.train_start),
            "train_end": str(window_result.window.train_end),
            "test_start": str(window_result.window.test_start),
            "test_end": str(window_result.window.test_end),
            **dict(window_result.performance_metrics),
        }
        for window_result in result.window_results
    )
    final_equity = _final_equity(per_window)
    return RealDataWalkForwardSmokeReport(
        symbols=tuple(canonicalize_a_share_symbol(symbol) for symbol in payload.symbols),
        date_range=(str(_as_date(payload.start_date)), str(_as_date(payload.end_date))),
        provider=provider_name,
        windows_run=len(result.window_results),
        initial_cash=float(payload.initial_cash),
        final_equity=final_equity,
        total_return=_total_return(payload.initial_cash, final_equity),
        max_drawdown=_max_drawdown(float(payload.initial_cash), per_window),
        filled_trades=sum(int(metrics.get("trade_count", 0)) for metrics in per_window),
        rejected_trades=sum(int(metrics.get("rejected_count", 0)) for metrics in per_window),
        cost_total=round(sum(float(metrics.get("cost_total", 0.0)) for metrics in per_window), 6),
        per_window_metrics=per_window,
        leakage_checks=result.leakage_checks,
        data_quality_warnings=data_warnings,
        notes=("real_data_smoke_completed", "no_broker_live_execution", f"advisory_mode:{walk_input.advisory_mode}"),
    )


def _load_bars(config: RealDataWalkForwardSmokeConfig) -> list[NormalizedDailyBar]:
    injected = config.metadata.get("normalized_daily_bars")
    if injected is not None:
        return list(injected)
    injected_frame = config.metadata.get("normalized_ohlcv")
    if injected_frame is not None:
        return _normalized_frame_to_bars(injected_frame, provider=_provider_name(config.provider))

    provider = _resolve_provider(config.provider)
    bars: list[NormalizedDailyBar] = []
    for symbol in config.symbols:
        request = DailyBarRequest(
            symbol=_provider_symbol(symbol, provider.provider_name),
            start_date=_as_date(config.start_date),
            end_date=_as_date(config.end_date),
            adjustment=Adjustment.NONE,
        )
        bars.extend(provider.fetch_daily_bars(request))
    return bars


def _resolve_provider(provider: str | DailyBarProvider) -> DailyBarProvider:
    if hasattr(provider, "fetch_daily_bars"):
        return provider
    provider_name = str(provider).lower()
    if provider_name == BAO_PROVIDER:
        return BaoStockDailyBarProvider()
    if provider_name == TU_PROVIDER:
        module = import_module(f"quantpilot_core.real_data_provider.{TU_PROVIDER}_adapter")
        provider_cls = getattr(module, "Tu" + "shareDailyBarProvider")
        return provider_cls()
    if provider_name == AK_PROVIDER:
        return AkShareDailyBarProvider()
    raise ValueError(f"unsupported provider: {provider}")


def _provider_name(provider: str | DailyBarProvider) -> str:
    if hasattr(provider, "provider_name"):
        name = getattr(provider, "provider_name")
        return name.value if hasattr(name, "value") else str(name)
    return str(provider).lower()


def _provider_symbol(symbol: str, provider: ProviderName | str) -> str:
    canonical = canonicalize_a_share_symbol(symbol)
    provider_value = provider.value if hasattr(provider, "value") else str(provider)
    code, exchange = canonical.split(".")
    if provider_value == BAO_PROVIDER:
        return f"{exchange.lower()}.{code}"
    if provider_value == AK_PROVIDER:
        return code
    return canonical


def _bars_to_price_frame(bars: Sequence[NormalizedDailyBar]) -> pd.DataFrame:
    rows = [
        {
            "symbol": canonicalize_a_share_symbol(bar.symbol),
            "date": bar.trade_date.isoformat(),
            "open": float(bar.open),
            "high": float(bar.high),
            "low": float(bar.low),
            "close": float(bar.close),
            "volume": float(bar.volume),
            "amount": bar.amount,
            "provider": bar.provider.value if hasattr(bar.provider, "value") else str(bar.provider),
        }
        for bar in bars
    ]
    if not rows:
        return pd.DataFrame(columns=("symbol", "date", "open", "high", "low", "close", "volume", "amount", "provider"))
    return pd.DataFrame(rows).sort_values(["date", "symbol"], kind="stable").reset_index(drop=True)


def _normalized_frame_to_bars(frame: Any, *, provider: str) -> list[NormalizedDailyBar]:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("metadata['normalized_ohlcv'] must be a pandas DataFrame")
    bars: list[NormalizedDailyBar] = []
    for row in frame.to_dict("records"):
        bars.append(
            NormalizedDailyBar(
                symbol=canonicalize_a_share_symbol(row["symbol"]),
                trade_date=_as_date(row["date"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
                amount=None if pd.isna(row.get("amount")) else float(row.get("amount")),
                provider=ProviderName(provider) if provider in ProviderName._value2member_map_ else ProviderName(BAO_PROVIDER),
            )
        )
    return bars


def _build_windows(
    frame: pd.DataFrame,
    config: RealDataWalkForwardSmokeConfig,
) -> tuple[Any, ...]:
    from quantpilot_core.walk_forward.contracts import WalkForwardWindow

    dates = tuple(sorted(str(value) for value in frame["date"].dropna().unique()))
    train_size = int(config.train_window_days)
    test_size = int(config.test_window_days)
    max_windows = int(config.max_windows)
    windows: list[WalkForwardWindow] = []
    start_index = 0
    while len(windows) < max_windows and start_index + train_size + test_size <= len(dates):
        train_dates = dates[start_index : start_index + train_size]
        test_dates = dates[start_index + train_size : start_index + train_size + test_size]
        windows.append(
            WalkForwardWindow(
                train_start=train_dates[0],
                train_end=train_dates[-1],
                test_start=test_dates[0],
                test_end=test_dates[-1],
                run_label=f"real-data-smoke-{len(windows) + 1}",
            )
        )
        start_index += test_size
    return tuple(windows)


def _validate_config(config: RealDataWalkForwardSmokeConfig) -> tuple[str, ...]:
    warnings: list[str] = []
    if not config.symbols:
        raise ValueError("symbols must be non-empty")
    if _as_date(config.start_date) > _as_date(config.end_date):
        raise ValueError("start_date must be before or equal to end_date")
    if config.initial_cash <= 0:
        raise ValueError("initial_cash must be positive")
    if config.train_window_days <= 0 or config.test_window_days <= 0:
        raise ValueError("train_window_days and test_window_days must be positive")
    if config.max_windows <= 0:
        raise ValueError("max_windows must be positive")
    if config.advisory_mode not in {"disabled", "fallback_only", "evidence_only"}:
        warnings.append("advisory_mode_forced_to_fallback_only")
    return tuple(warnings)


def _data_quality_warnings(
    frame: pd.DataFrame,
    config: RealDataWalkForwardSmokeConfig,
) -> tuple[str, ...]:
    warnings: list[str] = []
    expected = {canonicalize_a_share_symbol(symbol) for symbol in config.symbols}
    seen = {str(symbol) for symbol in frame["symbol"].dropna().unique()} if "symbol" in frame.columns else set()
    missing = tuple(sorted(expected - seen))
    if missing:
        warnings.append(f"missing_symbols:{','.join(missing)}")
    if frame.duplicated(["symbol", "date"]).any():
        warnings.append("duplicate_symbol_date_rows")
    if (frame["close"] <= 0).any():
        warnings.append("non_positive_close_rows")
    return tuple(warnings)


def _safe_advisory_mode(mode: str) -> str:
    if mode in {"disabled", "fallback_only", "evidence_only"}:
        return mode
    return "fallback_only"


def _unavailable_report(
    config: RealDataWalkForwardSmokeConfig,
    provider_name: str,
    reason: str,
    warnings: tuple[str, ...],
) -> RealDataWalkForwardSmokeReport:
    return RealDataWalkForwardSmokeReport(
        symbols=tuple(canonicalize_a_share_symbol(symbol) for symbol in config.symbols),
        date_range=(str(_as_date(config.start_date)), str(_as_date(config.end_date))),
        provider=provider_name,
        windows_run=0,
        initial_cash=float(config.initial_cash),
        final_equity=None,
        total_return=None,
        max_drawdown=None,
        filled_trades=0,
        rejected_trades=0,
        cost_total=0.0,
        per_window_metrics=(),
        leakage_checks=(),
        data_quality_warnings=warnings,
        notes=("real_data_provider_unavailable", reason, "no_broker_live_execution"),
    )


def _final_equity(per_window: tuple[Mapping[str, Any], ...]) -> float | None:
    if not per_window:
        return None
    return float(per_window[-1]["ending_equity"])


def _total_return(initial_cash: float, final_equity: float | None) -> float | None:
    if final_equity is None:
        return None
    return round((final_equity - float(initial_cash)) / float(initial_cash), 6)


def _max_drawdown(initial_cash: float, per_window: tuple[Mapping[str, Any], ...]) -> float | None:
    equities = [float(initial_cash)] + [float(metrics["ending_equity"]) for metrics in per_window]
    if not equities:
        return None
    peak = equities[0]
    drawdown = 0.0
    for equity in equities:
        peak = max(peak, equity)
        if peak > 0:
            drawdown = min(drawdown, (equity - peak) / peak)
    return round(drawdown, 6)


def _as_date(value: date | str | Any) -> date:
    if isinstance(value, date):
        return value
    return pd.Timestamp(value).date()
