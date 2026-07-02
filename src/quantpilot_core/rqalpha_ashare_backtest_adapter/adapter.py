"""Optional RQAlpha A-share adapter boundary."""

from __future__ import annotations

import importlib
import re
from collections.abc import Callable, Mapping

from quantpilot_core.rqalpha_ashare_backtest_adapter.contracts import (
    RqalphaAshareBacktestInput,
    RqalphaAshareBacktestResult,
    RqalphaAshareBacktestStatus,
)
from quantpilot_core.rqalpha_ashare_backtest_adapter.normalizer import (
    normalize_rqalpha_runner_output,
)


Runner = Callable[
    [RqalphaAshareBacktestInput],
    Mapping[str, object] | RqalphaAshareBacktestResult,
]


def run_rqalpha_ashare_backtest(
    backtest_input: RqalphaAshareBacktestInput,
    runner: Runner | None = None,
) -> RqalphaAshareBacktestResult:
    """Run only caller-supplied execution, otherwise return structured readiness."""

    validation_errors = _validate_input(backtest_input)
    if validation_errors:
        return _result(
            backtest_input,
            RqalphaAshareBacktestStatus.INVALID_INPUT,
            errors=validation_errors,
            notes=("Input failed the thin RQAlpha adapter validation.",),
        )

    if runner is not None:
        try:
            return normalize_rqalpha_runner_output(runner(backtest_input), backtest_input)
        except Exception as exc:  # pragma: no cover - defensive contract boundary
            return _result(
                backtest_input,
                RqalphaAshareBacktestStatus.NOT_EXECUTED,
                runtime_available=True,
                errors=(f"Runner failed: {exc}",),
                notes=("Caller-owned RQAlpha runner did not complete.",),
            )

    try:
        importlib.import_module("rqalpha")
    except ImportError:
        return _result(
            backtest_input,
            RqalphaAshareBacktestStatus.FRAMEWORK_MISSING,
            warnings=("Optional RQAlpha runtime is not installed.",),
            notes=("Missing framework is reported locally and does not block other paths.",),
        )

    if not _has_config(backtest_input.metadata):
        return _result(
            backtest_input,
            RqalphaAshareBacktestStatus.CONFIG_REQUIRED,
            runtime_available=True,
            warnings=("RQAlpha runtime is available, but no explicit config was supplied.",),
            notes=("The adapter does not build default configs or run fake backtests.",),
        )

    if not _has_data_bundle(backtest_input.metadata):
        return _result(
            backtest_input,
            RqalphaAshareBacktestStatus.DATA_BUNDLE_REQUIRED,
            runtime_available=True,
            warnings=("RQAlpha runtime is available, but no data bundle was supplied.",),
            notes=("A caller-owned runner and real local bundle are required for execution.",),
        )

    return _result(
        backtest_input,
        RqalphaAshareBacktestStatus.NOT_EXECUTED,
        runtime_available=True,
        warnings=("RQAlpha config and data hints are present, but no runner was supplied.",),
        notes=("QuantPilot keeps execution at the explicit caller-owned boundary.",),
    )


def _validate_input(backtest_input: RqalphaAshareBacktestInput) -> tuple[str, ...]:
    errors: list[str] = []
    if not backtest_input.strategy_id.strip():
        errors.append("strategy_id is required")
    if not backtest_input.symbols:
        errors.append("at least one symbol is required")
    if any(not symbol.strip() for symbol in backtest_input.symbols):
        errors.append("symbols must be non-empty strings")
    if backtest_input.initial_cash <= 0:
        errors.append("initial_cash must be greater than zero")
    if _is_iso_like(backtest_input.start_date) and _is_iso_like(backtest_input.end_date):
        if backtest_input.start_date > backtest_input.end_date:
            errors.append("start_date must be earlier than or equal to end_date")
    return tuple(errors)


def _is_iso_like(value: str) -> bool:
    return re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is not None


def _has_config(metadata: Mapping[str, object]) -> bool:
    return bool(metadata.get("rqalpha_config") or metadata.get("config"))


def _has_data_bundle(metadata: Mapping[str, object]) -> bool:
    return bool(
        metadata.get("data_bundle")
        or metadata.get("bundle_path")
        or metadata.get("data_bundle_path")
    )


def _result(
    backtest_input: RqalphaAshareBacktestInput,
    status: RqalphaAshareBacktestStatus,
    *,
    runtime_available: bool = False,
    warnings: tuple[str, ...] = (),
    errors: tuple[str, ...] = (),
    notes: tuple[str, ...] = (),
) -> RqalphaAshareBacktestResult:
    return RqalphaAshareBacktestResult(
        status=status.value,
        strategy_id=backtest_input.strategy_id,
        symbols=backtest_input.symbols,
        metrics=(),
        warnings=warnings,
        errors=errors,
        runtime_available=runtime_available,
        executed=False,
        notes=notes,
    )
