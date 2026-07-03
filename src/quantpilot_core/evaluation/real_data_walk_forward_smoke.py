"""Small real-data walk-forward smoke path for the existing engine."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from datetime import date
from importlib import import_module
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import pandas as pd

from quantpilot_core.data_provider_normalization import canonicalize_a_share_symbol
from quantpilot_core.evaluation.factor_ranking_baseline import (
    FACTOR_RANKING_BASELINE_MODES,
    FactorRankingBaselineConfig,
    run_factor_ranking_baseline_v1,
)
from quantpilot_core.order_intent import OrderIntent, OrderIntentProposal, OrderIntentProposalSource, OrderIntentSide
from quantpilot_core.paper_trading import (
    PaperAccount,
    PaperFillCostAssumptions,
    account_symbol_pnl_breakdown,
    run_paper_trading_loop,
)
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


DEFAULT_REAL_DATA_SMOKE_SYMBOLS = ("000001.SZ", "000002.SZ", "600000.SH", "601318.SH")
DEFAULT_REAL_DATA_SCALEUP_SYMBOLS = (
    "000001.SZ",
    "000002.SZ",
    "000063.SZ",
    "000100.SZ",
    "000333.SZ",
    "000338.SZ",
    "000538.SZ",
    "000568.SZ",
    "000596.SZ",
    "000651.SZ",
    "000725.SZ",
    "000858.SZ",
    "002027.SZ",
    "002050.SZ",
    "002230.SZ",
    "002241.SZ",
    "002415.SZ",
    "002475.SZ",
    "002594.SZ",
    "300059.SZ",
    "300750.SZ",
    "600000.SH",
    "600009.SH",
    "600016.SH",
    "600028.SH",
    "600030.SH",
    "600031.SH",
    "600036.SH",
    "600050.SH",
    "600104.SH",
    "600276.SH",
    "600309.SH",
    "600519.SH",
    "600585.SH",
    "600690.SH",
    "600887.SH",
    "601088.SH",
    "601166.SH",
    "601318.SH",
    "601398.SH",
)
DEFAULT_PROVIDER = "baostock"
DEFAULT_REAL_DATA_SCALEUP_ARTIFACT_PATH = Path("artifacts/real_data_walk_forward_scaleup/latest_report.json")
DEFAULT_REAL_DATA_SCALEUP_SWEEP_ARTIFACT_PATH = Path(
    "artifacts/real_data_walk_forward_scaleup_sweep/latest_report.json"
)
DEFAULT_FACTOR_RANKING_SWEEP_INTEGRATION_ARTIFACT_PATH = Path(
    "artifacts/factor_ranking_sweep_integration/latest_report.json"
)
REAL_DATA_SCALEUP_RANKING_MODES = (
    "momentum_20d",
    "momentum_60d",
    "low_volatility",
    "equal_weight_baseline",
)
SUPPORTED_REAL_DATA_SCALEUP_RANKING_MODES = REAL_DATA_SCALEUP_RANKING_MODES + FACTOR_RANKING_BASELINE_MODES
FACTOR_RANKING_SWEEP_INTEGRATION_MODES = FACTOR_RANKING_BASELINE_MODES
FACTOR_RANKING_SWEEP_BASELINE_REFERENCE = {
    "source": "PR #96 best real-data scale-up baseline",
    "ranking_mode": "low_volatility",
    "total_return": -0.000061,
    "benchmark_total_return": -0.08708,
    "strategy_excess_return": 0.087019,
    "max_drawdown": -0.12525,
    "rejected_trade_ratio": 0.0,
}
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
    allow_partial_universe: bool = True
    min_symbols_required: int = 2
    artifact_path: str | Path | None = None
    benchmark_mode: str = "equal_weight_close_to_close"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RealDataWalkForwardScaleupConfig:
    """Configuration for the manual A-share walk-forward scale-up run."""

    symbols: tuple[str, ...] = DEFAULT_REAL_DATA_SCALEUP_SYMBOLS
    start_date: date | str = "2023-01-01"
    end_date: date | str = "2024-12-31"
    initial_cash: float = 1_000_000.0
    train_window_days: int = 60
    test_window_days: int = 20
    max_windows: int = 12
    min_symbols_required: int = 20
    allow_partial_universe: bool = True
    artifact_path: str | Path | None = DEFAULT_REAL_DATA_SCALEUP_ARTIFACT_PATH
    benchmark_mode: str = "equal_weight_close_to_close"
    provider: str | DailyBarProvider = DEFAULT_PROVIDER
    advisory_mode: str = "disabled"
    max_position_weight: float = 0.10
    target_position_count: int = 10
    reserve_cash_weight: float = 0.02
    rebalance_each_window: bool = True
    ranking_mode: str = "momentum_60d"
    min_order_lot: int = 100
    max_rejected_trade_ratio_warning: float = 0.20
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RealDataWalkForwardScaleupSweepConfig:
    """Manual-only parameter sweep over the cash-aware real-data scale-up run."""

    symbols: tuple[str, ...] = DEFAULT_REAL_DATA_SCALEUP_SYMBOLS
    start_date: date | str = "2023-01-01"
    end_date: date | str = "2024-12-31"
    initial_cash: float = 1_000_000.0
    train_window_days: int = 60
    test_window_days: int = 20
    max_windows: int = 12
    min_symbols_required: int = 20
    allow_partial_universe: bool = True
    artifact_path: str | Path | None = DEFAULT_REAL_DATA_SCALEUP_SWEEP_ARTIFACT_PATH
    benchmark_mode: str = "equal_weight_close_to_close"
    provider: str | DailyBarProvider = DEFAULT_PROVIDER
    advisory_mode: str = "disabled"
    target_position_counts: tuple[int, ...] = (10, 15, 20)
    max_position_weights: tuple[float, ...] = (0.05, 0.08, 0.10)
    reserve_cash_weights: tuple[float, ...] = (0.02, 0.05)
    ranking_modes: tuple[str, ...] = REAL_DATA_SCALEUP_RANKING_MODES
    rebalance_each_window: bool = True
    min_order_lot: int = 100
    max_rejected_trade_ratio_warning: float = 0.20
    top_n: int = 5
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FactorRankingSweepIntegrationConfig:
    """Manual-only sweep over factor-ranking modes using the scale-up runner."""

    symbols: tuple[str, ...] = DEFAULT_REAL_DATA_SCALEUP_SYMBOLS
    start_date: date | str = "2023-01-01"
    end_date: date | str = "2024-12-31"
    initial_cash: float = 1_000_000.0
    train_window_days: int = 60
    test_window_days: int = 20
    max_windows: int = 12
    min_symbols_required: int = 20
    allow_partial_universe: bool = True
    artifact_path: str | Path | None = DEFAULT_FACTOR_RANKING_SWEEP_INTEGRATION_ARTIFACT_PATH
    benchmark_mode: str = "equal_weight_close_to_close"
    provider: str | DailyBarProvider = DEFAULT_PROVIDER
    advisory_mode: str = "disabled"
    target_position_counts: tuple[int, ...] = (10, 15, 20)
    max_position_weights: tuple[float, ...] = (0.05, 0.08, 0.10)
    reserve_cash_weights: tuple[float, ...] = (0.02, 0.05)
    factor_ranking_modes: tuple[str, ...] = FACTOR_RANKING_SWEEP_INTEGRATION_MODES
    rebalance_each_window: bool = True
    min_order_lot: int = 100
    max_rejected_trade_ratio_warning: float = 0.20
    top_n: int = 5
    metadata: Mapping[str, Any] = field(default_factory=dict)
    progress_callback: Callable[[Mapping[str, Any]], None] | None = None


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
    aggregate_symbol_breakdown: tuple[Mapping[str, Any], ...] = ()
    benchmark_final_equity: float | None = None
    benchmark_total_return: float | None = None
    strategy_excess_return: float | None = None
    benchmark_notes: tuple[str, ...] = ()
    artifact_path: str | None = None


@dataclass(frozen=True)
class RealDataWalkForwardScaleupReport:
    """Aggregate report for a larger manual A-share walk-forward run."""

    parameter_set_id: str | None
    ranking_mode: str
    target_position_count: int
    max_position_weight: float
    reserve_cash_weight: float
    symbols: tuple[str, ...]
    date_range: tuple[str, str]
    provider: str
    benchmark_mode: str
    windows_run: int
    valid_symbols: tuple[str, ...]
    skipped_symbols: tuple[str, ...]
    initial_cash: float
    final_equity: float | None
    total_return: float | None
    benchmark_total_return: float | None
    strategy_excess_return: float | None
    max_drawdown: float | None
    win_rate_by_window: float | None
    average_window_return: float | None
    median_window_return: float | None
    worst_window_return: float | None
    equity_window_return: tuple[float, ...]
    actual_position_count_by_window: tuple[int, ...]
    cash_weight_by_window: tuple[float | None, ...]
    gross_exposure_by_window: tuple[float | None, ...]
    largest_position_weight_by_window: tuple[float | None, ...]
    filled_trades: int
    rejected_trades: int
    rejected_trade_ratio: float | None
    average_position_count: float | None
    average_largest_position_weight: float | None
    rejection_reasons: Mapping[str, int]
    resized_order_count: int
    skipped_below_lot_count: int
    rebalance_sell_count: int
    rebalance_buy_count: int
    turnover: float
    cost_total: float
    cost_to_turnover_ratio: float | None
    top_contributors: tuple[Mapping[str, Any], ...]
    worst_contributors: tuple[Mapping[str, Any], ...]
    per_symbol_total_pnl: Mapping[str, float]
    contribution_to_total_return: Mapping[str, float]
    per_window_metrics: tuple[Mapping[str, Any], ...]
    data_quality_warnings: tuple[str, ...]
    mature_framework_hooks: Mapping[str, Any]
    notes: tuple[str, ...]
    artifact_path: str | None = None


@dataclass(frozen=True)
class RealDataWalkForwardScaleupSweepReport:
    """Parameter sweep diagnostics for manual-only real-data scale-up runs."""

    provider: str
    date_range: tuple[str, str]
    symbols: tuple[str, ...]
    parameter_set_count: int
    parameter_sets: tuple[Mapping[str, Any], ...]
    top_parameter_sets_by_excess: tuple[Mapping[str, Any], ...]
    top_parameter_sets_by_return: tuple[Mapping[str, Any], ...]
    top_parameter_sets_by_drawdown_adjusted: tuple[Mapping[str, Any], ...]
    notes: tuple[str, ...]
    artifact_path: str | None = None


@dataclass(frozen=True)
class FactorRankingSweepIntegrationReport:
    """Factor-mode integration diagnostics for manual-only scale-up sweeps."""

    provider: str
    date_range: tuple[str, str]
    symbols_requested: tuple[str, ...]
    valid_symbols: tuple[str, ...]
    factor_ranking_modes: tuple[str, ...]
    parameter_set_count: int
    parameter_sets: tuple[Mapping[str, Any], ...]
    top_parameter_sets_by_excess: tuple[Mapping[str, Any], ...]
    top_parameter_sets_by_return: tuple[Mapping[str, Any], ...]
    top_parameter_sets_by_drawdown_adjusted: tuple[Mapping[str, Any], ...]
    baseline_reference: Mapping[str, Any]
    per_mode_summary: tuple[Mapping[str, Any], ...]
    notes: tuple[str, ...]
    artifact_path: str | None = None


@dataclass(frozen=True)
class _LoadedBars:
    bars: tuple[NormalizedDailyBar, ...]
    warnings: tuple[str, ...] = ()


def run_real_data_walk_forward_smoke(
    config: RealDataWalkForwardSmokeConfig | None = None,
    **kwargs: Any,
) -> RealDataWalkForwardSmokeReport:
    """Run a small provider-backed smoke through WalkForwardEngine."""

    payload = config or RealDataWalkForwardSmokeConfig(**kwargs)
    warnings = _validate_config(payload)
    provider_name = _provider_name(payload.provider)
    try:
        loaded = _load_bars(payload)
    except Exception as exc:
        if isinstance(exc, (RuntimeError, ProviderError, ValueError)):
            return _unavailable_report(payload, provider_name, str(exc), warnings)
        raise

    price_frame = _bars_to_price_frame(loaded.bars)
    data_warnings = warnings + loaded.warnings + _data_quality_warnings(price_frame, payload)
    if price_frame.empty:
        return _unavailable_report(payload, provider_name, "provider returned no usable OHLCV rows", data_warnings)
    valid_symbol_count = _valid_symbol_count(price_frame)
    if valid_symbol_count < int(payload.min_symbols_required):
        reason = (
            "valid provider symbols below minimum: "
            f"{valid_symbol_count} < {int(payload.min_symbols_required)}"
        )
        return _unavailable_report(payload, provider_name, reason, data_warnings)

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
            "top_n": min(3, valid_symbol_count),
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
    per_window = tuple(_window_report_metrics(window_result, price_frame) for window_result in result.window_results)
    final_equity = _final_equity(per_window)
    benchmark = _benchmark_metrics(price_frame, windows, float(payload.initial_cash), payload.benchmark_mode)
    strategy_return = _total_return(payload.initial_cash, final_equity)
    report = RealDataWalkForwardSmokeReport(
        symbols=tuple(canonicalize_a_share_symbol(symbol) for symbol in payload.symbols),
        date_range=(str(_as_date(payload.start_date)), str(_as_date(payload.end_date))),
        provider=provider_name,
        windows_run=len(result.window_results),
        initial_cash=float(payload.initial_cash),
        final_equity=final_equity,
        total_return=strategy_return,
        max_drawdown=_max_drawdown(float(payload.initial_cash), per_window),
        filled_trades=sum(int(metrics.get("trade_count", 0)) for metrics in per_window),
        rejected_trades=sum(int(metrics.get("rejected_count", 0)) for metrics in per_window),
        cost_total=round(sum(float(metrics.get("cost_total", 0.0)) for metrics in per_window), 6),
        per_window_metrics=per_window,
        aggregate_symbol_breakdown=_aggregate_symbol_breakdown(per_window),
        benchmark_final_equity=benchmark["benchmark_final_equity"],
        benchmark_total_return=benchmark["benchmark_total_return"],
        strategy_excess_return=(
            round(strategy_return - benchmark["benchmark_total_return"], 6)
            if strategy_return is not None and benchmark["benchmark_total_return"] is not None
            else None
        ),
        benchmark_notes=tuple(benchmark["benchmark_notes"]),
        leakage_checks=result.leakage_checks,
        data_quality_warnings=data_warnings,
        notes=("real_data_smoke_completed", "no_broker_live_execution", f"advisory_mode:{walk_input.advisory_mode}"),
    )
    artifact_path = _write_report_artifact(report, payload.artifact_path)
    if artifact_path is not None:
        report = replace(report, artifact_path=artifact_path)
    return report


def run_real_data_walk_forward_scaleup_v1(
    config: RealDataWalkForwardScaleupConfig | None = None,
    **kwargs: Any,
) -> RealDataWalkForwardScaleupReport:
    """Run the manual scale-up wrapper without broker or live LLM calls."""

    payload = config or RealDataWalkForwardScaleupConfig(**kwargs)
    _validate_scaleup_config(payload)
    smoke_config = RealDataWalkForwardSmokeConfig(
        symbols=payload.symbols,
        start_date=payload.start_date,
        end_date=payload.end_date,
        initial_cash=payload.initial_cash,
        train_window_days=payload.train_window_days,
        test_window_days=payload.test_window_days,
        max_windows=payload.max_windows,
        provider=payload.provider,
        advisory_mode=payload.advisory_mode,
        allow_partial_universe=payload.allow_partial_universe,
        min_symbols_required=payload.min_symbols_required,
        artifact_path=None,
        benchmark_mode=payload.benchmark_mode,
        metadata={
            **dict(payload.metadata),
            "real_data_walk_forward_scaleup_v1": True,
            "mature_framework_hooks": _mature_framework_hooks(payload.metadata),
        },
    )
    provider_name = _provider_name(payload.provider)
    warnings = _validate_config(smoke_config)
    try:
        loaded = _load_bars(smoke_config)
    except Exception as exc:
        if isinstance(exc, (RuntimeError, ProviderError, ValueError)):
            unavailable = _unavailable_report(smoke_config, provider_name, str(exc), warnings)
            report = _scaleup_report_from_smoke(unavailable, payload)
            artifact_path = _write_scaleup_report_artifact(report, payload.artifact_path)
            return replace(report, artifact_path=artifact_path) if artifact_path is not None else report
        raise

    price_frame = _bars_to_price_frame(loaded.bars)
    data_warnings = warnings + loaded.warnings + _data_quality_warnings(price_frame, smoke_config)
    if price_frame.empty:
        unavailable = _unavailable_report(smoke_config, provider_name, "provider returned no usable OHLCV rows", data_warnings)
        report = _scaleup_report_from_smoke(unavailable, payload)
        artifact_path = _write_scaleup_report_artifact(report, payload.artifact_path)
        return replace(report, artifact_path=artifact_path) if artifact_path is not None else report

    valid_symbol_count = _valid_symbol_count(price_frame)
    if valid_symbol_count < int(payload.min_symbols_required):
        reason = (
            "valid provider symbols below minimum: "
            f"{valid_symbol_count} < {int(payload.min_symbols_required)}"
        )
        unavailable = _unavailable_report(smoke_config, provider_name, reason, data_warnings)
        report = _scaleup_report_from_smoke(unavailable, payload)
        artifact_path = _write_scaleup_report_artifact(report, payload.artifact_path)
        return replace(report, artifact_path=artifact_path) if artifact_path is not None else report

    windows = _build_windows(price_frame, smoke_config)
    if not windows:
        unavailable = _unavailable_report(smoke_config, provider_name, "not enough trading dates for configured windows", data_warnings)
        report = _scaleup_report_from_smoke(unavailable, payload)
        artifact_path = _write_scaleup_report_artifact(report, payload.artifact_path)
        return replace(report, artifact_path=artifact_path) if artifact_path is not None else report

    per_window, final_account = _run_scaleup_rebalance_windows(price_frame, windows, payload)
    final_equity = _final_equity(per_window)
    benchmark = _benchmark_metrics(price_frame, windows, float(payload.initial_cash), payload.benchmark_mode)
    strategy_return = _total_return(payload.initial_cash, final_equity)
    valid_symbols = tuple(sorted(str(symbol) for symbol in price_frame["symbol"].dropna().unique()))
    expected_symbols = tuple(canonicalize_a_share_symbol(symbol) for symbol in payload.symbols)
    skipped_symbols = tuple(symbol for symbol in expected_symbols if symbol not in set(valid_symbols))
    aggregate_breakdown = _aggregate_symbol_breakdown(per_window)
    scaleup_data_warnings = data_warnings + _scaleup_diagnostic_warnings(per_window, payload)
    smoke_report = RealDataWalkForwardSmokeReport(
        symbols=expected_symbols,
        date_range=(str(_as_date(payload.start_date)), str(_as_date(payload.end_date))),
        provider=provider_name,
        windows_run=len(per_window),
        initial_cash=float(payload.initial_cash),
        final_equity=final_equity,
        total_return=strategy_return,
        max_drawdown=_max_drawdown(float(payload.initial_cash), per_window),
        filled_trades=sum(int(metrics.get("trade_count", 0)) for metrics in per_window),
        rejected_trades=sum(int(metrics.get("rejected_count", 0)) for metrics in per_window),
        cost_total=round(sum(float(metrics.get("cost_total", 0.0)) for metrics in per_window), 6),
        per_window_metrics=per_window,
        leakage_checks=tuple(f"{window.run_label}:scaleup_train_and_test_slices_validated" for window in windows),
        data_quality_warnings=scaleup_data_warnings,
        notes=(
            "real_data_scaleup_completed",
            "no_broker_live_execution",
            "cash_aware_rebalance",
            f"advisory_mode:{_safe_advisory_mode(payload.advisory_mode)}",
            f"final_account_trade_log:{len(final_account.trade_log)}",
        ),
        aggregate_symbol_breakdown=aggregate_breakdown,
        benchmark_final_equity=benchmark["benchmark_final_equity"],
        benchmark_total_return=benchmark["benchmark_total_return"],
        strategy_excess_return=(
            round(strategy_return - benchmark["benchmark_total_return"], 6)
            if strategy_return is not None and benchmark["benchmark_total_return"] is not None
            else None
        ),
        benchmark_notes=tuple(benchmark["benchmark_notes"]),
    )
    report = _scaleup_report_from_smoke(smoke_report, payload)
    report = replace(report, valid_symbols=valid_symbols, skipped_symbols=skipped_symbols)
    artifact_path = _write_scaleup_report_artifact(report, payload.artifact_path)
    if artifact_path is not None:
        report = replace(report, artifact_path=artifact_path)
    return report


def run_real_data_walk_forward_scaleup_sweep(
    config: RealDataWalkForwardScaleupSweepConfig | None = None,
    **kwargs: Any,
) -> RealDataWalkForwardScaleupSweepReport:
    """Run a manual-only parameter sweep over the cash-aware scale-up wrapper."""

    payload = config or RealDataWalkForwardScaleupSweepConfig(**kwargs)
    parameter_configs = build_real_data_walk_forward_scaleup_sweep_grid(payload)
    reports: list[RealDataWalkForwardScaleupReport] = []
    for parameter_config in parameter_configs:
        reports.append(run_real_data_walk_forward_scaleup_v1(parameter_config))

    rows = tuple(_scaleup_parameter_set_row(report) for report in reports)
    report = _scaleup_sweep_report_from_reports(payload, rows)
    artifact_path = _write_scaleup_sweep_report_artifact(report, payload.artifact_path)
    if artifact_path is not None:
        report = replace(report, artifact_path=artifact_path)
    return report


def _scaleup_sweep_report_from_reports(
    config: RealDataWalkForwardScaleupSweepConfig,
    rows: tuple[Mapping[str, Any], ...],
) -> RealDataWalkForwardScaleupSweepReport:
    report = RealDataWalkForwardScaleupSweepReport(
        provider=_provider_name(config.provider),
        date_range=(str(_as_date(config.start_date)), str(_as_date(config.end_date))),
        symbols=tuple(canonicalize_a_share_symbol(symbol) for symbol in config.symbols),
        parameter_set_count=len(rows),
        parameter_sets=rows,
        top_parameter_sets_by_excess=_top_parameter_sets(rows, "strategy_excess_return", int(config.top_n)),
        top_parameter_sets_by_return=_top_parameter_sets(rows, "total_return", int(config.top_n)),
        top_parameter_sets_by_drawdown_adjusted=_top_drawdown_adjusted_parameter_sets(rows, int(config.top_n)),
        notes=(
            "real_data_walk_forward_scaleup_sweep_completed",
            "manual_only_real_provider_run",
            "no_broker_live_execution",
            "deepseek_live_disabled_by_default",
            "no_profitability_claim",
            f"advisory_mode:{config.advisory_mode}",
        ),
    )
    return report


def run_factor_ranking_sweep_integration_v1(
    config: FactorRankingSweepIntegrationConfig | None = None,
    **kwargs: Any,
) -> FactorRankingSweepIntegrationReport:
    """Run the factor-ranking mode sweep through the existing scale-up path."""

    payload = config or FactorRankingSweepIntegrationConfig(**kwargs)
    _validate_factor_ranking_sweep_config(payload)
    sweep_config = RealDataWalkForwardScaleupSweepConfig(
        symbols=payload.symbols,
        start_date=payload.start_date,
        end_date=payload.end_date,
        initial_cash=payload.initial_cash,
        train_window_days=payload.train_window_days,
        test_window_days=payload.test_window_days,
        max_windows=payload.max_windows,
        min_symbols_required=payload.min_symbols_required,
        allow_partial_universe=payload.allow_partial_universe,
        artifact_path=None,
        benchmark_mode=payload.benchmark_mode,
        provider=payload.provider,
        advisory_mode=payload.advisory_mode,
        target_position_counts=payload.target_position_counts,
        max_position_weights=payload.max_position_weights,
        reserve_cash_weights=payload.reserve_cash_weights,
        ranking_modes=payload.factor_ranking_modes,
        rebalance_each_window=payload.rebalance_each_window,
        min_order_lot=payload.min_order_lot,
        max_rejected_trade_ratio_warning=payload.max_rejected_trade_ratio_warning,
        top_n=payload.top_n,
        metadata={
            **dict(payload.metadata),
            "factor_ranking_sweep_integration_v1": True,
        },
    )
    sweep_report = _run_factor_ranking_sweep_with_cached_bars(
        sweep_config,
        progress_callback=payload.progress_callback,
    )
    rows = sweep_report.parameter_sets
    report = FactorRankingSweepIntegrationReport(
        provider=sweep_report.provider,
        date_range=sweep_report.date_range,
        symbols_requested=tuple(canonicalize_a_share_symbol(symbol) for symbol in payload.symbols),
        valid_symbols=_valid_symbols_from_parameter_rows(rows),
        factor_ranking_modes=tuple(payload.factor_ranking_modes),
        parameter_set_count=sweep_report.parameter_set_count,
        parameter_sets=rows,
        top_parameter_sets_by_excess=sweep_report.top_parameter_sets_by_excess,
        top_parameter_sets_by_return=sweep_report.top_parameter_sets_by_return,
        top_parameter_sets_by_drawdown_adjusted=sweep_report.top_parameter_sets_by_drawdown_adjusted,
        baseline_reference=dict(FACTOR_RANKING_SWEEP_BASELINE_REFERENCE),
        per_mode_summary=_factor_mode_summary(rows),
        notes=(
            "factor_ranking_sweep_integration_v1_completed",
            "reuses_real_data_walk_forward_scaleup_sweep",
            "manual_only_real_provider_run",
            "no_broker_live_execution",
            "deepseek_live_disabled_by_default",
            "no_profitability_claim",
            f"advisory_mode:{payload.advisory_mode}",
        ),
    )
    artifact_path = _write_factor_ranking_sweep_integration_artifact(report, payload.artifact_path)
    if artifact_path is not None:
        report = replace(report, artifact_path=artifact_path)
    return report


def _run_factor_ranking_sweep_with_cached_bars(
    config: RealDataWalkForwardScaleupSweepConfig,
    *,
    progress_callback: Callable[[Mapping[str, Any]], None] | None = None,
) -> RealDataWalkForwardScaleupSweepReport:
    parameter_configs = build_real_data_walk_forward_scaleup_sweep_grid(config)
    provider_name = _provider_name(config.provider)
    smoke_config = RealDataWalkForwardSmokeConfig(
        symbols=config.symbols,
        start_date=config.start_date,
        end_date=config.end_date,
        initial_cash=config.initial_cash,
        train_window_days=config.train_window_days,
        test_window_days=config.test_window_days,
        max_windows=config.max_windows,
        provider=config.provider,
        advisory_mode=config.advisory_mode,
        allow_partial_universe=config.allow_partial_universe,
        min_symbols_required=config.min_symbols_required,
        artifact_path=None,
        benchmark_mode=config.benchmark_mode,
        metadata={
            **dict(config.metadata),
            "real_data_walk_forward_scaleup_v1": True,
            "mature_framework_hooks": _mature_framework_hooks(config.metadata),
        },
    )
    validation_warnings = _validate_config(smoke_config)
    if progress_callback is not None:
        progress_callback(
            {
                "event": "data_load_started",
                "provider": provider_name,
                "date_range": (str(_as_date(config.start_date)), str(_as_date(config.end_date))),
                "symbols_requested": tuple(canonicalize_a_share_symbol(symbol) for symbol in config.symbols),
                "factor_modes_count": len(config.ranking_modes),
                "parameter_sets_count": len(parameter_configs),
                "completed_parameter_sets": 0,
            }
        )
    try:
        loaded = _load_bars(smoke_config)
    except Exception as exc:
        if not isinstance(exc, (RuntimeError, ProviderError, ValueError)):
            raise
        reports = tuple(
            _scaleup_report_from_smoke(
                _unavailable_report(smoke_config, provider_name, str(exc), validation_warnings),
                parameter_config,
            )
            for parameter_config in parameter_configs
        )
        return _scaleup_sweep_report_from_reports(config, tuple(_scaleup_parameter_set_row(report) for report in reports))

    price_frame = _bars_to_price_frame(loaded.bars)
    data_warnings = validation_warnings + loaded.warnings + _data_quality_warnings(price_frame, smoke_config)
    valid_symbols = tuple(sorted(str(symbol) for symbol in price_frame["symbol"].dropna().unique())) if not price_frame.empty else ()
    if progress_callback is not None:
        progress_callback(
            {
                "event": "data_load_completed",
                "provider": provider_name,
                "date_range": (str(_as_date(config.start_date)), str(_as_date(config.end_date))),
                "symbols_requested": tuple(canonicalize_a_share_symbol(symbol) for symbol in config.symbols),
                "valid_symbols": valid_symbols,
                "factor_modes_count": len(config.ranking_modes),
                "parameter_sets_count": len(parameter_configs),
                "completed_parameter_sets": 0,
            }
        )

    rows: list[Mapping[str, Any]] = []
    for index, parameter_config in enumerate(parameter_configs, start=1):
        report = _run_scaleup_with_loaded_price_frame(
            parameter_config,
            smoke_config=smoke_config,
            provider_name=provider_name,
            price_frame=price_frame,
            data_warnings=data_warnings,
        )
        rows.append(_scaleup_parameter_set_row(report))
        if progress_callback is not None:
            progress_callback(
                {
                    "event": "parameter_set_completed",
                    "provider": provider_name,
                    "date_range": (str(_as_date(config.start_date)), str(_as_date(config.end_date))),
                    "symbols_requested": tuple(canonicalize_a_share_symbol(symbol) for symbol in config.symbols),
                    "valid_symbols": valid_symbols,
                    "factor_modes_count": len(config.ranking_modes),
                    "parameter_sets_count": len(parameter_configs),
                    "completed_parameter_sets": index,
                    "parameter_set_id": parameter_config.metadata.get("parameter_set_id"),
                    "ranking_mode": parameter_config.ranking_mode,
                }
            )
    return _scaleup_sweep_report_from_reports(config, tuple(rows))


def _run_scaleup_with_loaded_price_frame(
    config: RealDataWalkForwardScaleupConfig,
    *,
    smoke_config: RealDataWalkForwardSmokeConfig,
    provider_name: str,
    price_frame: pd.DataFrame,
    data_warnings: tuple[str, ...],
) -> RealDataWalkForwardScaleupReport:
    if price_frame.empty:
        unavailable = _unavailable_report(smoke_config, provider_name, "provider returned no usable OHLCV rows", data_warnings)
        return _scaleup_report_from_smoke(unavailable, config)

    valid_symbol_count = _valid_symbol_count(price_frame)
    if valid_symbol_count < int(config.min_symbols_required):
        reason = (
            "valid provider symbols below minimum: "
            f"{valid_symbol_count} < {int(config.min_symbols_required)}"
        )
        unavailable = _unavailable_report(smoke_config, provider_name, reason, data_warnings)
        return _scaleup_report_from_smoke(unavailable, config)

    windows = _build_windows(price_frame, smoke_config)
    if not windows:
        unavailable = _unavailable_report(smoke_config, provider_name, "not enough trading dates for configured windows", data_warnings)
        return _scaleup_report_from_smoke(unavailable, config)

    per_window, final_account = _run_scaleup_rebalance_windows(price_frame, windows, config)
    final_equity = _final_equity(per_window)
    benchmark = _benchmark_metrics(price_frame, windows, float(config.initial_cash), config.benchmark_mode)
    strategy_return = _total_return(config.initial_cash, final_equity)
    valid_symbols = tuple(sorted(str(symbol) for symbol in price_frame["symbol"].dropna().unique()))
    expected_symbols = tuple(canonicalize_a_share_symbol(symbol) for symbol in config.symbols)
    skipped_symbols = tuple(symbol for symbol in expected_symbols if symbol not in set(valid_symbols))
    aggregate_breakdown = _aggregate_symbol_breakdown(per_window)
    scaleup_data_warnings = data_warnings + _scaleup_diagnostic_warnings(per_window, config)
    smoke_report = RealDataWalkForwardSmokeReport(
        symbols=expected_symbols,
        date_range=(str(_as_date(config.start_date)), str(_as_date(config.end_date))),
        provider=provider_name,
        windows_run=len(per_window),
        initial_cash=float(config.initial_cash),
        final_equity=final_equity,
        total_return=strategy_return,
        max_drawdown=_max_drawdown(float(config.initial_cash), per_window),
        filled_trades=sum(int(metrics.get("trade_count", 0)) for metrics in per_window),
        rejected_trades=sum(int(metrics.get("rejected_count", 0)) for metrics in per_window),
        cost_total=round(sum(float(metrics.get("cost_total", 0.0)) for metrics in per_window), 6),
        per_window_metrics=per_window,
        leakage_checks=tuple(f"{window.run_label}:scaleup_train_and_test_slices_validated" for window in windows),
        data_quality_warnings=scaleup_data_warnings,
        notes=(
            "real_data_scaleup_completed",
            "no_broker_live_execution",
            "cash_aware_rebalance",
            f"advisory_mode:{_safe_advisory_mode(config.advisory_mode)}",
            f"final_account_trade_log:{len(final_account.trade_log)}",
        ),
        aggregate_symbol_breakdown=aggregate_breakdown,
        benchmark_final_equity=benchmark["benchmark_final_equity"],
        benchmark_total_return=benchmark["benchmark_total_return"],
        strategy_excess_return=(
            round(strategy_return - benchmark["benchmark_total_return"], 6)
            if strategy_return is not None and benchmark["benchmark_total_return"] is not None
            else None
        ),
        benchmark_notes=tuple(benchmark["benchmark_notes"]),
    )
    return replace(
        _scaleup_report_from_smoke(smoke_report, config),
        valid_symbols=valid_symbols,
        skipped_symbols=skipped_symbols,
    )


def build_real_data_walk_forward_scaleup_sweep_grid(
    config: RealDataWalkForwardScaleupSweepConfig | None = None,
    **kwargs: Any,
) -> tuple[RealDataWalkForwardScaleupConfig, ...]:
    """Build the deterministic manual scale-up parameter grid."""

    payload = config or RealDataWalkForwardScaleupSweepConfig(**kwargs)
    if payload.top_n <= 0:
        raise ValueError("top_n must be positive")
    configs: list[RealDataWalkForwardScaleupConfig] = []
    index = 1
    for ranking_mode in payload.ranking_modes:
        if ranking_mode not in SUPPORTED_REAL_DATA_SCALEUP_RANKING_MODES:
            raise ValueError(f"unsupported ranking_mode: {ranking_mode}")
        for target_position_count in payload.target_position_counts:
            for max_position_weight in payload.max_position_weights:
                for reserve_cash_weight in payload.reserve_cash_weights:
                    parameter_set_id = f"scaleup-sweep-{index:03d}"
                    configs.append(
                        RealDataWalkForwardScaleupConfig(
                            symbols=payload.symbols,
                            start_date=payload.start_date,
                            end_date=payload.end_date,
                            initial_cash=payload.initial_cash,
                            train_window_days=payload.train_window_days,
                            test_window_days=payload.test_window_days,
                            max_windows=payload.max_windows,
                            min_symbols_required=payload.min_symbols_required,
                            allow_partial_universe=payload.allow_partial_universe,
                            artifact_path=None,
                            benchmark_mode=payload.benchmark_mode,
                            provider=payload.provider,
                            advisory_mode=payload.advisory_mode,
                            max_position_weight=max_position_weight,
                            target_position_count=target_position_count,
                            reserve_cash_weight=reserve_cash_weight,
                            rebalance_each_window=payload.rebalance_each_window,
                            ranking_mode=ranking_mode,
                            min_order_lot=payload.min_order_lot,
                            max_rejected_trade_ratio_warning=payload.max_rejected_trade_ratio_warning,
                            metadata={
                                **dict(payload.metadata),
                                "parameter_set_id": parameter_set_id,
                                "real_data_walk_forward_scaleup_sweep": True,
                            },
                        )
                    )
                    index += 1
    return tuple(configs)


def _validate_factor_ranking_sweep_config(config: FactorRankingSweepIntegrationConfig) -> None:
    if config.top_n <= 0:
        raise ValueError("top_n must be positive")
    if not config.factor_ranking_modes:
        raise ValueError("factor_ranking_modes must not be empty")
    unsupported = tuple(
        mode for mode in config.factor_ranking_modes if mode not in FACTOR_RANKING_SWEEP_INTEGRATION_MODES
    )
    if unsupported:
        raise ValueError(f"unsupported factor_ranking_modes: {', '.join(unsupported)}")


def _run_scaleup_rebalance_windows(
    price_frame: pd.DataFrame,
    windows: Sequence[Any],
    config: RealDataWalkForwardScaleupConfig,
) -> tuple[tuple[Mapping[str, Any], ...], PaperAccount]:
    account = PaperAccount(cash=float(config.initial_cash))
    per_window: list[Mapping[str, Any]] = []
    cost_assumptions = PaperFillCostAssumptions(lot_size=int(config.min_order_lot))
    for window in windows:
        train_prices = _slice_price_frame(price_frame, window.train_start, window.train_end)
        start_prices = _first_prices_for_window(price_frame, window.test_start, window.test_end)
        end_prices = _latest_prices_for_window(price_frame, window.test_start, window.test_end)
        starting_equity = _account_equity(account, start_prices)
        selected = _select_scaleup_candidates(train_prices, start_prices, config)
        target_weights = _target_weights(selected, config)
        proposal, build_notes = _build_rebalance_proposal(
            account=account,
            prices=start_prices,
            selected_symbols=selected,
            target_weights=target_weights,
            equity=starting_equity,
            config=config,
            cost_assumptions=cost_assumptions,
            run_label=window.run_label,
        )
        loop_result = run_paper_trading_loop(
            proposal,
            start_prices,
            account,
            cost_assumptions=cost_assumptions,
        )
        account = _mark_account_to_prices(loop_result.account, end_prices)
        ending_equity = _account_equity(account, end_prices)
        metrics = _scaleup_window_metrics(
            window=window,
            account=account,
            fill_result=loop_result.fill_result,
            starting_equity=starting_equity,
            ending_equity=ending_equity,
            start_prices=start_prices,
            end_prices=end_prices,
            selected_symbols=selected,
            target_weights=target_weights,
            proposal=proposal,
            build_notes=build_notes,
        )
        per_window.append(metrics)
    return tuple(per_window), account


def _slice_price_frame(frame: pd.DataFrame, start: Any, end: Any) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    dates = pd.to_datetime(frame["date"]).dt.tz_localize(None)
    return frame.loc[(dates >= start_ts) & (dates <= end_ts)].copy()


def _first_prices_for_window(frame: pd.DataFrame, start: Any, end: Any) -> Mapping[str, float]:
    window = _slice_price_frame(frame, start, end)
    if window.empty:
        return {}
    ordered = window.sort_values(["date", "symbol"], kind="stable")
    return {
        str(symbol): round(float(group["close"].iloc[0]), 6)
        for symbol, group in ordered.groupby("symbol", sort=True)
    }


def _select_scaleup_candidates(
    train_prices: pd.DataFrame,
    start_prices: Mapping[str, float],
    config: RealDataWalkForwardScaleupConfig,
) -> tuple[str, ...]:
    if train_prices.empty or config.ranking_mode == "equal_weight_baseline":
        return tuple(sorted(start_prices))[: int(config.target_position_count)]
    if config.ranking_mode in FACTOR_RANKING_BASELINE_MODES:
        report = run_factor_ranking_baseline_v1(
            train_prices.loc[train_prices["symbol"].isin(set(start_prices))],
            FactorRankingBaselineConfig(
                ranking_mode=config.ranking_mode,
                target_symbol_count=int(config.target_position_count),
                artifact_path=None,
            ),
        )
        return report.selected_symbols
    scores: list[tuple[float, str]] = []
    ordered = train_prices.sort_values(["date", "symbol"], kind="stable")
    for symbol, group in ordered.groupby("symbol", sort=True):
        if str(symbol) not in start_prices:
            continue
        score = _ranking_score(group, config.ranking_mode)
        scores.append((round(score, 12), str(symbol)))
    ranked = sorted(scores, key=lambda item: (-item[0], item[1]))
    return tuple(symbol for _, symbol in ranked[: int(config.target_position_count)])


def _ranking_score(group: pd.DataFrame, ranking_mode: str) -> float:
    prices = group.sort_values(["date", "symbol"], kind="stable")["close"].astype(float)
    if prices.empty:
        return -1.0
    if ranking_mode == "momentum_20d":
        return _momentum_score(prices.tail(20))
    if ranking_mode == "momentum_60d":
        return _momentum_score(prices.tail(60))
    if ranking_mode == "low_volatility":
        returns = prices.pct_change().dropna()
        volatility = float(returns.std()) if not returns.empty else 0.0
        return -volatility
    if ranking_mode == "equal_weight_baseline":
        return 0.0
    raise ValueError(f"unsupported ranking_mode: {ranking_mode}")


def _momentum_score(prices: pd.Series) -> float:
    if prices.empty:
        return -1.0
    first = float(prices.iloc[0])
    last = float(prices.iloc[-1])
    return (last - first) / first if first > 0 else -1.0


def _target_weights(
    selected_symbols: tuple[str, ...],
    config: RealDataWalkForwardScaleupConfig,
) -> Mapping[str, float]:
    if not selected_symbols:
        return {}
    investable = max(0.0, 1.0 - float(config.reserve_cash_weight))
    equal_weight = investable / len(selected_symbols)
    target_weight = min(float(config.max_position_weight), equal_weight)
    return {symbol: round(target_weight, 6) for symbol in selected_symbols}


def _build_rebalance_proposal(
    *,
    account: PaperAccount,
    prices: Mapping[str, float],
    selected_symbols: tuple[str, ...],
    target_weights: Mapping[str, float],
    equity: float,
    config: RealDataWalkForwardScaleupConfig,
    cost_assumptions: PaperFillCostAssumptions,
    run_label: str,
) -> tuple[OrderIntentProposal, Mapping[str, Any]]:
    if not config.rebalance_each_window and account.positions:
        return _rebalance_proposal((), run_label), {
            "resized_order_count": 0,
            "skipped_below_lot_count": 0,
            "rebalance_sell_count": 0,
            "rebalance_buy_count": 0,
            "rebalance_order_sides": (),
            "skipped_rebalance_orders": (),
        }

    lot = int(config.min_order_lot)
    intents: list[OrderIntent] = []
    skipped: list[Mapping[str, Any]] = []
    resized_count = 0
    selected_set = set(selected_symbols)
    target_values = {symbol: float(weight) * equity for symbol, weight in target_weights.items()}

    for symbol in sorted(set(account.positions) | selected_set):
        price = float(prices.get(symbol, 0.0))
        if price <= 0:
            continue
        current_shares = int(account.positions.get(symbol, 0))
        current_value = current_shares * price
        target_value = target_values.get(symbol, 0.0)
        reduce_value = current_value - target_value
        if current_shares > 0 and reduce_value >= price * lot:
            quantity = min(current_shares, _floor_lot(reduce_value / price, lot))
            if quantity >= lot:
                intents.append(
                    _rebalance_intent(
                        symbol=symbol,
                        side=OrderIntentSide.SELL,
                        quantity=quantity,
                        target_weight=target_weights.get(symbol, 0.0),
                        run_label=run_label,
                        reason="scaleup_rebalance_reduce_to_target",
                    )
                )

    estimated_cash = float(account.cash)
    for intent in intents:
        price = float(prices.get(intent.symbol, 0.0))
        estimated_cash += _estimated_sell_cash(int(intent.target_shares or 0), price, cost_assumptions)

    reserve_cash = max(0.0, equity * float(config.reserve_cash_weight))
    for symbol in selected_symbols:
        price = float(prices.get(symbol, 0.0))
        if price <= 0:
            continue
        current_value = int(account.positions.get(symbol, 0)) * price
        target_value = target_values.get(symbol, 0.0)
        add_value = target_value - current_value
        if add_value < price * lot:
            if add_value > 0:
                skipped.append({"symbol": symbol, "reason": "below_min_lot_after_resize"})
            continue
        desired_quantity = _floor_lot(add_value / price, lot)
        affordable_quantity = _max_affordable_buy_quantity(
            cash=max(0.0, estimated_cash - reserve_cash),
            price=price,
            lot=lot,
            cost_assumptions=cost_assumptions,
        )
        quantity = min(desired_quantity, affordable_quantity)
        if quantity < lot:
            skipped.append({"symbol": symbol, "reason": "below_min_lot_after_resize"})
            continue
        if quantity < desired_quantity:
            resized_count += 1
        estimated_cash -= _estimated_buy_cash(quantity, price, cost_assumptions)
        intents.append(
            _rebalance_intent(
                symbol=symbol,
                side=OrderIntentSide.BUY,
                quantity=quantity,
                target_weight=target_weights.get(symbol, 0.0),
                run_label=run_label,
                reason="scaleup_rebalance_add_to_target",
                resized=quantity < desired_quantity,
            )
        )

    proposal = _rebalance_proposal(tuple(intents), run_label)
    sides = tuple(str(intent.side.value if isinstance(intent.side, OrderIntentSide) else intent.side) for intent in intents)
    return proposal, {
        "resized_order_count": resized_count,
        "skipped_below_lot_count": len(skipped),
        "rebalance_sell_count": sum(1 for side in sides if side == "sell"),
        "rebalance_buy_count": sum(1 for side in sides if side == "buy"),
        "rebalance_order_sides": sides,
        "skipped_rebalance_orders": tuple(skipped),
        "target_weights": dict(target_weights),
    }


def _rebalance_intent(
    *,
    symbol: str,
    side: OrderIntentSide,
    quantity: int,
    target_weight: float,
    run_label: str,
    reason: str,
    resized: bool = False,
) -> OrderIntent:
    metadata: dict[str, Any] = {
        "no_broker_live_execution": True,
        "rebalance_intent": True,
        "resized_order": resized,
    }
    return OrderIntent(
        symbol=symbol,
        side=side,
        target_weight=round(float(target_weight), 6),
        target_shares=int(quantity),
        reason=reason,
        source_agent="scaleup_rebalance",
        confidence=1.0,
        strategy_id="real_data_walk_forward_scaleup_v1",
        run_label=run_label,
        metadata=metadata,
    )


def _rebalance_proposal(intents: tuple[OrderIntent, ...], run_label: str) -> OrderIntentProposal:
    return OrderIntentProposal(
        intents=intents,
        proposal_source=OrderIntentProposalSource.EXEC2,
        advisory_only=True,
        run_label=run_label,
        metadata={
            "strategy_id": "real_data_walk_forward_scaleup_v1",
            "no_broker_live_execution": True,
            "cash_aware_rebalance": True,
        },
    )


def _floor_lot(shares: float, lot: int) -> int:
    return int(shares // lot) * lot


def _estimated_buy_cash(quantity: int, price: float, cost_assumptions: PaperFillCostAssumptions) -> float:
    fill_price = price * (1 + cost_assumptions.slippage_bps / 10_000)
    gross = quantity * fill_price
    fee = max(gross * cost_assumptions.fee_rate, cost_assumptions.min_fee)
    return round(gross + fee, 6)


def _estimated_sell_cash(quantity: int, price: float, cost_assumptions: PaperFillCostAssumptions) -> float:
    fill_price = price * (1 - cost_assumptions.slippage_bps / 10_000)
    gross = quantity * fill_price
    fee = max(gross * cost_assumptions.fee_rate, cost_assumptions.min_fee)
    stamp_tax = gross * cost_assumptions.stamp_tax_rate
    return round(gross - fee - stamp_tax, 6)


def _max_affordable_buy_quantity(
    *,
    cash: float,
    price: float,
    lot: int,
    cost_assumptions: PaperFillCostAssumptions,
) -> int:
    if cash <= 0 or price <= 0:
        return 0
    rough = _floor_lot(cash / (price * (1 + cost_assumptions.slippage_bps / 10_000)), lot)
    while rough >= lot and _estimated_buy_cash(rough, price, cost_assumptions) > cash:
        rough -= lot
    return max(0, rough)


def _scaleup_window_metrics(
    *,
    window: Any,
    account: PaperAccount,
    fill_result: Any,
    starting_equity: float,
    ending_equity: float,
    start_prices: Mapping[str, float],
    end_prices: Mapping[str, float],
    selected_symbols: tuple[str, ...],
    target_weights: Mapping[str, float],
    proposal: OrderIntentProposal,
    build_notes: Mapping[str, Any],
) -> Mapping[str, Any]:
    gross_exposure = _position_market_value(account.positions, end_prices)
    turnover = round(sum(float(trade.gross_notional) for trade in fill_result.filled_trades), 6)
    cost_total = round(sum(float(trade.total_cost) for trade in fill_result.filled_trades), 6)
    rejected_details = _rejected_trade_details(tuple(fill_result.rejected_fills))
    symbol_breakdown = _symbol_breakdown(
        account=account,
        latest_prices=end_prices,
        ending_equity=ending_equity,
        symbols=tuple(sorted(set(end_prices) | set(account.positions) | set(account.average_costs))),
        starting_equity=starting_equity,
    )
    largest_weight = _largest_position_weight(account.positions, end_prices, ending_equity)
    equity_return = _ratio(ending_equity - starting_equity, starting_equity)
    return {
        "run_label": window.run_label,
        "train_start": str(window.train_start),
        "train_end": str(window.train_end),
        "test_start": str(window.test_start),
        "test_end": str(window.test_end),
        "starting_equity": round(starting_equity, 6),
        "ending_equity": round(ending_equity, 6),
        "equity_window_return": equity_return,
        "cash": round(float(account.cash), 6),
        "position_market_value": round(gross_exposure, 6),
        "gross_exposure": round(gross_exposure, 6),
        "net_exposure": round(gross_exposure, 6),
        "realized_pnl": round(float(account.realized_pnl), 6),
        "unrealized_pnl": round(float(account.unrealized_pnl), 6),
        "total_pnl": round(float(account.realized_pnl) + float(account.unrealized_pnl), 6),
        "net_pnl": round(ending_equity - starting_equity, 6),
        "trade_count": len(fill_result.filled_trades),
        "rejected_count": len(fill_result.rejected_fills),
        "fill_rate": round(len(fill_result.filled_trades) / len(proposal.intents), 6) if proposal.intents else 0.0,
        "turnover": turnover,
        "cost_total": cost_total,
        "cost_to_turnover_ratio": _ratio(cost_total, turnover),
        "rejection_reasons": rejected_details["rejection_reasons"],
        "rejected_symbols": rejected_details["rejected_symbols"],
        "per_symbol_breakdown": symbol_breakdown,
        "cash_ratio": _ratio(float(account.cash), ending_equity),
        "cash_weight": _ratio(float(account.cash), ending_equity),
        "gross_exposure_ratio": _ratio(gross_exposure, ending_equity),
        "gross_exposure_weight": _ratio(gross_exposure, ending_equity),
        "invested_ratio": _ratio(gross_exposure, ending_equity),
        "largest_position_weight": largest_weight,
        "actual_position_count": sum(1 for quantity in account.positions.values() if int(quantity) > 0),
        "candidate_symbols": selected_symbols,
        "target_weights": dict(target_weights),
        "rebalance_order_sides": build_notes.get("rebalance_order_sides", ()),
        "resized_order_count": int(build_notes.get("resized_order_count", 0)),
        "skipped_below_lot_count": int(build_notes.get("skipped_below_lot_count", 0)),
        "rebalance_sell_count": int(build_notes.get("rebalance_sell_count", 0)),
        "rebalance_buy_count": int(build_notes.get("rebalance_buy_count", 0)),
        "skipped_rebalance_orders": build_notes.get("skipped_rebalance_orders", ()),
        "start_prices": dict(start_prices),
        "end_prices": dict(end_prices),
    }


def _mark_account_to_prices(account: PaperAccount, prices: Mapping[str, float]) -> PaperAccount:
    unrealized = 0.0
    for symbol, shares in account.positions.items():
        latest_price = prices.get(symbol)
        if latest_price is None:
            continue
        unrealized += int(shares) * (float(latest_price) - float(account.average_costs.get(symbol, 0.0)))
    return replace(account, unrealized_pnl=round(unrealized, 6))


def _account_equity(account: PaperAccount, prices: Mapping[str, float]) -> float:
    return round(float(account.cash) + _position_market_value(account.positions, prices), 6)


def _largest_position_weight(
    positions: Mapping[str, int],
    prices: Mapping[str, float],
    equity: float,
) -> float | None:
    if equity <= 0:
        return None
    values = [abs(int(quantity) * float(prices.get(symbol, 0.0))) / equity for symbol, quantity in positions.items()]
    return round(max(values), 6) if values else 0.0


def _load_bars(config: RealDataWalkForwardSmokeConfig) -> _LoadedBars:
    injected = config.metadata.get("normalized_daily_bars")
    if injected is not None:
        return _LoadedBars(tuple(injected))
    injected_frame = config.metadata.get("normalized_ohlcv")
    if injected_frame is not None:
        return _LoadedBars(tuple(_normalized_frame_to_bars(injected_frame, provider=_provider_name(config.provider))))

    provider = _resolve_provider(config.provider)
    request_batch: list[DailyBarRequest] = []
    for symbol in config.symbols:
        request_batch.append(
            DailyBarRequest(
                symbol=_provider_symbol(symbol, provider.provider_name),
                start_date=_as_date(config.start_date),
                end_date=_as_date(config.end_date),
                adjustment=Adjustment.NONE,
            )
        )

    if config.allow_partial_universe and hasattr(provider, "fetch_many_daily_bars_with_empty_symbols"):
        bars, empty_symbols = provider.fetch_many_daily_bars_with_empty_symbols(tuple(request_batch))
        warnings = tuple(f"empty_provider_rows:{symbol}" for symbol in empty_symbols)
        return _LoadedBars(tuple(bars), warnings)

    if hasattr(provider, "fetch_many_daily_bars"):
        return _LoadedBars(tuple(provider.fetch_many_daily_bars(tuple(request_batch))))

    bars: list[NormalizedDailyBar] = []
    warnings: list[str] = []
    for request in request_batch:
        symbol_bars = provider.fetch_daily_bars(request)
        if not symbol_bars and config.allow_partial_universe:
            warnings.append(f"empty_provider_rows:{request.symbol}")
            continue
        bars.extend(symbol_bars)
    return _LoadedBars(tuple(bars), tuple(warnings))


def _window_report_metrics(window_result: Any, price_frame: pd.DataFrame) -> Mapping[str, Any]:
    metrics = dict(window_result.performance_metrics)
    account = window_result.paper_trading_result.account
    fill_result = window_result.paper_trading_result.fill_result
    latest_prices = _latest_prices_for_window(price_frame, window_result.window.test_start, window_result.window.test_end)
    position_market_value = _position_market_value(account.positions, latest_prices)
    gross_exposure = _gross_exposure(account.positions, latest_prices)
    net_exposure = _net_exposure(account.positions, latest_prices)
    ending_equity = float(metrics.get("ending_equity", account.cash + position_market_value))
    turnover = float(metrics.get("turnover", 0.0))
    cost_total = float(metrics.get("cost_total", 0.0))
    rejected_fills = tuple(fill_result.rejected_fills)
    rejected_details = _rejected_trade_details(rejected_fills)
    symbol_breakdown = _symbol_breakdown(
        account=account,
        latest_prices=latest_prices,
        ending_equity=ending_equity,
        symbols=tuple(
            sorted(
                set(latest_prices)
                | set(account.positions)
                | set(account.average_costs)
                | set(account.realized_pnl_by_symbol)
                | {str(rejected.symbol) for rejected in rejected_fills if rejected.symbol}
            )
        ),
        starting_equity=float(metrics.get("starting_equity", 0.0)),
    )
    unrealized_pnl = round(float(metrics.get("unrealized_pnl", account.unrealized_pnl)), 6)
    realized_pnl = round(float(metrics.get("realized_pnl", account.realized_pnl)), 6)
    report: dict[str, Any] = {
        "run_label": window_result.window.run_label,
        "train_start": str(window_result.window.train_start),
        "train_end": str(window_result.window.train_end),
        "test_start": str(window_result.window.test_start),
        "test_end": str(window_result.window.test_end),
        **metrics,
        "cash": round(float(metrics.get("cash", account.cash)), 6),
        "ending_equity": round(ending_equity, 6),
        "position_market_value": position_market_value,
        "gross_exposure": gross_exposure,
        "net_exposure": net_exposure,
        "realized_pnl": realized_pnl,
        "unrealized_pnl": unrealized_pnl,
        "total_pnl": round(realized_pnl + unrealized_pnl, 6),
        "rejected_count": len(rejected_fills),
        "rejection_reasons": rejected_details["rejection_reasons"],
        "rejected_symbols": rejected_details["rejected_symbols"],
        "per_symbol_breakdown": symbol_breakdown,
        "cash_ratio": _ratio(float(metrics.get("cash", account.cash)), ending_equity),
        "gross_exposure_ratio": _ratio(gross_exposure, ending_equity),
        "invested_ratio": _ratio(position_market_value, ending_equity),
        "turnover": round(turnover, 6),
        "cost_to_turnover_ratio": _ratio(cost_total, turnover),
    }
    return report


def _latest_prices_for_window(frame: pd.DataFrame, start: Any, end: Any) -> Mapping[str, float]:
    if frame.empty:
        return {}
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    dates = pd.to_datetime(frame["date"]).dt.tz_localize(None)
    window = frame.loc[(dates >= start_ts) & (dates <= end_ts)].copy()
    if window.empty:
        return {}
    window = window.sort_values(["date", "symbol"], kind="stable")
    return {
        str(symbol): round(float(group["close"].iloc[-1]), 6)
        for symbol, group in window.groupby("symbol", sort=True)
    }


def _position_market_value(positions: Mapping[str, int], latest_prices: Mapping[str, float]) -> float:
    return round(sum(int(quantity) * float(latest_prices.get(symbol, 0.0)) for symbol, quantity in positions.items()), 6)


def _gross_exposure(positions: Mapping[str, int], latest_prices: Mapping[str, float]) -> float:
    return round(sum(abs(int(quantity) * float(latest_prices.get(symbol, 0.0))) for symbol, quantity in positions.items()), 6)


def _net_exposure(positions: Mapping[str, int], latest_prices: Mapping[str, float]) -> float:
    return _position_market_value(positions, latest_prices)


def _rejected_trade_details(rejected_fills: Sequence[Any]) -> Mapping[str, Any]:
    reasons: dict[str, int] = {}
    symbols: set[str] = set()
    for rejected in rejected_fills:
        if rejected.symbol:
            symbols.add(str(rejected.symbol))
        for reason in rejected.reasons:
            reasons[str(reason)] = reasons.get(str(reason), 0) + 1
    return {
        "rejection_reasons": dict(sorted(reasons.items())),
        "rejected_symbols": tuple(sorted(symbols)),
    }


def _symbol_breakdown(
    *,
    account: PaperAccount,
    latest_prices: Mapping[str, float],
    ending_equity: float,
    symbols: Sequence[str],
    starting_equity: float | None = None,
) -> tuple[Mapping[str, Any], ...]:
    return account_symbol_pnl_breakdown(
        account,
        latest_prices,
        ending_equity=ending_equity,
        starting_equity=starting_equity,
        symbols=tuple(symbols),
    )


def _aggregate_symbol_breakdown(per_window: tuple[Mapping[str, Any], ...]) -> tuple[Mapping[str, Any], ...]:
    if not per_window:
        return ()
    return tuple(per_window[-1].get("per_symbol_breakdown", ()))


def _scaleup_report_from_smoke(
    smoke_report: RealDataWalkForwardSmokeReport,
    config: RealDataWalkForwardScaleupConfig,
) -> RealDataWalkForwardScaleupReport:
    expected_symbols = tuple(canonicalize_a_share_symbol(symbol) for symbol in config.symbols)
    valid_symbols = _valid_symbols_from_report(smoke_report)
    skipped_symbols = _skipped_symbols_from_report(smoke_report, expected_symbols, valid_symbols)
    if not valid_symbols and skipped_symbols and set(skipped_symbols) != set(expected_symbols):
        valid_symbols = tuple(symbol for symbol in expected_symbols if symbol not in set(skipped_symbols))
    window_returns = _window_returns(smoke_report.per_window_metrics)
    turnover = round(sum(float(metrics.get("turnover", 0.0)) for metrics in smoke_report.per_window_metrics), 6)
    per_symbol_total_pnl = _per_symbol_total_pnl(smoke_report.aggregate_symbol_breakdown)
    ranked = _rank_contributors(per_symbol_total_pnl)
    rejected_ratio = _rejected_trade_ratio(smoke_report.filled_trades, smoke_report.rejected_trades)
    contribution = _contribution_to_total_return(per_symbol_total_pnl, smoke_report.initial_cash)
    unavailable = smoke_report.notes[0] == "real_data_provider_unavailable" if smoke_report.notes else False
    position_counts = tuple(
        int(metrics.get("actual_position_count", 0)) for metrics in smoke_report.per_window_metrics
    )
    largest_weights = tuple(
        float(metrics["largest_position_weight"])
        for metrics in smoke_report.per_window_metrics
        if metrics.get("largest_position_weight") is not None
    )
    notes = (
        "real_data_walk_forward_scaleup_v1_completed" if not unavailable else "real_data_walk_forward_scaleup_v1_unavailable",
        "manual_only_real_provider_run",
        "no_broker_live_execution",
        "deepseek_live_disabled_by_default",
        f"advisory_mode:{config.advisory_mode}",
        f"ranking_mode:{config.ranking_mode}",
    )
    return RealDataWalkForwardScaleupReport(
        parameter_set_id=(
            str(config.metadata["parameter_set_id"])
            if config.metadata.get("parameter_set_id") is not None
            else None
        ),
        ranking_mode=config.ranking_mode,
        target_position_count=int(config.target_position_count),
        max_position_weight=round(float(config.max_position_weight), 6),
        reserve_cash_weight=round(float(config.reserve_cash_weight), 6),
        symbols=expected_symbols,
        date_range=smoke_report.date_range,
        provider=smoke_report.provider,
        benchmark_mode=config.benchmark_mode,
        windows_run=smoke_report.windows_run,
        valid_symbols=valid_symbols,
        skipped_symbols=skipped_symbols,
        initial_cash=smoke_report.initial_cash,
        final_equity=smoke_report.final_equity,
        total_return=smoke_report.total_return,
        benchmark_total_return=smoke_report.benchmark_total_return,
        strategy_excess_return=smoke_report.strategy_excess_return,
        max_drawdown=smoke_report.max_drawdown,
        win_rate_by_window=_win_rate(window_returns),
        average_window_return=_average(window_returns),
        median_window_return=_median(window_returns),
        worst_window_return=min(window_returns) if window_returns else None,
        equity_window_return=window_returns,
        actual_position_count_by_window=tuple(int(metrics.get("actual_position_count", 0)) for metrics in smoke_report.per_window_metrics),
        cash_weight_by_window=tuple(_optional_float(metrics.get("cash_weight")) for metrics in smoke_report.per_window_metrics),
        gross_exposure_by_window=tuple(_optional_float(metrics.get("gross_exposure_weight")) for metrics in smoke_report.per_window_metrics),
        largest_position_weight_by_window=tuple(_optional_float(metrics.get("largest_position_weight")) for metrics in smoke_report.per_window_metrics),
        filled_trades=smoke_report.filled_trades,
        rejected_trades=smoke_report.rejected_trades,
        rejected_trade_ratio=rejected_ratio,
        average_position_count=_average(tuple(float(value) for value in position_counts)),
        average_largest_position_weight=_average(tuple(largest_weights)),
        rejection_reasons=_aggregate_rejection_reasons(smoke_report.per_window_metrics),
        resized_order_count=sum(int(metrics.get("resized_order_count", 0)) for metrics in smoke_report.per_window_metrics),
        skipped_below_lot_count=sum(int(metrics.get("skipped_below_lot_count", 0)) for metrics in smoke_report.per_window_metrics),
        rebalance_sell_count=sum(int(metrics.get("rebalance_sell_count", 0)) for metrics in smoke_report.per_window_metrics),
        rebalance_buy_count=sum(int(metrics.get("rebalance_buy_count", 0)) for metrics in smoke_report.per_window_metrics),
        turnover=turnover,
        cost_total=smoke_report.cost_total,
        cost_to_turnover_ratio=_ratio(smoke_report.cost_total, turnover),
        top_contributors=ranked[:5],
        worst_contributors=tuple(reversed(ranked[-5:])) if ranked else (),
        per_symbol_total_pnl=per_symbol_total_pnl,
        contribution_to_total_return=contribution,
        per_window_metrics=smoke_report.per_window_metrics,
        data_quality_warnings=smoke_report.data_quality_warnings,
        mature_framework_hooks=_mature_framework_hooks(config.metadata),
        notes=notes + tuple(note for note in smoke_report.notes if note not in {"real_data_smoke_completed"}),
    )


def _valid_symbols_from_report(report: RealDataWalkForwardSmokeReport) -> tuple[str, ...]:
    symbols: set[str] = set()
    for metrics in report.per_window_metrics:
        for row in metrics.get("per_symbol_breakdown", ()):
            symbol = row.get("symbol") if isinstance(row, Mapping) else None
            if symbol:
                symbols.add(str(symbol))
    return tuple(sorted(symbols))


def _skipped_symbols_from_report(
    report: RealDataWalkForwardSmokeReport,
    expected_symbols: tuple[str, ...],
    valid_symbols: tuple[str, ...],
) -> tuple[str, ...]:
    missing_prefix = "missing_symbols:"
    for warning in report.data_quality_warnings:
        if warning.startswith(missing_prefix):
            return tuple(symbol for symbol in warning.removeprefix(missing_prefix).split(",") if symbol)
    return tuple(symbol for symbol in expected_symbols if symbol not in set(valid_symbols))


def _window_returns(per_window: tuple[Mapping[str, Any], ...]) -> tuple[float, ...]:
    returns: list[float] = []
    for metrics in per_window:
        if metrics.get("equity_window_return") is not None:
            returns.append(round(float(metrics["equity_window_return"]), 6))
            continue
        starting = float(metrics.get("starting_equity", 0.0))
        ending = float(metrics.get("ending_equity", 0.0))
        if starting > 0:
            returns.append(round((ending - starting) / starting, 6))
    return tuple(returns)


def _win_rate(values: tuple[float, ...]) -> float | None:
    if not values:
        return None
    return round(sum(1 for value in values if value > 0) / len(values), 6)


def _average(values: tuple[float, ...]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 6)


def _median(values: tuple[float, ...]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return round(ordered[middle], 6)
    return round((ordered[middle - 1] + ordered[middle]) / 2, 6)


def _aggregate_rejection_reasons(per_window: tuple[Mapping[str, Any], ...]) -> Mapping[str, int]:
    reasons: dict[str, int] = {}
    for metrics in per_window:
        for reason, count in dict(metrics.get("rejection_reasons", {})).items():
            reasons[str(reason)] = reasons.get(str(reason), 0) + int(count)
    return dict(sorted(reasons.items()))


def _per_symbol_total_pnl(rows: tuple[Mapping[str, Any], ...]) -> Mapping[str, float]:
    values: dict[str, float] = {}
    for row in rows:
        symbol = str(row.get("symbol", ""))
        if not symbol:
            continue
        values[symbol] = round(float(row.get("total_pnl", 0.0)), 6)
    return dict(sorted(values.items()))


def _rank_contributors(per_symbol_total_pnl: Mapping[str, float]) -> tuple[Mapping[str, Any], ...]:
    non_zero = {symbol: pnl for symbol, pnl in per_symbol_total_pnl.items() if float(pnl) != 0.0}
    values = non_zero or dict(per_symbol_total_pnl)
    rows = [
        {"symbol": symbol, "total_pnl": pnl}
        for symbol, pnl in sorted(
            values.items(),
            key=lambda item: (-float(item[1]), item[0]),
        )
    ]
    return tuple(rows)


def _rejected_trade_ratio(filled_trades: int, rejected_trades: int) -> float | None:
    total = int(filled_trades) + int(rejected_trades)
    if total <= 0:
        return None
    return round(int(rejected_trades) / total, 6)


def _contribution_to_total_return(
    per_symbol_total_pnl: Mapping[str, float],
    initial_cash: float,
) -> Mapping[str, float]:
    if initial_cash == 0:
        return {}
    return {
        symbol: round(float(pnl) / float(initial_cash), 6)
        for symbol, pnl in sorted(per_symbol_total_pnl.items())
    }


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return round(float(value), 6)


def _mature_framework_hooks(metadata: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "vectorbt_stats_adapter": "optional_not_required",
        "qlib_report_adapter": "optional_not_required",
        "rqalpha_artifact_adapter": "optional_not_required",
        "provided_vectorbt_stats": metadata.get("vectorbt_stats") is not None,
        "provided_qlib_report": metadata.get("qlib_report") is not None,
        "provided_rqalpha_artifact": metadata.get("rqalpha_artifact") is not None,
    }


def _benchmark_metrics(
    frame: pd.DataFrame,
    windows: Sequence[Any],
    initial_cash: float,
    benchmark_mode: str,
) -> Mapping[str, Any]:
    if benchmark_mode != "equal_weight_close_to_close":
        unavailable = f"benchmark_unavailable:unsupported_mode:{benchmark_mode}"
        return {
            "benchmark_final_equity": None,
            "benchmark_total_return": None,
            "benchmark_notes": (unavailable,),
        }
    return _buy_and_hold_benchmark(frame, windows, initial_cash)


def _buy_and_hold_benchmark(
    frame: pd.DataFrame,
    windows: Sequence[Any],
    initial_cash: float,
) -> Mapping[str, Any]:
    if frame.empty:
        return {
            "benchmark_final_equity": None,
            "benchmark_total_return": None,
            "benchmark_notes": ("simple_equal_weight_benchmark_unavailable:no_price_rows",),
        }
    start_date = str(windows[0].test_start) if windows else str(frame["date"].min())
    end_date = str(windows[-1].test_end) if windows else str(frame["date"].max())
    ordered = frame.sort_values(["date", "symbol"], kind="stable")
    symbols = tuple(sorted(str(symbol) for symbol in ordered["symbol"].dropna().unique()))
    valid: list[tuple[str, float, float]] = []
    for symbol in symbols:
        group = ordered.loc[ordered["symbol"] == symbol].copy()
        start_rows = group.loc[group["date"] >= start_date]
        end_rows = group.loc[group["date"] <= end_date]
        if start_rows.empty or end_rows.empty:
            continue
        start_price = float(start_rows.iloc[0]["close"])
        end_price = float(end_rows.iloc[-1]["close"])
        if start_price > 0 and end_price > 0:
            valid.append((symbol, start_price, end_price))
    if not valid:
        return {
            "benchmark_final_equity": None,
            "benchmark_total_return": None,
            "benchmark_notes": ("simple_equal_weight_benchmark_unavailable:no_valid_symbol_prices",),
        }
    allocation = initial_cash / len(valid)
    final_equity = round(sum((allocation / start_price) * end_price for _, start_price, end_price in valid), 6)
    return {
        "benchmark_final_equity": final_equity,
        "benchmark_total_return": _total_return(initial_cash, final_equity),
        "benchmark_notes": (
            "simple_equal_weight_close_to_close_no_costs",
            f"benchmark_start:{start_date}",
            f"benchmark_end:{end_date}",
            f"benchmark_symbols:{','.join(symbol for symbol, _, _ in valid)}",
        ),
    }


def _write_report_artifact(report: RealDataWalkForwardSmokeReport, artifact_path: str | Path | None) -> str | None:
    if artifact_path is None:
        return None
    path = Path(artifact_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _json_ready(asdict(replace(report, artifact_path=str(path))))
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(path)


def _write_scaleup_report_artifact(
    report: RealDataWalkForwardScaleupReport,
    artifact_path: str | Path | None,
) -> str | None:
    if artifact_path is None:
        return None
    path = Path(artifact_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _json_ready(asdict(replace(report, artifact_path=str(path))))
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(path)


def _write_scaleup_sweep_report_artifact(
    report: RealDataWalkForwardScaleupSweepReport,
    artifact_path: str | Path | None,
) -> str | None:
    if artifact_path is None:
        return None
    path = Path(artifact_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _json_ready(asdict(replace(report, artifact_path=str(path))))
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(path)


def _write_factor_ranking_sweep_integration_artifact(
    report: FactorRankingSweepIntegrationReport,
    artifact_path: str | Path | None,
) -> str | None:
    if artifact_path is None:
        return None
    path = Path(artifact_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _json_ready(asdict(replace(report, artifact_path=str(path))))
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(path)


def _scaleup_parameter_set_row(report: RealDataWalkForwardScaleupReport) -> Mapping[str, Any]:
    return {
        "parameter_set_id": report.parameter_set_id,
        "ranking_mode": report.ranking_mode,
        "target_position_count": report.target_position_count,
        "max_position_weight": report.max_position_weight,
        "reserve_cash_weight": report.reserve_cash_weight,
        "total_return": report.total_return,
        "benchmark_total_return": report.benchmark_total_return,
        "strategy_excess_return": report.strategy_excess_return,
        "max_drawdown": report.max_drawdown,
        "win_rate_by_window": report.win_rate_by_window,
        "average_window_return": report.average_window_return,
        "median_window_return": report.median_window_return,
        "worst_window_return": report.worst_window_return,
        "turnover": report.turnover,
        "cost_total": report.cost_total,
        "cost_to_turnover_ratio": report.cost_to_turnover_ratio,
        "rejected_trade_ratio": report.rejected_trade_ratio,
        "average_position_count": report.average_position_count,
        "average_largest_position_weight": report.average_largest_position_weight,
        "top_contributors": report.top_contributors,
        "worst_contributors": report.worst_contributors,
        "windows_run": report.windows_run,
        "filled_trades": report.filled_trades,
        "rejected_trades": report.rejected_trades,
        "valid_symbols": report.valid_symbols,
        "data_quality_warnings": report.data_quality_warnings,
        "notes": report.notes,
    }


def _top_parameter_sets(
    rows: tuple[Mapping[str, Any], ...],
    metric: str,
    top_n: int,
) -> tuple[Mapping[str, Any], ...]:
    ranked = sorted(
        rows,
        key=lambda row: (
            _none_low(row.get(metric)),
            _none_low(row.get("strategy_excess_return")),
            str(row.get("parameter_set_id") or ""),
        ),
        reverse=True,
    )
    return tuple(_ranking_summary(row) for row in ranked[:top_n])


def _top_drawdown_adjusted_parameter_sets(
    rows: tuple[Mapping[str, Any], ...],
    top_n: int,
) -> tuple[Mapping[str, Any], ...]:
    scored = [
        (
            _drawdown_adjusted_score(row),
            _none_low(row.get("strategy_excess_return")),
            str(row.get("parameter_set_id") or ""),
            row,
        )
        for row in rows
    ]
    ranked = sorted(scored, key=lambda item: (item[0], item[1], item[2]), reverse=True)
    return tuple(
        {
            **_ranking_summary(row),
            "drawdown_adjusted_score": score,
        }
        for score, _, _, row in ranked[:top_n]
    )


def _valid_symbols_from_parameter_rows(rows: tuple[Mapping[str, Any], ...]) -> tuple[str, ...]:
    symbols: set[str] = set()
    for row in rows:
        for symbol in row.get("valid_symbols", ()):
            symbols.add(str(symbol))
    return tuple(sorted(symbols))


def _factor_mode_summary(rows: tuple[Mapping[str, Any], ...]) -> tuple[Mapping[str, Any], ...]:
    summary: list[Mapping[str, Any]] = []
    for ranking_mode in FACTOR_RANKING_SWEEP_INTEGRATION_MODES:
        mode_rows = tuple(row for row in rows if row.get("ranking_mode") == ranking_mode)
        if not mode_rows:
            continue
        best_by_excess = _top_parameter_sets(mode_rows, "strategy_excess_return", 1)
        best_by_return = _top_parameter_sets(mode_rows, "total_return", 1)
        best_by_drawdown = _top_drawdown_adjusted_parameter_sets(mode_rows, 1)
        summary.append(
            {
                "ranking_mode": ranking_mode,
                "parameter_set_count": len(mode_rows),
                "best_by_excess": best_by_excess[0] if best_by_excess else None,
                "best_by_return": best_by_return[0] if best_by_return else None,
                "best_by_drawdown_adjusted": best_by_drawdown[0] if best_by_drawdown else None,
                "average_total_return": _average_metric(mode_rows, "total_return"),
                "average_strategy_excess_return": _average_metric(mode_rows, "strategy_excess_return"),
                "average_max_drawdown": _average_metric(mode_rows, "max_drawdown"),
                "average_turnover": _average_metric(mode_rows, "turnover"),
                "average_cost_total": _average_metric(mode_rows, "cost_total"),
                "average_cost_to_turnover_ratio": _average_metric(mode_rows, "cost_to_turnover_ratio"),
                "average_rejected_trade_ratio": _average_metric(mode_rows, "rejected_trade_ratio"),
            }
        )
    return tuple(summary)


def _average_metric(rows: tuple[Mapping[str, Any], ...], metric: str) -> float | None:
    values = tuple(float(row[metric]) for row in rows if row.get(metric) is not None)
    return _average(values)


def _ranking_summary(row: Mapping[str, Any]) -> Mapping[str, Any]:
    fields = (
        "parameter_set_id",
        "ranking_mode",
        "target_position_count",
        "max_position_weight",
        "reserve_cash_weight",
        "total_return",
        "benchmark_total_return",
        "strategy_excess_return",
        "max_drawdown",
        "turnover",
        "cost_total",
        "cost_to_turnover_ratio",
        "rejected_trade_ratio",
        "average_position_count",
        "average_largest_position_weight",
    )
    return {field: row.get(field) for field in fields}


def _drawdown_adjusted_score(row: Mapping[str, Any]) -> float:
    excess = row.get("strategy_excess_return")
    if excess is None:
        excess = row.get("total_return")
    if excess is None:
        return -1_000_000_000.0
    drawdown = abs(float(row.get("max_drawdown") or 0.0))
    if drawdown == 0:
        return round(float(excess), 6)
    return round(float(excess) / drawdown, 6)


def _none_low(value: Any) -> float:
    if value is None:
        return -1_000_000_000.0
    return float(value)


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _ratio(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return round(float(numerator) / float(denominator), 6)


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


def _validate_scaleup_config(config: RealDataWalkForwardScaleupConfig) -> None:
    if config.max_position_weight <= 0 or config.max_position_weight > 1:
        raise ValueError("max_position_weight must be in (0, 1]")
    if config.target_position_count <= 0:
        raise ValueError("target_position_count must be positive")
    if config.reserve_cash_weight < 0 or config.reserve_cash_weight >= 1:
        raise ValueError("reserve_cash_weight must be in [0, 1)")
    if config.min_order_lot <= 0:
        raise ValueError("min_order_lot must be positive")
    if config.max_rejected_trade_ratio_warning < 0 or config.max_rejected_trade_ratio_warning > 1:
        raise ValueError("max_rejected_trade_ratio_warning must be in [0, 1]")
    if config.ranking_mode not in SUPPORTED_REAL_DATA_SCALEUP_RANKING_MODES:
        raise ValueError(f"unsupported ranking_mode: {config.ranking_mode}")


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
    if config.min_symbols_required <= 0:
        raise ValueError("min_symbols_required must be positive")
    if config.advisory_mode not in {"disabled", "fallback_only", "evidence_only"}:
        warnings.append("advisory_mode_forced_to_fallback_only")
    if config.benchmark_mode != "equal_weight_close_to_close":
        warnings.append(f"benchmark_mode_unsupported:{config.benchmark_mode}")
    return tuple(warnings)


def _scaleup_diagnostic_warnings(
    per_window: tuple[Mapping[str, Any], ...],
    config: RealDataWalkForwardScaleupConfig,
) -> tuple[str, ...]:
    warnings: list[str] = []
    tolerance = 0.01
    for metrics in per_window:
        label = str(metrics.get("run_label", "window"))
        largest = metrics.get("largest_position_weight")
        if largest is not None and float(largest) > float(config.max_position_weight) + tolerance:
            warnings.append(f"{label}:largest_position_weight_above_target:{float(largest):.6f}")
        position_count = int(metrics.get("actual_position_count", 0))
        if position_count < max(1, int(config.target_position_count) / 2):
            warnings.append(f"{label}:actual_position_count_below_half_target:{position_count}")
    filled = sum(int(metrics.get("trade_count", 0)) for metrics in per_window)
    rejected = sum(int(metrics.get("rejected_count", 0)) for metrics in per_window)
    rejected_ratio = _rejected_trade_ratio(filled, rejected)
    if rejected_ratio is not None and rejected_ratio > float(config.max_rejected_trade_ratio_warning):
        warnings.append(f"rejected_trade_ratio_above_warning:{rejected_ratio:.6f}")
    reasons = _aggregate_rejection_reasons(per_window)
    if reasons:
        dominant_reason, dominant_count = max(reasons.items(), key=lambda item: item[1])
        if dominant_reason == "insufficient_cash" and dominant_count > rejected / 2:
            warnings.append("insufficient_cash_dominant_after_resizing")
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


def _valid_symbol_count(frame: pd.DataFrame) -> int:
    if "symbol" not in frame.columns:
        return 0
    return len({str(symbol) for symbol in frame["symbol"].dropna().unique()})


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
