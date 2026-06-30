"""Local provider-like sample bridge for P39."""

from __future__ import annotations

from datetime import date
from typing import Any
from urllib.parse import urlparse

from quantpilot_core.alpha_sizing_etf_universe_tuning_loop import EtfCategory, InstrumentType
from quantpilot_core.real_provider_mixed_etf_paper_replay.contracts import (
    ProviderMixedUniverseSample,
    ProviderSampleSourceType,
    ProviderSampleValidationResult,
    RealProviderReplayInput,
)


REQUIRED_FIELDS = {
    "symbol",
    "trade_date",
    "instrument_type",
    "open",
    "high",
    "low",
    "close",
    "volume",
}


def validate_provider_mixed_universe_sample(
    replay_input: RealProviderReplayInput,
) -> ProviderSampleValidationResult:
    """Validate local provider-like sample records for mixed stock/ETF replay."""

    blockers: list[str] = []
    flags: list[str] = []
    source_type_values = {item.value for item in ProviderSampleSourceType}
    if replay_input.sample_source_type not in source_type_values:
        blockers.append("sample_source_type_unknown")
    if _is_remote_uri(replay_input.sample_source_uri):
        blockers.append("sample_source_uri_remote")
    if not replay_input.records:
        blockers.append("records_missing")

    start = _parse_iso_date(replay_input.evaluation_start, blockers, "evaluation_start")
    end = _parse_iso_date(replay_input.evaluation_end, blockers, "evaluation_end")
    if start and end and start > end:
        blockers.append("evaluation_window_reversed")

    rows = tuple(dict(row) for row in replay_input.records)
    row_dates: list[date] = []
    seen: set[tuple[str, str]] = set()
    stock_symbols: set[str] = set()
    etf_symbols: set[str] = set()
    etf_categories: set[str] = set()

    for index, row in enumerate(rows):
        missing = sorted(REQUIRED_FIELDS - set(row))
        if missing:
            blockers.append(f"missing_required_fields:{index}:{','.join(missing)}")
            continue
        symbol = str(row.get("symbol", "")).strip()
        trade_date_value = str(row.get("trade_date", "")).strip()
        row_date = _parse_iso_date(trade_date_value, blockers, f"row_trade_date:{index}")
        if row_date is not None:
            row_dates.append(row_date)
            if end is not None and row_date > end:
                blockers.append(f"future_dated_row:{symbol}:{trade_date_value}")
        key = (symbol, trade_date_value)
        if key in seen:
            blockers.append(f"duplicate_symbol_date:{symbol}:{trade_date_value}")
        seen.add(key)
        _validate_ohlcv(row, blockers, index)
        instrument_type = str(row.get("instrument_type", "")).strip()
        if instrument_type == InstrumentType.STOCK.value:
            stock_symbols.add(symbol)
        elif instrument_type == InstrumentType.ETF.value:
            etf_symbols.add(symbol)
            category = str(row.get("etf_category", "")).strip()
            if not category:
                blockers.append(f"etf_category_missing:{symbol}")
            elif category not in {item.value for item in EtfCategory}:
                blockers.append(f"etf_category_unknown:{symbol}")
            else:
                etf_categories.add(category)
        else:
            blockers.append(f"instrument_type_unknown:{symbol}")

    if row_dates and row_dates != sorted(row_dates):
        blockers.append("trade_dates_unsorted")
    if len({item.isoformat() for item in row_dates}) < 3:
        blockers.append("insufficient_trading_days")
    if not stock_symbols:
        blockers.append("stock_sample_missing")
    if not etf_symbols:
        blockers.append("etf_sample_missing")

    if blockers:
        return ProviderSampleValidationResult(
            ok=False,
            quality_flags=tuple(sorted(set(flags))),
            blockers=tuple(sorted(set(blockers))),
            sample=None,
        )

    flags.extend(
        (
            "local_only_sample_source",
            "provider_like_ohlcv_present",
            "mixed_stock_etf_sample_present",
            "dates_sorted",
        )
    )
    sample = ProviderMixedUniverseSample(
        sample_source_type=replay_input.sample_source_type,
        sample_source_uri=replay_input.sample_source_uri,
        evaluation_start=replay_input.evaluation_start,
        evaluation_end=replay_input.evaluation_end,
        stock_symbols=tuple(sorted(stock_symbols)),
        etf_symbols=tuple(sorted(etf_symbols)),
        etf_categories=tuple(sorted(etf_categories)),
        records=tuple(sorted(rows, key=lambda row: (str(row["trade_date"]), str(row["symbol"])))),
        trading_days=tuple(sorted({str(row["trade_date"]) for row in rows})),
        evidence_refs=replay_input.evidence_refs,
    )
    return ProviderSampleValidationResult(
        ok=True,
        quality_flags=tuple(sorted(set(flags))),
        blockers=(),
        sample=sample,
    )


def _validate_ohlcv(row: dict[str, Any], blockers: list[str], index: int) -> None:
    for field in ("open", "high", "low", "close", "volume"):
        value = row.get(field)
        if value is None or value == "":
            blockers.append(f"missing_{field}:{index}")
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            blockers.append(f"non_numeric_{field}:{index}")
            continue
        if field == "volume" and numeric <= 0:
            blockers.append(f"missing_volume:{index}")
        elif field != "volume" and numeric <= 0:
            blockers.append(f"missing_{field}:{index}")


def _parse_iso_date(value: str, blockers: list[str], field_name: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        blockers.append(f"invalid_date:{field_name}")
        return None


def _is_remote_uri(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"}
