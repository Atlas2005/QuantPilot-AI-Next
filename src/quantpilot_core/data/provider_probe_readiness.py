from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class ProviderProbeStatus(str, Enum):
    not_run = "not_run"
    success = "success"
    failed = "failed"
    skipped = "skipped"
    inconclusive = "inconclusive"


class ProviderReadinessDecision(str, Enum):
    not_approved = "not_approved"
    retry_later = "retry_later"
    candidate_for_manual_review = "candidate_for_manual_review"
    rejected = "rejected"


class ProviderProbeRisk(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    unknown = "unknown"


@dataclass(frozen=True)
class ProviderProbeSummary:
    provider_name: str
    status: ProviderProbeStatus
    row_count: int
    mapped_field_count: int
    missing_required_fields: list[str]
    output_path: str
    raw_data_committed: bool
    approved_for_adapter: bool
    approved_for_alpha_validation: bool
    decision: ProviderReadinessDecision
    warnings: list[str]
    notes: str


REQUIRED_SUMMARY_FIELDS = {
    "provider_name",
    "status",
    "row_count",
    "mapped_field_count",
    "missing_required_fields",
    "output_path",
    "raw_data_committed",
    "approved_for_adapter",
    "approved_for_alpha_validation",
    "decision",
    "warnings",
    "notes",
}


def load_provider_probe_summary(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Provider probe summary must be a JSON object.")
    return data


def validate_provider_probe_summary(summary: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = sorted(REQUIRED_SUMMARY_FIELDS - set(summary))
    for field in missing:
        errors.append(f"missing required field: {field}")

    provider_name = str(summary.get("provider_name", "")).strip()
    if not provider_name:
        errors.append("provider_name must be non-empty")

    try:
        status = ProviderProbeStatus(summary.get("status"))
    except ValueError:
        errors.append("invalid status")
        status = ProviderProbeStatus.not_run

    try:
        decision = ProviderReadinessDecision(summary.get("decision"))
    except ValueError:
        errors.append("invalid decision")
        decision = ProviderReadinessDecision.not_approved

    if summary.get("approved_for_adapter") is not False:
        errors.append("approved_for_adapter must be false")
    if summary.get("approved_for_alpha_validation") is not False:
        errors.append("approved_for_alpha_validation must be false")
    if summary.get("raw_data_committed") is not False:
        errors.append("raw_data_committed must be false")

    output_path = str(summary.get("output_path", "")).replace("\\", "/")
    if output_path and "local_artifacts/provider_probes/" not in output_path:
        errors.append("output_path must point under local_artifacts/provider_probes/ or be empty")

    warnings = summary.get("warnings", [])
    if not isinstance(warnings, list):
        errors.append("warnings must be a list")
        warnings = []

    missing_fields = summary.get("missing_required_fields", [])
    if not isinstance(missing_fields, list):
        errors.append("missing_required_fields must be a list")

    for integer_field in ("row_count", "mapped_field_count"):
        value = summary.get(integer_field)
        if not isinstance(value, int) or value < 0:
            errors.append(f"{integer_field} must be a non-negative integer")

    if (
        status in {ProviderProbeStatus.failed, ProviderProbeStatus.inconclusive}
        and decision == ProviderReadinessDecision.candidate_for_manual_review
        and not warnings
    ):
        errors.append("failed or inconclusive probes need warnings before manual-review candidacy")

    return errors


def summarize_provider_probe_summaries(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = {status.value: 0 for status in ProviderProbeStatus}
    approved_for_adapter_count = 0
    approved_for_alpha_validation_count = 0
    total_rows = 0

    for summary in summaries:
        status_value = str(summary.get("status", ProviderProbeStatus.not_run.value))
        if status_value in status_counts:
            status_counts[status_value] += 1
        total_rows += int(summary.get("row_count", 0) or 0)
        if summary.get("approved_for_adapter") is True:
            approved_for_adapter_count += 1
        if summary.get("approved_for_alpha_validation") is True:
            approved_for_alpha_validation_count += 1

    return {
        "summary_count": len(summaries),
        "status_counts": status_counts,
        "total_rows": total_rows,
        "approved_for_adapter_count": approved_for_adapter_count,
        "approved_for_alpha_validation_count": approved_for_alpha_validation_count,
        "any_data_source_approved": approved_for_adapter_count > 0,
    }
