"""Point-in-time validation for future feature-store adapter work."""

from __future__ import annotations

from datetime import date
import math
from typing import Iterable

from quantpilot_core.pit_feature_store_preflight.contracts import (
    PITFeatureBuildMode,
    PITFeatureRecord,
    PITFeatureStoreManifest,
    PITFeatureStorePreflightResult,
    PITFeatureStoreStatus,
    PITFeatureValueKind,
)


def parse_iso_date(value: str) -> date:
    """Parse an ISO date for deterministic PIT checks."""

    if len(value) != 10 or value[4] != "-" or value[7] != "-":
        raise ValueError(f"invalid ISO date: {value}")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid ISO date: {value}") from exc


def validate_pit_feature_manifest(
    manifest: PITFeatureStoreManifest,
) -> tuple[str, ...]:
    """Validate feature-set metadata before records can feed the sandbox path."""

    reasons: list[str] = []
    if not manifest.feature_set_id.strip():
        reasons.append("feature_set_id_missing")
    if not manifest.version.strip():
        reasons.append("version_missing")
    if not manifest.source_ref.strip():
        reasons.append("source_ref_missing")
    if manifest.build_mode is not PITFeatureBuildMode.OFFLINE_PREFLIGHT:
        reasons.append("build_mode_must_be_offline_preflight")
    if manifest.sandbox_only is not True:
        reasons.append("sandbox_only_required")
    if manifest.no_live_trading is not True:
        reasons.append("no_live_trading_required")
    if manifest.no_order_execution is not True:
        reasons.append("no_order_execution_required")
    if manifest.point_in_time is not True:
        reasons.append("point_in_time_required")
    return tuple(reasons)


def validate_pit_feature_record(record: PITFeatureRecord) -> tuple[str, ...]:
    """Validate a single feature record for PIT safety and usable numeric shape."""

    reasons: list[str] = []
    if not record.symbol.strip():
        reasons.append("symbol_missing")
    if not record.feature_name.strip():
        reasons.append("feature_name_missing")
    if record.value_kind is not PITFeatureValueKind.NUMERIC:
        reasons.append("value_kind_must_be_numeric")
    if not _is_finite_number(record.feature_value):
        reasons.append("feature_value_not_finite_number")
    if not _has_non_empty_evidence(record.evidence_refs):
        reasons.append("evidence_refs_missing")

    dates = _parse_record_dates(record)
    reasons.extend(dates.reasons)
    if dates.observation_date and dates.available_date and dates.as_of_date:
        if dates.observation_date > dates.as_of_date:
            reasons.append("observation_after_as_of")
        if dates.available_date < dates.observation_date:
            reasons.append("available_before_observation")
        if dates.available_date > dates.as_of_date:
            reasons.append("available_after_as_of")

    return tuple(reasons)


def run_pit_feature_store_preflight(
    manifest: PITFeatureStoreManifest,
    records: Iterable[PITFeatureRecord],
) -> PITFeatureStorePreflightResult:
    """Run the R18 PIT preflight without storage, provider, or model dependencies."""

    feature_records = tuple(records)
    reasons: list[str] = list(validate_pit_feature_manifest(manifest))
    warnings: list[str] = []
    rejected_record_count = 0

    if not feature_records:
        reasons.append("feature_records_missing")

    seen_keys: set[tuple[str, str, str]] = set()
    for index, record in enumerate(feature_records):
        record_reasons = validate_pit_feature_record(record)
        if record_reasons:
            rejected_record_count += 1
            reasons.extend(f"record[{index}]:{reason}" for reason in record_reasons)
        key = (record.symbol.strip(), record.feature_name.strip(), record.as_of_date)
        if key in seen_keys:
            warnings.append(f"duplicate_feature_key:{key[0]}:{key[1]}:{key[2]}")
        else:
            seen_keys.add(key)

    accepted_record_count = len(feature_records) - rejected_record_count
    ok = not reasons
    return PITFeatureStorePreflightResult(
        status=PITFeatureStoreStatus.READY if ok else PITFeatureStoreStatus.REJECTED,
        ok=ok,
        feature_set_id=manifest.feature_set_id,
        accepted_record_count=accepted_record_count,
        rejected_record_count=rejected_record_count,
        can_feed_sandbox=ok,
        reasons=tuple(reasons),
        warnings=tuple(warnings),
        suggested_next_action=(
            "Feed PIT-safe features into sandbox-only research preflight."
            if ok
            else "Fix manifest and PIT record reasons before feature-store adapter work."
        ),
    )


def _is_finite_number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def _has_non_empty_evidence(evidence_refs: tuple[str, ...]) -> bool:
    return any(ref.strip() for ref in evidence_refs)


def _parse_record_dates(record: PITFeatureRecord) -> "_ParsedRecordDates":
    reasons: list[str] = []
    observation_date = _parse_date_field(
        record.observation_date,
        "observation_date_invalid",
        reasons,
    )
    available_date = _parse_date_field(
        record.available_date,
        "available_date_invalid",
        reasons,
    )
    as_of_date = _parse_date_field(record.as_of_date, "as_of_date_invalid", reasons)
    return _ParsedRecordDates(
        observation_date=observation_date,
        available_date=available_date,
        as_of_date=as_of_date,
        reasons=tuple(reasons),
    )


def _parse_date_field(
    value: str,
    reason: str,
    reasons: list[str],
) -> date | None:
    try:
        return parse_iso_date(value)
    except ValueError:
        reasons.append(reason)
        return None


class _ParsedRecordDates:
    def __init__(
        self,
        observation_date: date | None,
        available_date: date | None,
        as_of_date: date | None,
        reasons: tuple[str, ...],
    ) -> None:
        self.observation_date = observation_date
        self.available_date = available_date
        self.as_of_date = as_of_date
        self.reasons = reasons
