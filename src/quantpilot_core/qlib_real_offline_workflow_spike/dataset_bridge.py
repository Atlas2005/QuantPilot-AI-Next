"""Qlib-style local dataset bridge for P41."""

from __future__ import annotations

from datetime import date
from typing import Any

from quantpilot_core.qlib_real_offline_workflow_spike.contracts import (
    QlibDatasetSourceType,
    QlibFieldMapping,
    QlibInstrumentKind,
    QlibLocalDatasetSpec,
)


def build_qlib_local_dataset_spec(
    *,
    dataset_id: str,
    provider_name: str,
    source_type: str,
    records: tuple[dict[str, Any], ...],
    field_mapping: QlibFieldMapping,
    evaluation_start: str,
    evaluation_end: str,
    mixed_mode: bool = True,
    benchmark_candidate: str = "000300.SH",
) -> QlibLocalDatasetSpec:
    """Validate local records and produce a Qlib-style dataset spec."""

    blockers = validate_qlib_dataset_records(
        records=records,
        field_mapping=field_mapping,
        evaluation_start=evaluation_start,
        evaluation_end=evaluation_end,
        mixed_mode=mixed_mode,
        source_type=source_type,
    )
    if blockers:
        raise ValueError(";".join(blockers))

    normalized = tuple(sorted((dict(row) for row in records), key=lambda row: (str(row[field_mapping.trade_date]), str(row[field_mapping.symbol]))))
    symbols = tuple(sorted({str(row[field_mapping.symbol]) for row in normalized}))
    calendar = tuple(sorted({str(row[field_mapping.trade_date]) for row in normalized}))
    stock_symbols = {
        str(row[field_mapping.symbol])
        for row in normalized
        if str(row[field_mapping.instrument_kind]) == QlibInstrumentKind.A_SHARE_STOCK.value
    }
    etf_symbols = {
        str(row[field_mapping.symbol])
        for row in normalized
        if str(row[field_mapping.instrument_kind]) == QlibInstrumentKind.EXCHANGE_TRADED_ETF.value
    }
    quality_flags = ["local_dataset_records_normalized"]
    if tuple(str(row[field_mapping.trade_date]) for row in records) != tuple(sorted(str(row[field_mapping.trade_date]) for row in records)):
        quality_flags.append("dates_normalized_deterministically")
    return QlibLocalDatasetSpec(
        dataset_id=dataset_id,
        provider_name=provider_name,
        source_type=source_type,
        stock_count=len(stock_symbols),
        etf_count=len(etf_symbols),
        instrument_symbols=symbols,
        trading_calendar=calendar,
        records=normalized,
        field_mapping=field_mapping,
        calendar_assumptions=(
            "local_trade_dates_define_calendar",
            f"window:{evaluation_start}:{evaluation_end}",
        ),
        cost_model_assumptions=(
            "commission_slippage_from_p40_replay",
            "etf_stamp_duty_zero_fixture_assumption",
        ),
        benchmark_candidate=benchmark_candidate,
        known_limitations=(
            "small_sample_only",
            "qlib_runtime_not_executed_by_default",
            "no_live_provider_fetch",
        ),
        quality_flags=tuple(sorted(set(quality_flags))),
    )


def validate_qlib_dataset_records(
    *,
    records: tuple[dict[str, Any], ...],
    field_mapping: QlibFieldMapping,
    evaluation_start: str,
    evaluation_end: str,
    mixed_mode: bool,
    source_type: str,
) -> tuple[str, ...]:
    """Return dataset blockers without touching the filesystem or network."""

    blockers: list[str] = []
    if source_type not in {item.value for item in QlibDatasetSourceType}:
        blockers.append("source_type_unknown")
    if not records:
        blockers.append("records_missing")
    end = _parse_date(evaluation_end, blockers, "evaluation_end")
    _parse_date(evaluation_start, blockers, "evaluation_start")

    seen: set[tuple[str, str]] = set()
    stock_seen = False
    etf_seen = False
    required_fields = (
        field_mapping.symbol,
        field_mapping.trade_date,
        field_mapping.open,
        field_mapping.high,
        field_mapping.low,
        field_mapping.close,
        field_mapping.volume,
        field_mapping.instrument_kind,
    )
    for index, row in enumerate(records):
        missing = sorted(field for field in required_fields if field not in row)
        if missing:
            blockers.append(f"missing_ohlcv_fields:{index}:{','.join(missing)}")
            continue
        symbol = str(row[field_mapping.symbol])
        trade_date = str(row[field_mapping.trade_date])
        row_date = _parse_date(trade_date, blockers, f"row_trade_date:{index}")
        if row_date is not None and end is not None and row_date > end:
            blockers.append(f"future_dated_row:{symbol}:{trade_date}")
        key = (symbol, trade_date)
        if key in seen:
            blockers.append(f"duplicate_symbol_date:{symbol}:{trade_date}")
        seen.add(key)
        _validate_price_volume(row, field_mapping, blockers, index)
        kind = str(row[field_mapping.instrument_kind])
        if kind == QlibInstrumentKind.A_SHARE_STOCK.value:
            stock_seen = True
        elif kind == QlibInstrumentKind.EXCHANGE_TRADED_ETF.value:
            etf_seen = True
            if not str(row.get(field_mapping.etf_category, "")).strip():
                blockers.append(f"etf_category_missing:{symbol}")
        else:
            blockers.append(f"instrument_kind_unknown:{symbol}")
    if mixed_mode and not stock_seen:
        blockers.append("stock_coverage_missing")
    if mixed_mode and not etf_seen:
        blockers.append("etf_coverage_missing")
    return tuple(sorted(set(blockers)))


def _validate_price_volume(
    row: dict[str, Any],
    mapping: QlibFieldMapping,
    blockers: list[str],
    index: int,
) -> None:
    for label, field in (
        ("open", mapping.open),
        ("high", mapping.high),
        ("low", mapping.low),
        ("close", mapping.close),
        ("volume", mapping.volume),
    ):
        value = row.get(field)
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            blockers.append(f"non_numeric_{label}:{index}")
            continue
        if numeric <= 0:
            blockers.append(f"missing_{label}:{index}")


def _parse_date(value: str, blockers: list[str], field_name: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        blockers.append(f"invalid_date:{field_name}")
        return None
