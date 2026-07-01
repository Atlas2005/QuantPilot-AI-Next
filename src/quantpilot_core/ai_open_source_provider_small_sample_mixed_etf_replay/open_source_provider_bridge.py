"""Approved local export bridge for open-source provider boundaries."""

from __future__ import annotations

from datetime import date
from typing import Any
from urllib.parse import urlparse

from quantpilot_core.alpha_sizing_etf_universe_tuning_loop import EtfCategory, InstrumentType
from quantpilot_core.ai_open_source_provider_small_sample_mixed_etf_replay.contracts import (
    ApprovedProviderSampleValidationResult,
    ApprovedSmallSampleRecord,
    OpenSourceProviderExportSpec,
    OpenSourceProviderName,
    ProviderExportSourceType,
)
from quantpilot_core.real_provider_mixed_etf_paper_replay import (
    ProviderSampleSourceType,
    RealProviderReplayInput,
)


CANONICAL_FIELDS = {
    "symbol",
    "trade_date",
    "instrument_type",
    "open",
    "high",
    "low",
    "close",
    "volume",
}


def validate_approved_provider_export(
    spec: OpenSourceProviderExportSpec,
    records: tuple[dict[str, Any], ...],
) -> ApprovedProviderSampleValidationResult:
    """Validate approved local provider exports and normalize to P39 records."""

    blockers: list[str] = []
    flags: list[str] = []
    provider_names = {item.value for item in OpenSourceProviderName}
    source_types = {item.value for item in ProviderExportSourceType}
    if spec.provider_name not in provider_names:
        blockers.append("provider_name_unknown")
    if spec.source_type not in source_types:
        blockers.append("source_type_unknown")
    if _is_remote_uri(spec.source_uri):
        blockers.append("remote_source_rejected")
    if not spec.approved_by.strip():
        blockers.append("approved_by_missing")
    if not spec.approval_reason.strip():
        blockers.append("approval_reason_missing")
    if not spec.export_timestamp.strip():
        blockers.append("export_timestamp_missing")
    if not spec.provider_schema_mapping:
        blockers.append("provider_schema_mapping_missing")
    elif CANONICAL_FIELDS - set(spec.provider_schema_mapping):
        blockers.append("provider_schema_mapping_incomplete")
    if not records:
        blockers.append("records_missing")

    start = _parse_date(spec.evaluation_start, blockers, "evaluation_start")
    end = _parse_date(spec.evaluation_end, blockers, "evaluation_end")
    if start and end and start > end:
        blockers.append("evaluation_window_reversed")

    normalized: list[ApprovedSmallSampleRecord] = []
    seen: set[tuple[str, str]] = set()
    row_dates: list[str] = []
    stock_seen = False
    etf_seen = False

    for index, row in enumerate(records):
        normalized_row = _normalize_row(spec.provider_schema_mapping, row, blockers, index)
        if normalized_row is None:
            continue
        row_date = _parse_date(normalized_row.trade_date, blockers, f"row_trade_date:{index}")
        if row_date is not None and end is not None and row_date > end:
            blockers.append(f"future_dated_row:{normalized_row.symbol}:{normalized_row.trade_date}")
        key = (normalized_row.symbol, normalized_row.trade_date)
        if key in seen:
            blockers.append(f"duplicate_symbol_date:{normalized_row.symbol}:{normalized_row.trade_date}")
        seen.add(key)
        row_dates.append(normalized_row.trade_date)
        if normalized_row.instrument_type == InstrumentType.STOCK.value:
            stock_seen = True
        elif normalized_row.instrument_type == InstrumentType.ETF.value:
            etf_seen = True
            if not normalized_row.etf_category:
                blockers.append(f"etf_category_missing:{normalized_row.symbol}")
            elif normalized_row.etf_category not in {item.value for item in EtfCategory}:
                blockers.append(f"etf_category_unknown:{normalized_row.symbol}")
        else:
            blockers.append(f"instrument_type_unknown:{normalized_row.symbol}")
        normalized.append(normalized_row)

    if not stock_seen:
        blockers.append("stock_coverage_missing")
    if not etf_seen:
        blockers.append("etf_coverage_missing")
    if row_dates and row_dates != sorted(row_dates):
        flags.append("dates_normalized_deterministically")

    sorted_records = tuple(sorted(normalized, key=lambda item: (item.trade_date, item.symbol)))
    quality_flags = tuple(
        sorted(
            set(
                flags
                + [
                    "approval_metadata_present",
                    "provider_schema_mapping_explicit",
                    f"provider_boundary:{spec.provider_name}",
                    "local_export_style_sample",
                ]
            )
        )
    )

    if blockers:
        return ApprovedProviderSampleValidationResult(
            ok=False,
            provider_name=spec.provider_name if spec.provider_name in provider_names else None,
            quality_flags=quality_flags,
            blockers=tuple(sorted(set(blockers))),
            normalized_records=sorted_records,
            replay_input=None,
        )

    replay_input = RealProviderReplayInput(
        sample_source_type=_to_p39_source_type(spec.source_type),
        sample_source_uri=spec.source_uri,
        evaluation_start=spec.evaluation_start,
        evaluation_end=spec.evaluation_end,
        initial_cash=spec.initial_cash,
        records=tuple(_to_p39_row(item) for item in sorted_records),
        evidence_refs=spec.evidence_refs,
    )
    return ApprovedProviderSampleValidationResult(
        ok=True,
        provider_name=spec.provider_name,
        quality_flags=quality_flags,
        blockers=(),
        normalized_records=sorted_records,
        replay_input=replay_input,
    )


def _normalize_row(
    mapping: dict[str, str],
    row: dict[str, Any],
    blockers: list[str],
    index: int,
) -> ApprovedSmallSampleRecord | None:
    missing_mapping = [field for field in CANONICAL_FIELDS if field not in mapping]
    if missing_mapping:
        return None
    missing_source_fields = sorted(
        mapping[field] for field in CANONICAL_FIELDS if mapping[field] not in row
    )
    if missing_source_fields:
        blockers.append(f"missing_ohlcv_fields:{index}:{','.join(missing_source_fields)}")
        return None
    try:
        close = _positive_float(row[mapping["close"]], "close", blockers, index)
        volume = _positive_float(row[mapping["volume"]], "volume", blockers, index)
        return ApprovedSmallSampleRecord(
            symbol=str(row[mapping["symbol"]]).strip(),
            trade_date=str(row[mapping["trade_date"]]).strip(),
            instrument_type=str(row[mapping["instrument_type"]]).strip(),
            open=_positive_float(row[mapping["open"]], "open", blockers, index),
            high=_positive_float(row[mapping["high"]], "high", blockers, index),
            low=_positive_float(row[mapping["low"]], "low", blockers, index),
            close=close,
            volume=volume,
            etf_category=str(row.get(mapping.get("etf_category", "etf_category"), "")).strip()
            or None,
            provider_fields=dict(row),
        )
    except ValueError:
        return None


def _positive_float(value: Any, field: str, blockers: list[str], index: int) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        blockers.append(f"non_numeric_{field}:{index}")
        raise ValueError(field)
    if number <= 0:
        blockers.append(f"missing_{field}:{index}")
        raise ValueError(field)
    return number


def _to_p39_row(record: ApprovedSmallSampleRecord) -> dict[str, Any]:
    row = {
        "symbol": record.symbol,
        "trade_date": record.trade_date,
        "instrument_type": record.instrument_type,
        "open": record.open,
        "high": record.high,
        "low": record.low,
        "close": record.close,
        "volume": record.volume,
    }
    if record.etf_category:
        row["etf_category"] = record.etf_category
    return row


def _to_p39_source_type(source_type: str) -> str:
    if source_type == ProviderExportSourceType.DETERMINISTIC_FIXTURE.value:
        return ProviderSampleSourceType.FIXTURE.value
    return ProviderSampleSourceType.APPROVED_MANUAL_EXPORT.value


def _parse_date(value: str, blockers: list[str], field_name: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        blockers.append(f"invalid_date:{field_name}")
        return None


def _is_remote_uri(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"}
