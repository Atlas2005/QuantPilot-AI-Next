"""Validation helpers for P31 real data stability trial."""

from __future__ import annotations

import math
import re
from datetime import datetime

from quantpilot_core.real_data_stability_trial.contracts import (
    AshareSampleUniverse,
    ExpectedDataType,
    ProviderDataRow,
    ProviderTrialConfig,
    RealDataProviderName,
    RealDataTrialRiskFlag,
    RealDataTrialSeverity,
)


NUMERIC_SANITY_FIELDS = frozenset({"open", "high", "low", "close", "volume"})
SYMBOL_PATTERN = re.compile(r"^\d{6}(\.(SH|SZ|BJ))?$", re.IGNORECASE)


def validate_sample_universe(
    universe: AshareSampleUniverse,
) -> tuple[RealDataTrialRiskFlag, ...]:
    """Validate fixed A-share sample universe metadata."""

    flags: list[RealDataTrialRiskFlag] = []
    if not universe.universe_id.strip():
        flags.append(_critical("universe_id_missing", "Universe id must be non-empty."))
    if not universe.symbols:
        flags.append(_critical("universe_symbols_empty", "Universe symbols must not be empty."))
    if len(set(universe.symbols)) != len(universe.symbols):
        flags.append(_critical("universe_duplicate_symbols", "Universe symbols must be unique."))
    for index, symbol in enumerate(universe.symbols):
        if not SYMBOL_PATTERN.match(symbol):
            flags.append(_critical(f"universe_symbol_invalid:{index}", "Universe symbol must be A-share shaped."))
    if not _strict_iso_date(universe.start_date):
        flags.append(_critical("universe_start_date_invalid", "Universe start_date must be YYYY-MM-DD."))
    if not _strict_iso_date(universe.end_date):
        flags.append(_critical("universe_end_date_invalid", "Universe end_date must be YYYY-MM-DD."))
    if _strict_iso_date(universe.start_date) and _strict_iso_date(universe.end_date):
        if universe.start_date > universe.end_date:
            flags.append(_critical("universe_date_range_invalid", "Universe start_date must be <= end_date."))
    if universe.expected_trading_days is not None and universe.expected_trading_days <= 0:
        flags.append(_critical("universe_expected_trading_days_invalid", "Expected trading days must be positive when provided."))
    if not _has_evidence(universe.evidence_refs):
        flags.append(_critical("universe_evidence_missing", "Universe evidence_refs must be non-empty."))
    return tuple(flags)


def validate_provider_trial_config(
    config: ProviderTrialConfig,
) -> tuple[RealDataTrialRiskFlag, ...]:
    """Validate provider trial config without invoking providers."""

    flags: list[RealDataTrialRiskFlag] = []
    if config.provider_name not in {provider.value for provider in RealDataProviderName}:
        flags.append(_critical("provider_name_unsupported", "Provider name is not supported."))
    if config.data_type not in {data_type.value for data_type in ExpectedDataType}:
        flags.append(_critical("provider_data_type_unsupported", "Provider data_type is not supported."))
    if not config.required_fields:
        flags.append(_critical("provider_required_fields_empty", "Provider required_fields must not be empty."))
    if not _has_evidence(config.evidence_refs):
        flags.append(_critical("provider_config_evidence_missing", "Provider config evidence_refs must be non-empty."))
    if config.allow_network:
        flags.append(_warning("provider_network_manual_review", "Network-enabled provider trial requires manual review."))
    return tuple(flags)


def validate_provider_rows(
    rows: tuple[ProviderDataRow, ...],
    universe: AshareSampleUniverse,
    config: ProviderTrialConfig,
) -> tuple[RealDataTrialRiskFlag, ...]:
    """Validate provided provider rows against universe and config."""

    flags: list[RealDataTrialRiskFlag] = []
    allowed_symbols = set(universe.symbols)
    seen: set[tuple[str, str, str]] = set()
    for index, row in enumerate(rows):
        prefix = f"row[{index}]"
        if row.provider_name != config.provider_name:
            flags.append(_critical(f"{prefix}:provider_mismatch", "Row provider_name must match config."))
        if row.symbol not in allowed_symbols:
            flags.append(_critical(f"{prefix}:symbol_not_in_universe", "Row symbol must be in sample universe."))
        if not _strict_iso_date(row.trading_date):
            flags.append(_critical(f"{prefix}:trading_date_invalid", "Row trading_date must be YYYY-MM-DD."))
        elif _strict_iso_date(universe.start_date) and _strict_iso_date(universe.end_date):
            if row.trading_date < universe.start_date or row.trading_date > universe.end_date:
                flags.append(_critical(f"{prefix}:trading_date_out_of_range", "Row trading_date must be inside universe range."))
        missing_fields = tuple(field for field in config.required_fields if field not in row.fields)
        if missing_fields:
            flags.append(_critical(f"{prefix}:required_fields_missing", "Row is missing required fields."))
        flags.extend(_numeric_sanity_flags(row, prefix))
        if not _has_evidence(row.evidence_refs):
            flags.append(_critical(f"{prefix}:evidence_missing", "Row evidence_refs must be non-empty."))
        key = (row.provider_name, row.symbol, row.trading_date)
        if key in seen:
            flags.append(_critical(f"{prefix}:duplicate_provider_symbol_date", "Duplicate provider/symbol/date row is not allowed."))
        seen.add(key)
    return tuple(flags)


def _numeric_sanity_flags(
    row: ProviderDataRow,
    prefix: str,
) -> tuple[RealDataTrialRiskFlag, ...]:
    flags: list[RealDataTrialRiskFlag] = []
    for field in NUMERIC_SANITY_FIELDS:
        if field in row.fields and not _finite(row.fields[field]):
            flags.append(_critical(f"{prefix}:{field}_not_finite", f"{field} must be finite."))
    high = row.fields.get("high")
    low = row.fields.get("low")
    if _finite(high) and _finite(low) and float(high) < float(low):
        flags.append(_critical(f"{prefix}:high_lower_than_low", "high must be >= low."))
    for field in ("open", "close"):
        value = row.fields.get(field)
        if _finite(value) and _finite(high) and _finite(low):
            if float(value) > float(high) or float(value) < float(low):
                flags.append(_critical(f"{prefix}:{field}_outside_high_low", f"{field} must be within high/low."))
    volume = row.fields.get("volume")
    if _finite(volume) and float(volume) < 0:
        flags.append(_critical(f"{prefix}:volume_negative", "volume must be non-negative."))
    return tuple(flags)


def _strict_iso_date(value: str) -> bool:
    if len(value) != 10:
        return False
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return parsed.strftime("%Y-%m-%d") == value


def _finite(value: object) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def _has_evidence(evidence_refs: tuple[str, ...]) -> bool:
    return any(ref.strip() for ref in evidence_refs)


def _critical(code: str, message: str) -> RealDataTrialRiskFlag:
    return RealDataTrialRiskFlag(
        code=code,
        severity=RealDataTrialSeverity.CRITICAL.value,
        message=message,
    )


def _warning(code: str, message: str) -> RealDataTrialRiskFlag:
    return RealDataTrialRiskFlag(
        code=code,
        severity=RealDataTrialSeverity.MEDIUM.value,
        message=message,
    )
