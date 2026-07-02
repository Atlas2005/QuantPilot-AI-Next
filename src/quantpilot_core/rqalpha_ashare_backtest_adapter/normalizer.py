"""Normalize explicitly supplied RQAlpha runner outputs."""

from __future__ import annotations

from collections.abc import Mapping

from quantpilot_core.rqalpha_ashare_backtest_adapter.contracts import (
    RqalphaAshareBacktestInput,
    RqalphaAshareBacktestMetric,
    RqalphaAshareBacktestResult,
    RqalphaAshareBacktestStatus,
)


def normalize_rqalpha_runner_output(
    output: Mapping[str, object] | RqalphaAshareBacktestResult,
    backtest_input: RqalphaAshareBacktestInput,
) -> RqalphaAshareBacktestResult:
    """Convert a caller-owned runner result into QuantPilot's thin contract."""

    if isinstance(output, RqalphaAshareBacktestResult):
        return output

    status = _normalize_status(output.get("status"))
    executed = bool(output.get("executed", False))
    if status is None:
        status = (
            RqalphaAshareBacktestStatus.COMPLETED.value
            if executed is True
            else RqalphaAshareBacktestStatus.NOT_EXECUTED.value
        )
    elif status == RqalphaAshareBacktestStatus.COMPLETED.value:
        executed = True

    return RqalphaAshareBacktestResult(
        status=status,
        strategy_id=str(output.get("strategy_id") or backtest_input.strategy_id),
        symbols=_normalize_symbols(output.get("symbols"), backtest_input.symbols),
        metrics=_normalize_metrics(output.get("metrics")),
        warnings=_normalize_text_tuple(output.get("warnings")),
        errors=_normalize_text_tuple(output.get("errors")),
        runtime_available=bool(output.get("runtime_available", True)),
        executed=executed,
        notes=_normalize_text_tuple(output.get("notes")),
    )


def _normalize_status(value: object) -> str | None:
    if isinstance(value, RqalphaAshareBacktestStatus):
        return value.value
    if isinstance(value, str):
        normalized = value.strip().lower()
        allowed = {status.value for status in RqalphaAshareBacktestStatus}
        if normalized in allowed:
            return normalized
    return None


def _normalize_symbols(value: object, fallback: tuple[str, ...]) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, tuple):
        symbols = tuple(str(item) for item in value if str(item).strip())
        return symbols or fallback
    if isinstance(value, list):
        symbols = tuple(str(item) for item in value if str(item).strip())
        return symbols or fallback
    return fallback


def _normalize_metrics(value: object) -> tuple[RqalphaAshareBacktestMetric, ...]:
    if value is None:
        return ()
    if isinstance(value, Mapping):
        return tuple(
            RqalphaAshareBacktestMetric(name=str(name), value=_metric_value(metric_value))
            for name, metric_value in value.items()
        )
    if isinstance(value, (list, tuple)):
        metrics: list[RqalphaAshareBacktestMetric] = []
        for item in value:
            if isinstance(item, RqalphaAshareBacktestMetric):
                metrics.append(item)
            elif isinstance(item, Mapping) and "name" in item:
                metrics.append(
                    RqalphaAshareBacktestMetric(
                        name=str(item["name"]),
                        value=_metric_value(item.get("value")),
                        source=str(item.get("source", "rqalpha")),
                    )
                )
        return tuple(metrics)
    return ()


def _metric_value(value: object) -> float | str | bool | None:
    if isinstance(value, (float, str, bool)) or value is None:
        return value
    if isinstance(value, int):
        return float(value)
    return str(value)


def _normalize_text_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value)
    return (str(value),)
