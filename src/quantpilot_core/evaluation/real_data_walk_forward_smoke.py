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
from quantpilot_core.a_share_market_reality_execution import (
    AShareExecutionAccountState,
    AShareExecutionConfig,
    execute_a_share_reality_proposal,
    summarize_metadata_availability,
    summarize_execution_outcomes,
    summarize_rule_coverage,
)
from quantpilot_core.a_share_tradability_metadata import (
    AShareTradabilityMetadataConfig,
    enrich_market_rows,
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
SUPPORTED_REAL_DATA_SCALEUP_RANKING_MODES = REAL_DATA_SCALEUP_RANKING_MODES + FACTOR_RANKING_BASELINE_MODES + ("ml_prediction_score",)
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
class TurnoverAwareRebalanceConfig:
    """Focused turnover controls for the existing scale-up rebalance path."""

    enabled: bool = False
    entry_rank_threshold: int | None = None
    exit_rank_threshold: int | None = None
    minimum_score_improvement: float = 0.0
    target_weight_no_trade_band: float = 0.0
    minimum_order_value: float = 0.0
    minimum_holding_days: int = 0
    normalized_turnover_penalty: float = 0.0
    estimated_cost_multiplier: float = 1.0


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
    cost_multiplier: float = 1.0
    turnover_aware_rebalance: TurnoverAwareRebalanceConfig = field(default_factory=TurnoverAwareRebalanceConfig)
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
    turnover_aware_attribution: Mapping[str, Any] = field(default_factory=dict)


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
                            cost_multiplier=float(payload.metadata.get("cost_multiplier", 1.0)),
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
    account = _initial_paper_account(config)
    execution_state = AShareExecutionAccountState(
        account=account,
        settlement_lots=tuple(config.metadata.get("initial_settlement_lots", ())),
        frozen_cash=float(config.metadata.get("initial_frozen_cash", 0.0)),
    )
    per_window: list[Mapping[str, Any]] = []
    cost_assumptions = _scale_cost_assumptions(
        PaperFillCostAssumptions(lot_size=int(config.min_order_lot)),
        float(config.cost_multiplier),
    )
    use_a_share_reality = str(config.metadata.get("execution_reality", "")).lower() == "a_share_market_reality_v1"
    a_share_config = _a_share_execution_config(config.metadata)
    holding_start_dates: dict[str, str] = {
        str(symbol): str(config.metadata.get("initial_holding_start_date", config.start_date))
        for symbol, quantity in account.positions.items()
        if int(quantity) > 0
    }
    for window in windows:
        train_prices = _slice_price_frame(price_frame, window.train_start, window.train_end)
        start_prices = _first_prices_for_window(price_frame, window.test_start, window.test_end)
        start_market_rows = _first_market_rows_for_window(price_frame, window.test_start, window.test_end, config.metadata)
        end_prices = _latest_prices_for_window(price_frame, window.test_start, window.test_end)
        starting_equity = _account_equity(account, start_prices)
        ranked_candidates = _rank_scaleup_candidates(train_prices, start_prices, config)
        selected = tuple(symbol for _, symbol, _ in ranked_candidates[: int(config.target_position_count)])
        policy_notes = _turnover_aware_selection_notes()
        if config.turnover_aware_rebalance.enabled:
            raw_target_weights = _target_weights(selected, config)
            raw_proposal, _ = _build_rebalance_proposal(
                account=account,
                prices=start_prices,
                selected_symbols=selected,
                target_weights=raw_target_weights,
                equity=starting_equity,
                config=replace(config, turnover_aware_rebalance=TurnoverAwareRebalanceConfig(enabled=False)),
                cost_assumptions=cost_assumptions,
                run_label=window.run_label,
            )
            policy_notes["raw_orders_before_controls"] = len(raw_proposal.intents)
        if config.turnover_aware_rebalance.enabled:
            selected, policy_notes = _apply_turnover_aware_candidate_controls(
                ranked_candidates=ranked_candidates,
                account=account,
                prices=start_prices,
                equity=starting_equity,
                config=config,
                cost_assumptions=cost_assumptions,
                trade_date=str(pd.Timestamp(window.test_start).date()),
                holding_start_dates=holding_start_dates,
                raw_orders_before_controls=int(policy_notes.get("raw_orders_before_controls", 0)),
            )
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
            policy_notes=policy_notes,
        )
        execution_outcomes = ()
        cash_before_execution = float(account.cash)
        if use_a_share_reality:
            reality_result = execute_a_share_reality_proposal(
                proposal,
                start_market_rows,
                execution_state,
                trade_date=str(pd.Timestamp(window.test_start).date()),
                cost_assumptions=cost_assumptions,
                config=a_share_config,
            )
            execution_state = replace(reality_result.state, account=_mark_account_to_prices(reality_result.state.account, end_prices))
            account = execution_state.account
            fill_result = reality_result.fill_result
            execution_outcomes = reality_result.outcomes
        else:
            loop_result = run_paper_trading_loop(
                proposal,
                start_prices,
                account,
                cost_assumptions=cost_assumptions,
            )
            account = _mark_account_to_prices(loop_result.account, end_prices)
            execution_state = replace(execution_state, account=account)
            fill_result = loop_result.fill_result
        ending_equity = _account_equity(account, end_prices)
        metrics = _scaleup_window_metrics(
            window=window,
            account=account,
            fill_result=fill_result,
            starting_equity=starting_equity,
            ending_equity=ending_equity,
            start_prices=start_prices,
            end_prices=end_prices,
            selected_symbols=selected,
            target_weights=target_weights,
            proposal=proposal,
            build_notes=build_notes,
            execution_outcomes=execution_outcomes,
            execution_reality="a_share_market_reality_v1" if use_a_share_reality else "base_paper_fill",
            cash_before_execution=cash_before_execution,
        )
        per_window.append(metrics)
        _update_holding_start_dates(
            holding_start_dates,
            account.positions,
            trade_date=str(pd.Timestamp(window.test_start).date()),
        )
    return tuple(per_window), account


def _initial_paper_account(config: RealDataWalkForwardScaleupConfig) -> PaperAccount:
    injected = config.metadata.get("initial_paper_account")
    if isinstance(injected, PaperAccount):
        return injected
    if isinstance(injected, Mapping):
        return PaperAccount(
            cash=float(injected.get("cash", config.initial_cash)),
            positions=dict(injected.get("positions", {})),
            average_costs=dict(injected.get("average_costs", {})),
            realized_pnl_by_symbol=dict(injected.get("realized_pnl_by_symbol", {})),
            realized_pnl=float(injected.get("realized_pnl", 0.0)),
            unrealized_pnl=float(injected.get("unrealized_pnl", 0.0)),
        )
    return PaperAccount(cash=float(config.initial_cash))


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


def _first_market_rows_for_window(
    frame: pd.DataFrame,
    start: Any,
    end: Any,
    metadata: Mapping[str, Any] | None = None,
) -> Mapping[str, Mapping[str, Any]]:
    window = _slice_price_frame(frame, start, end)
    if window.empty:
        return {}
    start_ts = pd.Timestamp(start)
    full_ordered = frame.sort_values(["date", "symbol"], kind="stable").copy()
    full_ordered["_date_ts"] = pd.to_datetime(full_ordered["date"]).dt.tz_localize(None)
    ordered = window.sort_values(["date", "symbol"], kind="stable")
    rows: dict[str, Mapping[str, Any]] = {}
    for symbol, group in ordered.groupby("symbol", sort=True):
        first = group.iloc[0].to_dict()
        if first.get("previous_close") is None or pd.isna(first.get("previous_close")):
            symbol_history = full_ordered.loc[
                (full_ordered["symbol"] == symbol) & (full_ordered["_date_ts"] < start_ts)
            ]
            if not symbol_history.empty:
                first["previous_close"] = float(symbol_history["close"].iloc[-1])
                first["previous_close_source"] = "derived_from_prior_loaded_bar"
            else:
                first["previous_close_source"] = "unavailable"
        first.setdefault("price_basis", "unadjusted_adjustment_none")
        rows[str(symbol)] = first
    return enrich_market_rows(rows, config=AShareTradabilityMetadataConfig.from_metadata(metadata or {}))


def _select_scaleup_candidates(
    train_prices: pd.DataFrame,
    start_prices: Mapping[str, float],
    config: RealDataWalkForwardScaleupConfig,
) -> tuple[str, ...]:
    return tuple(symbol for _, symbol, _ in _rank_scaleup_candidates(train_prices, start_prices, config)[: int(config.target_position_count)])


def _rank_scaleup_candidates(
    train_prices: pd.DataFrame,
    start_prices: Mapping[str, float],
    config: RealDataWalkForwardScaleupConfig,
) -> tuple[tuple[int, str, float | None], ...]:
    if train_prices.empty or config.ranking_mode == "equal_weight_baseline":
        return tuple((rank, symbol, 0.0) for rank, symbol in enumerate(sorted(start_prices), start=1))
    if config.ranking_mode == "ml_prediction_score":
        prediction_map = config.metadata.get("ml_prediction_map", {})
        as_of_date = str(pd.Timestamp(train_prices["date"].max()).date())
        scores: list[tuple[float, str, float | None]] = []
        for symbol in sorted(start_prices):
            score = prediction_map.get((as_of_date, symbol))
            if score is None:
                score = prediction_map.get(f"{as_of_date}|{symbol}")
            try:
                numeric_score = float(score)
            except (TypeError, ValueError):
                scores.append((-1_000_000_000.0, symbol, None))
                continue
            if pd.isna(numeric_score) or numeric_score in (float("inf"), float("-inf")):
                scores.append((-1_000_000_000.0, symbol, None))
                continue
            scores.append((numeric_score, symbol, numeric_score))
        ranked = sorted(scores, key=lambda item: (-item[0], item[1]))
        return tuple((rank, symbol, score) for rank, (_, symbol, score) in enumerate(ranked, start=1))
    if config.ranking_mode in FACTOR_RANKING_BASELINE_MODES:
        report = run_factor_ranking_baseline_v1(
            train_prices.loc[train_prices["symbol"].isin(set(start_prices))],
            FactorRankingBaselineConfig(
                ranking_mode=config.ranking_mode,
                target_symbol_count=len(start_prices),
                artifact_path=None,
            ),
        )
        return tuple((rank, symbol, float(len(start_prices) - rank + 1)) for rank, symbol in enumerate(report.selected_symbols, start=1))
    scores: list[tuple[float, str]] = []
    ordered = train_prices.sort_values(["date", "symbol"], kind="stable")
    for symbol, group in ordered.groupby("symbol", sort=True):
        if str(symbol) not in start_prices:
            continue
        score = _ranking_score(group, config.ranking_mode)
        scores.append((round(score, 12), str(symbol)))
    ranked = sorted(scores, key=lambda item: (-item[0], item[1]))
    return tuple((rank, symbol, score) for rank, (score, symbol) in enumerate(ranked, start=1))


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


def _turnover_aware_selection_notes() -> dict[str, Any]:
    return {
        "raw_ranked_candidates": 0,
        "existing_positions_considered": 0,
        "candidates_after_rank_hysteresis": 0,
        "replacements_evaluated": 0,
        "replacements_blocked_by_score_threshold": 0,
        "target_positions_retained": 0,
        "selection_removed_by_rank_hysteresis": 0,
        "selection_removed_by_score_threshold": 0,
        "selection_removed_by_minimum_holding_period": 0,
        "raw_target_weight_deltas": 0,
        "orders_removed_as_zero_delta": 0,
        "orders_removed_below_lot": 0,
        "orders_removed_by_cash_resize": 0,
        "orders_removed_missing_price": 0,
        "orders_merged_or_net_adjusted": 0,
        "raw_orders_before_controls": 0,
        "orders_after_rank_hysteresis": 0,
        "orders_after_score_improvement": 0,
        "orders_after_weight_no_trade_band": 0,
        "orders_after_minimum_order_value": 0,
        "orders_after_minimum_holding_period": 0,
        "final_orders_retained": 0,
        "orders_proposed_before_turnover_controls": 0,
        "orders_retained": 0,
        "orders_skipped_by_rank_hysteresis": 0,
        "orders_skipped_by_score_improvement": 0,
        "orders_skipped_by_weight_no_trade_band": 0,
        "orders_skipped_by_minimum_order_value": 0,
        "orders_skipped_by_minimum_holding_period": 0,
        "direct_filter_estimated_cost_avoided": 0.0,
        "direct_filter_estimated_turnover_avoided": 0.0,
        "positions_retained_due_to_hysteresis": 0,
        "replacements_prevented": 0,
        "forced_required_exits_bypassed_turnover_controls": 0,
        "score_improvement_evaluated_replacement_count": 0,
        "score_improvement_triggered_count": 0,
        "turnover_control_skipped_orders": (),
        "turnover_controls_enabled": False,
    }


def _apply_turnover_aware_candidate_controls(
    *,
    ranked_candidates: tuple[tuple[int, str, float | None], ...],
    account: PaperAccount,
    prices: Mapping[str, float],
    equity: float,
    config: RealDataWalkForwardScaleupConfig,
    cost_assumptions: PaperFillCostAssumptions,
    trade_date: str,
    holding_start_dates: Mapping[str, str],
    raw_orders_before_controls: int = 0,
) -> tuple[tuple[str, ...], dict[str, Any]]:
    policy = config.turnover_aware_rebalance
    notes = _turnover_aware_selection_notes()
    notes["turnover_controls_enabled"] = True
    notes["raw_ranked_candidates"] = len(ranked_candidates)
    notes["raw_orders_before_controls"] = int(raw_orders_before_controls)
    entry = int(policy.entry_rank_threshold or config.target_position_count)
    exit_rank = int(policy.exit_rank_threshold or entry)
    target_count = int(config.target_position_count)
    rank_by_symbol = {symbol: rank for rank, symbol, _ in ranked_candidates}
    score_by_symbol = {symbol: score for _, symbol, score in ranked_candidates}
    current = tuple(symbol for symbol, quantity in sorted(account.positions.items()) if int(quantity) > 0)
    notes["existing_positions_considered"] = len(current)
    retained: list[str] = []
    for symbol in current:
        rank = rank_by_symbol.get(symbol)
        if rank is not None and rank <= exit_rank:
            retained.append(symbol)
            if rank > entry:
                notes["positions_retained_due_to_hysteresis"] += 1
                notes["orders_skipped_by_rank_hysteresis"] += 1
            continue
        if _holding_days(holding_start_dates.get(symbol), trade_date) < int(policy.minimum_holding_days):
            retained.append(symbol)
            notes["orders_skipped_by_minimum_holding_period"] += 1
            continue

    selected = list(retained)
    outgoing = [symbol for symbol in current if symbol not in set(retained)]
    notes["selection_removed_by_rank_hysteresis"] = len(outgoing)
    outgoing_scores = [score_by_symbol.get(symbol) for symbol in outgoing if _valid_score(score_by_symbol.get(symbol))]
    hurdle = float(policy.minimum_score_improvement)
    for rank, symbol, score in ranked_candidates:
        if len(selected) >= target_count:
            break
        if rank > entry or symbol in selected:
            continue
        if outgoing_scores:
            notes["score_improvement_evaluated_replacement_count"] += 1
            notes["replacements_evaluated"] += 1
            weakest_outgoing_score = min(float(value) for value in outgoing_scores)
            if not _valid_score(score) or float(score) - weakest_outgoing_score < hurdle:
                notes["orders_skipped_by_score_improvement"] += 1
                notes["replacements_prevented"] += 1
                notes["score_improvement_triggered_count"] += 1
                notes["replacements_blocked_by_score_threshold"] += 1
                continue
            cost_penalty = _replacement_cost_penalty(
                symbol=symbol,
                outgoing_symbols=tuple(outgoing),
                prices=prices,
                equity=equity,
                config=config,
                cost_assumptions=cost_assumptions,
            )
            if float(policy.normalized_turnover_penalty) > 0 and float(score) - weakest_outgoing_score < cost_penalty:
                notes["orders_skipped_by_score_improvement"] += 1
                notes["replacements_prevented"] += 1
                notes["score_improvement_triggered_count"] += 1
                notes["replacements_blocked_by_score_threshold"] += 1
                continue
        selected.append(symbol)
    final_selected = tuple(selected[:target_count])
    notes["candidates_after_rank_hysteresis"] = len(retained) + sum(1 for rank, symbol, _ in ranked_candidates if rank <= entry and symbol not in set(retained))
    notes["target_positions_retained"] = len(final_selected)
    notes["selection_removed_by_score_threshold"] = int(notes["replacements_blocked_by_score_threshold"])
    notes["selection_removed_by_minimum_holding_period"] = int(notes["orders_skipped_by_minimum_holding_period"])
    return final_selected, notes


def _valid_score(value: Any) -> bool:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return False
    return not pd.isna(numeric) and numeric not in (float("inf"), float("-inf"))


def _replacement_cost_penalty(
    *,
    symbol: str,
    outgoing_symbols: tuple[str, ...],
    prices: Mapping[str, float],
    equity: float,
    config: RealDataWalkForwardScaleupConfig,
    cost_assumptions: PaperFillCostAssumptions,
) -> float:
    if equity <= 0:
        return 0.0
    target_value = equity * min(float(config.max_position_weight), max(0.0, 1.0 - float(config.reserve_cash_weight)) / max(1, int(config.target_position_count)))
    buy_cost = _estimated_buy_cost(target_value, cost_assumptions)
    sell_cost = 0.0
    if outgoing_symbols:
        sell_cost = _estimated_sell_cost(target_value, cost_assumptions)
    normalized_cost = ((buy_cost + sell_cost) / equity) * float(config.turnover_aware_rebalance.estimated_cost_multiplier)
    return round(normalized_cost * float(config.turnover_aware_rebalance.normalized_turnover_penalty), 12)


def _holding_days(start_date: str | None, trade_date: str) -> int:
    if not start_date:
        return 1_000_000
    return max(0, (pd.Timestamp(trade_date) - pd.Timestamp(start_date)).days)


def _update_holding_start_dates(holding_start_dates: dict[str, str], positions: Mapping[str, int], trade_date: str) -> None:
    for symbol in list(holding_start_dates):
        if int(positions.get(symbol, 0)) <= 0:
            holding_start_dates.pop(symbol, None)
    for symbol, quantity in positions.items():
        if int(quantity) > 0 and symbol not in holding_start_dates:
            holding_start_dates[str(symbol)] = trade_date


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
    policy_notes: Mapping[str, Any] | None = None,
) -> tuple[OrderIntentProposal, Mapping[str, Any]]:
    if not config.rebalance_each_window and account.positions:
        return _rebalance_proposal((), run_label), {
            **_turnover_aware_selection_notes(),
            "resized_order_count": 0,
            "skipped_below_lot_count": 0,
            "rebalance_sell_count": 0,
            "rebalance_buy_count": 0,
            "rebalance_order_sides": (),
            "skipped_rebalance_orders": (),
        }

    lot = int(config.min_order_lot)
    notes = dict(policy_notes or _turnover_aware_selection_notes())
    intents: list[OrderIntent] = []
    skipped: list[Mapping[str, Any]] = []
    resized_count = 0
    selected_set = set(selected_symbols)
    target_values = {symbol: float(weight) * equity for symbol, weight in target_weights.items()}
    target_universe = sorted(set(account.positions) | selected_set)
    order_counts = _order_construction_counts(
        account=account,
        prices=prices,
        target_values=target_values,
        target_universe=tuple(target_universe),
        lot=lot,
    )
    notes.update(order_counts)

    for symbol in target_universe:
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
            notes["orders_removed_by_cash_resize"] = int(notes.get("orders_removed_by_cash_resize", 0)) + 1
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

    orders_after_candidate_controls = len(intents)
    candidate_skip_count = (
        int(notes.get("orders_skipped_by_rank_hysteresis", 0))
        + int(notes.get("orders_skipped_by_score_improvement", 0))
        + int(notes.get("orders_skipped_by_minimum_holding_period", 0))
    )
    raw_orders = int(notes.get("raw_orders_before_controls", 0)) or orders_after_candidate_controls + candidate_skip_count
    notes["raw_orders_before_controls"] = raw_orders
    notes["orders_proposed_before_turnover_controls"] = raw_orders
    notes["orders_proposed_after_candidate_controls"] = orders_after_candidate_controls
    if config.turnover_aware_rebalance.enabled:
        intents = list(
            _apply_turnover_aware_order_controls(
                intents=tuple(intents),
                account=account,
                prices=prices,
                equity=equity,
                target_weights=target_weights,
                config=config,
                cost_assumptions=cost_assumptions,
                notes=notes,
            )
        )
    after_rank = max(0, raw_orders - int(notes.get("orders_skipped_by_rank_hysteresis", 0)))
    after_score = max(0, after_rank - int(notes.get("orders_skipped_by_score_improvement", 0)))
    after_weight = max(0, after_score - int(notes.get("orders_skipped_by_weight_no_trade_band", 0)))
    after_min_order = max(0, after_weight - int(notes.get("orders_skipped_by_minimum_order_value", 0)))
    after_min_holding = max(0, after_min_order - int(notes.get("orders_skipped_by_minimum_holding_period", 0)))
    notes["orders_after_rank_hysteresis"] = after_rank
    notes["orders_after_score_improvement"] = after_score
    notes["orders_after_weight_no_trade_band"] = after_weight
    notes["orders_after_minimum_order_value"] = after_min_order
    notes["orders_after_minimum_holding_period"] = after_min_holding
    notes["final_orders_retained"] = len(intents)
    notes["orders_retained"] = len(intents)
    notes["order_final_order_intents"] = len(intents)
    proposal = _rebalance_proposal(tuple(intents), run_label)
    sides = tuple(str(intent.side.value if isinstance(intent.side, OrderIntentSide) else intent.side) for intent in intents)
    return proposal, {
        **notes,
        "resized_order_count": resized_count,
        "skipped_below_lot_count": len(skipped),
        "rebalance_sell_count": sum(1 for side in sides if side == "sell"),
        "rebalance_buy_count": sum(1 for side in sides if side == "buy"),
        "rebalance_order_sides": sides,
        "skipped_rebalance_orders": tuple(skipped),
        "target_weights": dict(target_weights),
    }


def _order_construction_counts(
    *,
    account: PaperAccount,
    prices: Mapping[str, float],
    target_values: Mapping[str, float],
    target_universe: tuple[str, ...],
    lot: int,
) -> Mapping[str, int]:
    counts = {
        "raw_target_weight_deltas": 0,
        "orders_removed_as_zero_delta": 0,
        "orders_removed_below_lot": 0,
        "orders_removed_missing_price": 0,
        "orders_merged_or_net_adjusted": 0,
    }
    for symbol in target_universe:
        target_value = float(target_values.get(symbol, 0.0))
        current_shares = int(account.positions.get(symbol, 0))
        price = float(prices.get(symbol, 0.0))
        if price <= 0:
            if current_shares > 0 or target_value > 0:
                counts["raw_target_weight_deltas"] += 1
                counts["orders_removed_missing_price"] += 1
            continue
        current_value = current_shares * price
        delta_value = target_value - current_value
        if current_shares > 0 or target_value > 0:
            counts["raw_target_weight_deltas"] += 1
        if round(delta_value, 8) == 0.0:
            if current_shares > 0 or target_value > 0:
                counts["orders_removed_as_zero_delta"] += 1
            continue
        if abs(delta_value) < price * lot:
            counts["orders_removed_below_lot"] += 1
    return counts


def _apply_turnover_aware_order_controls(
    *,
    intents: tuple[OrderIntent, ...],
    account: PaperAccount,
    prices: Mapping[str, float],
    equity: float,
    target_weights: Mapping[str, float],
    config: RealDataWalkForwardScaleupConfig,
    cost_assumptions: PaperFillCostAssumptions,
    notes: dict[str, Any],
) -> tuple[OrderIntent, ...]:
    policy = config.turnover_aware_rebalance
    retained: list[OrderIntent] = []
    skipped: list[Mapping[str, Any]] = list(notes.get("turnover_control_skipped_orders", ()))
    for intent in intents:
        symbol = str(intent.symbol)
        side = str(intent.side.value if isinstance(intent.side, OrderIntentSide) else intent.side)
        quantity = int(intent.target_shares or 0)
        price = float(prices.get(symbol, 0.0))
        target_weight = float(target_weights.get(symbol, 0.0))
        current_weight = _ratio(int(account.positions.get(symbol, 0)) * price, equity) or 0.0
        order_value = abs(quantity * price)
        is_liquidation = side == "sell" and target_weight <= 0.0
        reason: str | None = None
        if not is_liquidation and float(policy.target_weight_no_trade_band) > 0:
            if abs(target_weight - current_weight) < float(policy.target_weight_no_trade_band):
                reason = "target_weight_no_trade_band"
                notes["orders_skipped_by_weight_no_trade_band"] += 1
        if reason is None and not is_liquidation and float(policy.minimum_order_value) > 0:
            if order_value < float(policy.minimum_order_value):
                reason = "minimum_order_value"
                notes["orders_skipped_by_minimum_order_value"] += 1
        if reason is None:
            retained.append(intent)
            continue
        avoided_cost = _estimated_order_cost(quantity, price, side, cost_assumptions)
        notes["direct_filter_estimated_cost_avoided"] = round(float(notes.get("direct_filter_estimated_cost_avoided", 0.0)) + avoided_cost, 6)
        notes["direct_filter_estimated_turnover_avoided"] = round(float(notes.get("direct_filter_estimated_turnover_avoided", 0.0)) + order_value, 6)
        skipped.append({"symbol": symbol, "side": side, "quantity": quantity, "reason": reason, "estimated_cost_avoided": avoided_cost})
    notes["turnover_control_skipped_orders"] = tuple(skipped)
    return tuple(retained)


def _estimated_order_cost(
    quantity: int,
    price: float,
    side: str,
    cost_assumptions: PaperFillCostAssumptions,
) -> float:
    if quantity <= 0 or price <= 0:
        return 0.0
    if side == "sell":
        fill_price = price * (1 - cost_assumptions.slippage_bps / 10_000)
        gross = quantity * fill_price
        return round(max(gross * cost_assumptions.fee_rate, cost_assumptions.min_fee) + gross * cost_assumptions.stamp_tax_rate + abs(quantity * price - gross), 6)
    fill_price = price * (1 + cost_assumptions.slippage_bps / 10_000)
    gross = quantity * fill_price
    return round(max(gross * cost_assumptions.fee_rate, cost_assumptions.min_fee) + abs(gross - quantity * price), 6)


def _estimated_buy_cost(notional: float, cost_assumptions: PaperFillCostAssumptions) -> float:
    if notional <= 0:
        return 0.0
    slippage = notional * cost_assumptions.slippage_bps / 10_000
    gross = notional + slippage
    return round(max(gross * cost_assumptions.fee_rate, cost_assumptions.min_fee) + slippage, 6)


def _estimated_sell_cost(notional: float, cost_assumptions: PaperFillCostAssumptions) -> float:
    if notional <= 0:
        return 0.0
    slippage = notional * cost_assumptions.slippage_bps / 10_000
    gross = max(0.0, notional - slippage)
    return round(max(gross * cost_assumptions.fee_rate, cost_assumptions.min_fee) + gross * cost_assumptions.stamp_tax_rate + slippage, 6)


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
    execution_outcomes: Sequence[Any] = (),
    execution_reality: str = "base_paper_fill",
    cash_before_execution: float | None = None,
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
    serialized_outcomes = (
        tuple(_serialize_execution_outcome(outcome) for outcome in execution_outcomes)
        if execution_outcomes
        else _base_execution_outcomes(proposal, fill_result, cash_before_execution=float(cash_before_execution or 0.0))
    )
    execution_summary = summarize_execution_outcomes(execution_outcomes) if execution_outcomes else {
        "attempted_order_count": len(proposal.intents),
        "fill_ratio": round(len(fill_result.filled_trades) / len(proposal.intents), 6) if proposal.intents else 0.0,
        "partial_fill_count": 0,
        "rejected_order_count": len(fill_result.rejected_fills),
        "deferred_order_count": 0,
        "rejection_reasons": rejected_details["rejection_reasons"],
        "rule_coverage": {},
        "metadata_availability": {},
    }
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
        "attempted_order_count": int(execution_summary["attempted_order_count"]),
        "execution_fill_ratio": float(execution_summary["fill_ratio"]),
        "partial_fill_count": int(execution_summary["partial_fill_count"]),
        "rejected_order_count": int(execution_summary["rejected_order_count"]),
        "deferred_order_count": int(execution_summary["deferred_order_count"]),
        "execution_rejection_reasons": execution_summary["rejection_reasons"],
        "rule_coverage": (
            summarize_rule_coverage(execution_outcomes)
            if execution_outcomes
            else execution_summary["rule_coverage"]
        ),
        "metadata_availability": (
            summarize_metadata_availability(execution_outcomes)
            if execution_outcomes
            else execution_summary["metadata_availability"]
        ),
        "execution_reality": execution_reality,
        "execution_outcomes": serialized_outcomes,
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
        "turnover_aware_attribution": _turnover_attribution_from_notes(build_notes),
        "raw_orders_before_controls": int(build_notes.get("raw_orders_before_controls", build_notes.get("orders_proposed_before_turnover_controls", len(proposal.intents)))),
        "orders_after_rank_hysteresis": int(build_notes.get("orders_after_rank_hysteresis", len(proposal.intents))),
        "orders_after_score_improvement": int(build_notes.get("orders_after_score_improvement", len(proposal.intents))),
        "orders_after_weight_no_trade_band": int(build_notes.get("orders_after_weight_no_trade_band", len(proposal.intents))),
        "orders_after_minimum_order_value": int(build_notes.get("orders_after_minimum_order_value", len(proposal.intents))),
        "orders_after_minimum_holding_period": int(build_notes.get("orders_after_minimum_holding_period", len(proposal.intents))),
        "final_orders_retained": int(build_notes.get("final_orders_retained", len(proposal.intents))),
        "orders_proposed_before_turnover_controls": int(build_notes.get("orders_proposed_before_turnover_controls", len(proposal.intents))),
        "orders_proposed_after_candidate_controls": int(build_notes.get("orders_proposed_after_candidate_controls", len(proposal.intents))),
        "orders_retained": int(build_notes.get("orders_retained", len(proposal.intents))),
        "orders_skipped_by_rank_hysteresis": int(build_notes.get("orders_skipped_by_rank_hysteresis", 0)),
        "orders_skipped_by_score_improvement": int(build_notes.get("orders_skipped_by_score_improvement", 0)),
        "orders_skipped_by_weight_no_trade_band": int(build_notes.get("orders_skipped_by_weight_no_trade_band", 0)),
        "orders_skipped_by_minimum_order_value": int(build_notes.get("orders_skipped_by_minimum_order_value", 0)),
        "orders_skipped_by_minimum_holding_period": int(build_notes.get("orders_skipped_by_minimum_holding_period", 0)),
        "direct_filter_estimated_cost_avoided": round(float(build_notes.get("direct_filter_estimated_cost_avoided", 0.0)), 6),
        "direct_filter_estimated_turnover_avoided": round(float(build_notes.get("direct_filter_estimated_turnover_avoided", 0.0)), 6),
        "positions_retained_due_to_hysteresis": int(build_notes.get("positions_retained_due_to_hysteresis", 0)),
        "replacements_prevented": int(build_notes.get("replacements_prevented", 0)),
        "forced_required_exits_bypassed_turnover_controls": int(build_notes.get("forced_required_exits_bypassed_turnover_controls", 0)),
        "score_improvement_evaluated_replacement_count": int(build_notes.get("score_improvement_evaluated_replacement_count", 0)),
        "score_improvement_triggered_count": int(build_notes.get("score_improvement_triggered_count", 0)),
        "start_prices": dict(start_prices),
        "end_prices": dict(end_prices),
    }


def _turnover_attribution_from_notes(notes: Mapping[str, Any]) -> Mapping[str, Any]:
    selection_attribution = {
        "raw_ranked_candidates": int(notes.get("raw_ranked_candidates", 0)),
        "existing_positions_considered": int(notes.get("existing_positions_considered", 0)),
        "candidates_after_rank_hysteresis": int(notes.get("candidates_after_rank_hysteresis", 0)),
        "replacements_evaluated": int(notes.get("replacements_evaluated", notes.get("score_improvement_evaluated_replacement_count", 0))),
        "replacements_blocked_by_score_threshold": int(notes.get("replacements_blocked_by_score_threshold", notes.get("score_improvement_triggered_count", 0))),
        "target_positions_retained": int(notes.get("target_positions_retained", 0)),
        "positions_retained_due_to_hysteresis": int(notes.get("positions_retained_due_to_hysteresis", 0)),
        "minimum_holding_period_retentions": int(notes.get("orders_skipped_by_minimum_holding_period", 0)),
    }
    order_construction_attribution = {
        "raw_target_weight_deltas": int(notes.get("raw_target_weight_deltas", 0)),
        "orders_after_weight_no_trade_band": int(notes.get("orders_after_weight_no_trade_band", 0)),
        "orders_after_minimum_order_value": int(notes.get("orders_after_minimum_order_value", 0)),
        "orders_removed_as_zero_delta": int(notes.get("orders_removed_as_zero_delta", 0)),
        "orders_removed_below_lot": int(notes.get("orders_removed_below_lot", 0)),
        "orders_removed_by_cash_resize": int(notes.get("orders_removed_by_cash_resize", 0)),
        "orders_removed_missing_price": int(notes.get("orders_removed_missing_price", 0)),
        "orders_merged_or_net_adjusted": int(notes.get("orders_merged_or_net_adjusted", 0)),
        "orders_removed_by_weight_no_trade_band": int(notes.get("orders_skipped_by_weight_no_trade_band", 0)),
        "orders_removed_by_minimum_order_value": int(notes.get("orders_skipped_by_minimum_order_value", 0)),
        "final_order_intents": int(notes.get("order_final_order_intents", notes.get("final_orders_retained", 0))),
    }
    return {
        "selection_attribution": selection_attribution,
        "order_construction_attribution": order_construction_attribution,
        "raw_orders_before_controls": int(notes.get("raw_orders_before_controls", 0)),
        "raw_ranked_candidates": selection_attribution["raw_ranked_candidates"],
        "existing_positions_considered": selection_attribution["existing_positions_considered"],
        "candidates_after_rank_hysteresis": selection_attribution["candidates_after_rank_hysteresis"],
        "replacements_evaluated": selection_attribution["replacements_evaluated"],
        "replacements_blocked_by_score_threshold": selection_attribution["replacements_blocked_by_score_threshold"],
        "target_positions_retained": selection_attribution["target_positions_retained"],
        "raw_target_weight_deltas": order_construction_attribution["raw_target_weight_deltas"],
        "orders_removed_as_zero_delta": order_construction_attribution["orders_removed_as_zero_delta"],
        "orders_removed_below_lot": order_construction_attribution["orders_removed_below_lot"],
        "orders_removed_by_cash_resize": order_construction_attribution["orders_removed_by_cash_resize"],
        "orders_removed_missing_price": order_construction_attribution["orders_removed_missing_price"],
        "orders_merged_or_net_adjusted": order_construction_attribution["orders_merged_or_net_adjusted"],
        "order_final_order_intents": order_construction_attribution["final_order_intents"],
        "orders_after_rank_hysteresis": int(notes.get("orders_after_rank_hysteresis", 0)),
        "orders_after_score_improvement": int(notes.get("orders_after_score_improvement", 0)),
        "orders_after_weight_no_trade_band": int(notes.get("orders_after_weight_no_trade_band", 0)),
        "orders_after_minimum_order_value": int(notes.get("orders_after_minimum_order_value", 0)),
        "orders_after_minimum_holding_period": int(notes.get("orders_after_minimum_holding_period", 0)),
        "final_orders_retained": int(notes.get("final_orders_retained", notes.get("orders_retained", 0))),
        "orders_proposed_before_turnover_controls": int(notes.get("orders_proposed_before_turnover_controls", 0)),
        "orders_proposed_after_candidate_controls": int(notes.get("orders_proposed_after_candidate_controls", 0)),
        "orders_retained": int(notes.get("orders_retained", 0)),
        "orders_skipped_by_rank_hysteresis": int(notes.get("orders_skipped_by_rank_hysteresis", 0)),
        "orders_skipped_by_score_improvement": int(notes.get("orders_skipped_by_score_improvement", 0)),
        "orders_skipped_by_weight_no_trade_band": int(notes.get("orders_skipped_by_weight_no_trade_band", 0)),
        "orders_skipped_by_minimum_order_value": int(notes.get("orders_skipped_by_minimum_order_value", 0)),
        "orders_skipped_by_minimum_holding_period": int(notes.get("orders_skipped_by_minimum_holding_period", 0)),
        "direct_filter_estimated_cost_avoided": round(float(notes.get("direct_filter_estimated_cost_avoided", 0.0)), 6),
        "direct_filter_estimated_turnover_avoided": round(float(notes.get("direct_filter_estimated_turnover_avoided", 0.0)), 6),
        "positions_retained_due_to_hysteresis": int(notes.get("positions_retained_due_to_hysteresis", 0)),
        "replacements_prevented": int(notes.get("replacements_prevented", 0)),
        "forced_required_exits_bypassed_turnover_controls": int(notes.get("forced_required_exits_bypassed_turnover_controls", 0)),
        "score_improvement_evaluated_replacement_count": int(notes.get("score_improvement_evaluated_replacement_count", 0)),
        "score_improvement_triggered_count": int(notes.get("score_improvement_triggered_count", 0)),
        "skipped_orders": notes.get("turnover_control_skipped_orders", ()),
    }


def _serialize_execution_outcome(outcome: Any) -> Mapping[str, Any]:
    return {
        "order_id": outcome.order_id,
        "date": outcome.date,
        "symbol": outcome.symbol,
        "side": outcome.side,
        "requested_quantity": outcome.requested_quantity,
        "normalized_quantity": outcome.normalized_quantity,
        "filled_quantity": outcome.filled_quantity,
        "unfilled_quantity": outcome.unfilled_quantity,
        "execution_price": outcome.execution_price,
        "gross_value": outcome.gross_value,
        "fee_breakdown": dict(outcome.fee_breakdown),
        "total_cost": outcome.total_cost,
        "status": outcome.status,
        "rejection_or_deferral_reason": outcome.rejection_or_deferral_reason,
        "sellable_quantity_before": outcome.sellable_quantity_before,
        "cash_available_before": outcome.cash_available_before,
        "cash_available_after": outcome.cash_available_after,
        "rule_diagnostics": dict(outcome.rule_diagnostics),
        "metadata_availability": dict(outcome.metadata_availability),
    }


def _base_execution_outcomes(
    proposal: OrderIntentProposal,
    fill_result: Any,
    *,
    cash_before_execution: float,
) -> tuple[Mapping[str, Any], ...]:
    filled_by_key: dict[tuple[str, str, int], list[Any]] = {}
    for trade in fill_result.filled_trades:
        filled_by_key.setdefault((str(trade.symbol), str(trade.side), int(trade.quantity)), []).append(trade)
    rejected_by_key: dict[tuple[str, str, int | None], list[Any]] = {}
    for rejected in fill_result.rejected_fills:
        rejected_by_key.setdefault((str(rejected.symbol), str(rejected.side), rejected.requested_quantity), []).append(rejected)

    outcomes: list[Mapping[str, Any]] = []
    cash_after = round(float(cash_before_execution), 6)
    for index, intent in enumerate(proposal.intents, start=1):
        side = str(intent.side.value if isinstance(intent.side, OrderIntentSide) else intent.side)
        quantity = int(intent.target_shares or 0)
        key = (str(intent.symbol), side, quantity)
        trade = filled_by_key.get(key, []).pop(0) if filled_by_key.get(key) else None
        rejected = rejected_by_key.get((str(intent.symbol), side, intent.target_shares), []).pop(0) if rejected_by_key.get((str(intent.symbol), side, intent.target_shares)) else None
        if trade is not None:
            cash_after = round(float(cash_after) + float(trade.cash_impact), 6)
            outcomes.append(
                {
                    "order_id": f"{proposal.run_label or 'proposal'}:{index}:{intent.symbol}:{side}:{quantity}",
                    "date": None,
                    "symbol": intent.symbol,
                    "side": side,
                    "requested_quantity": quantity,
                    "normalized_quantity": quantity,
                    "filled_quantity": int(trade.quantity),
                    "unfilled_quantity": 0,
                    "execution_price": float(trade.fill_price),
                    "gross_value": float(trade.gross_notional),
                    "fee_breakdown": {
                        "commission": float(trade.fee),
                        "transaction_tax": round(float(trade.total_cost) - float(trade.fee) - float(trade.slippage_cost), 6),
                        "transfer_or_exchange_fee": 0.0,
                        "slippage_cost": float(trade.slippage_cost),
                    },
                    "total_cost": float(trade.total_cost),
                    "status": "filled",
                    "rejection_or_deferral_reason": None,
                    "cash_available_after": cash_after,
                }
            )
        elif rejected is not None:
            outcomes.append(
                {
                    "order_id": f"{proposal.run_label or 'proposal'}:{index}:{intent.symbol}:{side}:{quantity}",
                    "date": None,
                    "symbol": intent.symbol,
                    "side": side,
                    "requested_quantity": quantity,
                    "normalized_quantity": quantity,
                    "filled_quantity": 0,
                    "unfilled_quantity": quantity,
                    "execution_price": None,
                    "gross_value": 0.0,
                    "fee_breakdown": {},
                    "total_cost": 0.0,
                    "status": "rejected",
                    "rejection_or_deferral_reason": ",".join(rejected.reasons),
                    "cash_available_after": cash_after,
                }
            )
    return tuple(outcomes)


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
        turnover_aware_attribution=_aggregate_turnover_attribution(smoke_report.per_window_metrics),
    )


def _aggregate_turnover_attribution(per_window: tuple[Mapping[str, Any], ...]) -> Mapping[str, Any]:
    fields = (
        "raw_ranked_candidates",
        "existing_positions_considered",
        "candidates_after_rank_hysteresis",
        "replacements_evaluated",
        "replacements_blocked_by_score_threshold",
        "target_positions_retained",
        "raw_target_weight_deltas",
        "orders_removed_as_zero_delta",
        "orders_removed_below_lot",
        "orders_removed_by_cash_resize",
        "orders_removed_missing_price",
        "orders_merged_or_net_adjusted",
        "order_final_order_intents",
        "raw_orders_before_controls",
        "orders_after_rank_hysteresis",
        "orders_after_score_improvement",
        "orders_after_weight_no_trade_band",
        "orders_after_minimum_order_value",
        "orders_after_minimum_holding_period",
        "final_orders_retained",
        "orders_proposed_before_turnover_controls",
        "orders_proposed_after_candidate_controls",
        "orders_retained",
        "orders_skipped_by_rank_hysteresis",
        "orders_skipped_by_score_improvement",
        "orders_skipped_by_weight_no_trade_band",
        "orders_skipped_by_minimum_order_value",
        "orders_skipped_by_minimum_holding_period",
        "positions_retained_due_to_hysteresis",
        "replacements_prevented",
        "forced_required_exits_bypassed_turnover_controls",
        "score_improvement_evaluated_replacement_count",
        "score_improvement_triggered_count",
    )
    float_fields = ("direct_filter_estimated_cost_avoided", "direct_filter_estimated_turnover_avoided")
    result: dict[str, Any] = {field: 0 for field in fields}
    for field in float_fields:
        result[field] = 0.0
    skipped: list[Mapping[str, Any]] = []
    for metrics in per_window:
        attribution = metrics.get("turnover_aware_attribution", metrics)
        for field in fields:
            result[field] += int(attribution.get(field, 0))
        for field in float_fields:
            result[field] = round(float(result[field]) + float(attribution.get(field, 0.0)), 6)
        skipped.extend(tuple(attribution.get("skipped_orders", ())))
    result["skipped_orders"] = tuple(skipped)
    result["selection_attribution"] = {
        "raw_ranked_candidates": result["raw_ranked_candidates"],
        "existing_positions_considered": result["existing_positions_considered"],
        "candidates_after_rank_hysteresis": result["candidates_after_rank_hysteresis"],
        "replacements_evaluated": result["replacements_evaluated"],
        "replacements_blocked_by_score_threshold": result["replacements_blocked_by_score_threshold"],
        "target_positions_retained": result["target_positions_retained"],
        "positions_retained_due_to_hysteresis": result["positions_retained_due_to_hysteresis"],
        "minimum_holding_period_retentions": result["orders_skipped_by_minimum_holding_period"],
    }
    result["order_construction_attribution"] = {
        "raw_target_weight_deltas": result["raw_target_weight_deltas"],
        "orders_after_weight_no_trade_band": result["orders_after_weight_no_trade_band"],
        "orders_after_minimum_order_value": result["orders_after_minimum_order_value"],
        "orders_removed_as_zero_delta": result["orders_removed_as_zero_delta"],
        "orders_removed_below_lot": result["orders_removed_below_lot"],
        "orders_removed_by_cash_resize": result["orders_removed_by_cash_resize"],
        "orders_removed_missing_price": result["orders_removed_missing_price"],
        "orders_merged_or_net_adjusted": result["orders_merged_or_net_adjusted"],
        "orders_removed_by_weight_no_trade_band": result["orders_skipped_by_weight_no_trade_band"],
        "orders_removed_by_minimum_order_value": result["orders_skipped_by_minimum_order_value"],
        "final_order_intents": result["order_final_order_intents"],
    }
    return result


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
        "turnover_aware_attribution": report.turnover_aware_attribution,
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
            "previous_close": bar.previous_close,
            "adjustment_flag": bar.adjustment_flag,
            "trade_status": bar.trade_status,
            "is_st": bar.is_st,
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
                previous_close=None if pd.isna(row.get("previous_close")) else float(row.get("previous_close")),
                adjustment_flag=None if pd.isna(row.get("adjustment_flag")) else str(row.get("adjustment_flag")),
                trade_status=None if pd.isna(row.get("trade_status")) else str(row.get("trade_status")),
                is_st=None if pd.isna(row.get("is_st")) else bool(row.get("is_st")),
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
    if config.cost_multiplier <= 0:
        raise ValueError("cost_multiplier must be positive")
    if config.max_rejected_trade_ratio_warning < 0 or config.max_rejected_trade_ratio_warning > 1:
        raise ValueError("max_rejected_trade_ratio_warning must be in [0, 1]")
    if config.ranking_mode not in SUPPORTED_REAL_DATA_SCALEUP_RANKING_MODES:
        raise ValueError(f"unsupported ranking_mode: {config.ranking_mode}")
    _validate_turnover_aware_config(config.turnover_aware_rebalance)


def _validate_turnover_aware_config(config: TurnoverAwareRebalanceConfig) -> None:
    if config.entry_rank_threshold is not None and int(config.entry_rank_threshold) <= 0:
        raise ValueError("entry_rank_threshold must be positive when provided")
    if config.exit_rank_threshold is not None and int(config.exit_rank_threshold) <= 0:
        raise ValueError("exit_rank_threshold must be positive when provided")
    if (
        config.enabled
        and config.entry_rank_threshold is not None
        and config.exit_rank_threshold is not None
        and int(config.exit_rank_threshold) < int(config.entry_rank_threshold)
    ):
        raise ValueError("exit_rank_threshold must not be tighter than entry_rank_threshold")
    if config.minimum_score_improvement < 0:
        raise ValueError("minimum_score_improvement must be non-negative")
    if config.target_weight_no_trade_band < 0:
        raise ValueError("target_weight_no_trade_band must be non-negative")
    if config.minimum_order_value < 0:
        raise ValueError("minimum_order_value must be non-negative")
    if config.minimum_holding_days < 0:
        raise ValueError("minimum_holding_days must be non-negative")
    if config.normalized_turnover_penalty < 0:
        raise ValueError("normalized_turnover_penalty must be non-negative")
    if config.estimated_cost_multiplier <= 0:
        raise ValueError("estimated_cost_multiplier must be positive")


def _scale_cost_assumptions(
    assumptions: PaperFillCostAssumptions,
    multiplier: float,
) -> PaperFillCostAssumptions:
    if multiplier <= 0:
        raise ValueError("cost_multiplier must be positive")
    return PaperFillCostAssumptions(
        fee_rate=round(float(assumptions.fee_rate) * multiplier, 12),
        min_fee=round(float(assumptions.min_fee) * multiplier, 6),
        stamp_tax_rate=round(float(assumptions.stamp_tax_rate) * multiplier, 12),
        slippage_bps=round(float(assumptions.slippage_bps) * multiplier, 6),
        lot_size=int(assumptions.lot_size),
    )


def _a_share_execution_config(metadata: Mapping[str, Any]) -> AShareExecutionConfig:
    overrides = metadata.get("a_share_execution_config", {})
    if not isinstance(overrides, Mapping):
        overrides = {}
    return AShareExecutionConfig(
        buy_lot_size=int(overrides.get("buy_lot_size", 100)),
        buy_lot_increment=int(overrides.get("buy_lot_increment", 100)),
        odd_lot_sell_policy=str(overrides.get("odd_lot_sell_policy", "allow_position_residual")),
        enforce_t_plus_one=bool(overrides.get("enforce_t_plus_one", True)),
        max_participation_rate=float(overrides.get("max_participation_rate", 0.10)),
        block_suspended=bool(overrides.get("block_suspended", True)),
        block_unavailable_price=bool(overrides.get("block_unavailable_price", True)),
        block_one_price_limit=bool(overrides.get("block_one_price_limit", True)),
        default_price_limit_pct=float(overrides.get("default_price_limit_pct", 0.10)),
        price_limit_tolerance=float(overrides.get("price_limit_tolerance", 1e-6)),
    )


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
