"""Validation helpers for R7 small-sample data gate manifests."""

from __future__ import annotations

import json
from datetime import date
from pathlib import PurePosixPath
from pathlib import Path
from typing import Any

from quantpilot_core.small_sample_data_gate.contracts import (
    SmallSampleAdjustmentPolicyAudit,
    SmallSampleDataAuditRecord,
    SmallSampleDataClassification,
    SmallSampleDataGateDecision,
    SmallSampleDataGateRejectionReason,
    SmallSampleDataGateRequest,
    SmallSampleDataGateStatus,
    SmallSampleDataManifest,
    SmallSampleDataScope,
    SmallSampleDataSourceReview,
    SmallSampleLicenseReview,
    SmallSampleSchemaReview,
    SmallSampleStoragePolicy,
    SmallSampleSymbolMappingAudit,
    SmallSampleTimestampAudit,
)


OUTPUT_CLASSIFICATION = SmallSampleDataClassification.SMALL_SAMPLE_RESEARCH_ONLY
MAX_SYMBOLS = 5
MAX_ROWS = 500
MAX_LOOKBACK_DAYS = 30


def load_small_sample_data_gate_request(path: str | Path) -> SmallSampleDataGateRequest:
    """Load a static local small-sample data gate request manifest."""

    with Path(path).open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    if not isinstance(raw, dict):
        raise ValueError("Small-sample data gate request must be a JSON object.")
    return small_sample_data_gate_request_from_mapping(raw)


def small_sample_data_gate_request_from_mapping(
    value: dict[str, Any],
) -> SmallSampleDataGateRequest:
    """Convert mapping data into a typed R7 gate request."""

    manifest = _mapping_or_empty(value.get("manifest", value))
    source = _mapping_or_empty(manifest.get("source_review", {}))
    scope = _mapping_or_empty(manifest.get("scope", {}))
    license_review = _mapping_or_empty(manifest.get("license_review", {}))
    schema = _mapping_or_empty(manifest.get("schema_review", {}))
    timestamp = _mapping_or_empty(manifest.get("timestamp_audit", {}))
    adjustment = _mapping_or_empty(manifest.get("adjustment_policy_audit", {}))
    symbol_mapping = _mapping_or_empty(manifest.get("symbol_mapping_audit", {}))
    storage = _mapping_or_empty(manifest.get("storage_policy", {}))
    return SmallSampleDataGateRequest(
        manifest=SmallSampleDataManifest(
            dataset_id=str(manifest.get("dataset_id", "")),
            source_review=SmallSampleDataSourceReview(
                provider_candidate_name=str(source.get("provider_candidate_name", "")),
                source_project=str(source.get("source_project", "")),
                documentation_marker=str(source.get("documentation_marker", "")),
                provider_adapter_probe_plan_reference=str(
                    source.get("provider_adapter_probe_plan_reference", "")
                ),
                approved_r4_gate_decision_reference=str(
                    source.get("approved_r4_gate_decision_reference", "")
                ),
                r3_bridge_compatible=bool(source.get("r3_bridge_compatible", False)),
                r2_sandbox_fixture_compatible=bool(
                    source.get("r2_sandbox_fixture_compatible", False)
                ),
            ),
            scope=SmallSampleDataScope(
                symbol_list=tuple(str(symbol) for symbol in scope.get("symbol_list", ())),
                start_date=str(scope.get("start_date", "")),
                end_date=str(scope.get("end_date", "")),
                max_symbols=int(scope.get("max_symbols", 0)),
                max_rows=int(scope.get("max_rows", 0)),
                max_lookback_days=int(scope.get("max_lookback_days", 0)),
                declared_row_count=int(scope.get("declared_row_count", 0)),
            ),
            license_review=SmallSampleLicenseReview(
                review_status=str(license_review.get("review_status", "")),
                commercial_use_notes=str(license_review.get("commercial_use_notes", "")),
                approved_for_production=bool(
                    license_review.get("approved_for_production", False)
                ),
            ),
            schema_review=SmallSampleSchemaReview(
                expected_schema_fields=tuple(
                    str(field) for field in schema.get("expected_schema_fields", ())
                ),
                schema_notes=str(schema.get("schema_notes", "")),
                reviewed=bool(schema.get("reviewed", False)),
            ),
            timestamp_audit=SmallSampleTimestampAudit(
                audit_status=str(timestamp.get("audit_status", "")),
                timestamp_source=str(timestamp.get("timestamp_source", "")),
                reviewed=bool(timestamp.get("reviewed", False)),
            ),
            adjustment_policy_audit=SmallSampleAdjustmentPolicyAudit(
                adjustment_policy=str(adjustment.get("adjustment_policy", "")),
                audit_notes=str(adjustment.get("audit_notes", "")),
                reviewed=bool(adjustment.get("reviewed", False)),
            ),
            symbol_mapping_audit=SmallSampleSymbolMappingAudit(
                symbol_format=str(symbol_mapping.get("symbol_format", "")),
                mapping_confidence=str(symbol_mapping.get("mapping_confidence", "")),
                audit_notes=str(symbol_mapping.get("audit_notes", "")),
                reviewed=bool(symbol_mapping.get("reviewed", False)),
            ),
            storage_policy=SmallSampleStoragePolicy(
                storage_root=str(storage.get("storage_root", "")),
                allowed_storage_path=str(storage.get("allowed_storage_path", "")),
                version_marker=str(storage.get("version_marker", "")),
            ),
            data_classification=_data_classification_from(
                manifest.get("data_classification", "")
            ),
            no_production_data=bool(manifest.get("no_production_data", False)),
            no_broker=bool(manifest.get("no_broker", False)),
            no_live_trading=bool(manifest.get("no_live_trading", False)),
            no_order_execution=bool(manifest.get("no_order_execution", False)),
            audit_notes=str(manifest.get("audit_notes", "")),
        ),
        request_notes=str(value.get("request_notes", "")),
    )


def validate_small_sample_data_gate_request(
    request: SmallSampleDataGateRequest,
) -> SmallSampleDataGateDecision:
    """Validate an R7 manifest without reading data files or calling providers."""

    manifest = request.manifest
    reasons: list[SmallSampleDataGateRejectionReason] = []
    messages: list[str] = []

    _validate_classification(manifest, reasons, messages)
    _validate_source_review(manifest, reasons, messages)
    _validate_scope(manifest, reasons, messages)
    _validate_reviews(manifest, reasons, messages)
    _validate_storage(manifest, reasons, messages)
    _validate_safety(manifest, reasons, messages)

    status = (
        SmallSampleDataGateStatus.ALLOWED
        if not reasons
        else SmallSampleDataGateStatus.REJECTED
    )
    audit = SmallSampleDataAuditRecord(
        dataset_id=manifest.dataset_id,
        provider_candidate_name=manifest.source_review.provider_candidate_name,
        status=status,
        rejection_reasons=tuple(reasons),
        data_classification=manifest.data_classification,
        no_production_data=manifest.no_production_data,
        no_broker=manifest.no_broker,
        no_live_trading=manifest.no_live_trading,
        no_order_execution=manifest.no_order_execution,
        no_data_fetch=True,
        no_provider_api_call=True,
        no_production_data_asset_written=True,
        notes=manifest.audit_notes,
    )
    return SmallSampleDataGateDecision(
        status=status,
        allowed_for_sandbox_replay_preparation=(
            status is SmallSampleDataGateStatus.ALLOWED
        ),
        rejection_reasons=tuple(reasons),
        messages=tuple(messages) if messages else ("Small-sample manifest allowed.",),
        audit_record=audit,
    )


def _mapping_or_empty(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _data_classification_from(value: Any) -> SmallSampleDataClassification:
    try:
        return SmallSampleDataClassification(str(value))
    except ValueError:
        return SmallSampleDataClassification.UNKNOWN


def _validate_classification(
    manifest: SmallSampleDataManifest,
    reasons: list[SmallSampleDataGateRejectionReason],
    messages: list[str],
) -> None:
    if manifest.data_classification is not OUTPUT_CLASSIFICATION:
        _append(
            reasons,
            messages,
            SmallSampleDataGateRejectionReason.CLASSIFICATION_INVALID,
            "Dataset classification must be small_sample_research_only.",
        )


def _validate_source_review(
    manifest: SmallSampleDataManifest,
    reasons: list[SmallSampleDataGateRejectionReason],
    messages: list[str],
) -> None:
    source = manifest.source_review
    if not source.provider_candidate_name.strip():
        _append(
            reasons,
            messages,
            SmallSampleDataGateRejectionReason.PROVIDER_CANDIDATE_MISSING,
            "Provider candidate name is required.",
        )
    if not source.provider_adapter_probe_plan_reference.strip():
        _append(
            reasons,
            messages,
            SmallSampleDataGateRejectionReason.PROVIDER_ADAPTER_PROBE_PLAN_REFERENCE_MISSING,
            "R6 provider adapter probe plan reference is required.",
        )
    if not source.approved_r4_gate_decision_reference.strip():
        _append(
            reasons,
            messages,
            SmallSampleDataGateRejectionReason.R4_GATE_DECISION_REFERENCE_MISSING,
            "Approved R4 gate decision reference is required.",
        )
    if not source.r3_bridge_compatible:
        _append(
            reasons,
            messages,
            SmallSampleDataGateRejectionReason.R3_BRIDGE_COMPATIBILITY_MISSING,
            "R3 bridge compatibility marker is required.",
        )
    if not source.r2_sandbox_fixture_compatible:
        _append(
            reasons,
            messages,
            SmallSampleDataGateRejectionReason.R2_SANDBOX_FIXTURE_COMPATIBILITY_MISSING,
            "R2 sandbox fixture compatibility marker is required.",
        )


def _validate_scope(
    manifest: SmallSampleDataManifest,
    reasons: list[SmallSampleDataGateRejectionReason],
    messages: list[str],
) -> None:
    scope = manifest.scope
    too_broad = False
    if not scope.symbol_list or len(scope.symbol_list) > scope.max_symbols:
        too_broad = True
    if scope.max_symbols <= 0 or scope.max_symbols > MAX_SYMBOLS:
        too_broad = True
    if scope.max_rows <= 0 or scope.max_rows > MAX_ROWS:
        too_broad = True
    if scope.declared_row_count <= 0 or scope.declared_row_count > scope.max_rows:
        too_broad = True
    if scope.max_lookback_days <= 0 or scope.max_lookback_days > MAX_LOOKBACK_DAYS:
        too_broad = True
    try:
        start = date.fromisoformat(scope.start_date)
        end = date.fromisoformat(scope.end_date)
    except ValueError:
        too_broad = True
    else:
        if end < start or (end - start).days + 1 > scope.max_lookback_days:
            too_broad = True
    if too_broad:
        _append(
            reasons,
            messages,
            SmallSampleDataGateRejectionReason.SCOPE_TOO_BROAD,
            "Symbol/date/row scope is missing or too broad.",
        )


def _validate_reviews(
    manifest: SmallSampleDataManifest,
    reasons: list[SmallSampleDataGateRejectionReason],
    messages: list[str],
) -> None:
    if (
        not manifest.schema_review.reviewed
        or not manifest.schema_review.expected_schema_fields
        or not manifest.schema_review.schema_notes.strip()
    ):
        _append(
            reasons,
            messages,
            SmallSampleDataGateRejectionReason.SCHEMA_REVIEW_MISSING,
            "Schema review and expected fields are required.",
        )
    if (
        not manifest.license_review.review_status.strip()
        or manifest.license_review.approved_for_production
    ):
        _append(
            reasons,
            messages,
            SmallSampleDataGateRejectionReason.LICENSE_REVIEW_MISSING,
            "License review is required and must not approve production use.",
        )
    if (
        not manifest.adjustment_policy_audit.reviewed
        or not manifest.adjustment_policy_audit.adjustment_policy.strip()
    ):
        _append(
            reasons,
            messages,
            SmallSampleDataGateRejectionReason.ADJUSTMENT_POLICY_AUDIT_MISSING,
            "Adjustment policy audit is required.",
        )
    if (
        not manifest.symbol_mapping_audit.reviewed
        or not manifest.symbol_mapping_audit.symbol_format.strip()
        or not manifest.symbol_mapping_audit.mapping_confidence.strip()
    ):
        _append(
            reasons,
            messages,
            SmallSampleDataGateRejectionReason.SYMBOL_MAPPING_AUDIT_MISSING,
            "Symbol mapping audit is required.",
        )
    if (
        not manifest.timestamp_audit.reviewed
        or not manifest.timestamp_audit.audit_status.strip()
        or not manifest.timestamp_audit.timestamp_source.strip()
    ):
        _append(
            reasons,
            messages,
            SmallSampleDataGateRejectionReason.TIMESTAMP_AUDIT_MISSING,
            "Timestamp audit is required.",
        )


def _validate_storage(
    manifest: SmallSampleDataManifest,
    reasons: list[SmallSampleDataGateRejectionReason],
    messages: list[str],
) -> None:
    storage = manifest.storage_policy
    if not _is_safe_storage_path(storage):
        _append(
            reasons,
            messages,
            SmallSampleDataGateRejectionReason.STORAGE_POLICY_INVALID,
            "Storage root, allowed path, and version marker must be safe metadata paths.",
        )


def _is_safe_storage_path(storage: SmallSampleStoragePolicy) -> bool:
    root = storage.storage_root.strip()
    allowed = storage.allowed_storage_path.strip()
    version = storage.version_marker.strip()
    if not root or not allowed or not version:
        return False
    if root.startswith("/") or allowed.startswith("/") or root.startswith("~"):
        return False
    if allowed.startswith("~") or "\\" in root or "\\" in allowed:
        return False
    root_path = PurePosixPath(root)
    allowed_path = PurePosixPath(allowed)
    if ".." in root_path.parts or ".." in allowed_path.parts:
        return False
    if allowed_path.parts[: len(root_path.parts)] != root_path.parts:
        return False
    return "production" not in allowed.lower()


def _validate_safety(
    manifest: SmallSampleDataManifest,
    reasons: list[SmallSampleDataGateRejectionReason],
    messages: list[str],
) -> None:
    if (
        not manifest.no_production_data
        or not manifest.no_broker
        or not manifest.no_live_trading
        or not manifest.no_order_execution
    ):
        _append(
            reasons,
            messages,
            SmallSampleDataGateRejectionReason.SAFETY_FLAG_VIOLATION,
            "No production data, broker, live trading, and order execution flags are required.",
        )


def _append(
    reasons: list[SmallSampleDataGateRejectionReason],
    messages: list[str],
    reason: SmallSampleDataGateRejectionReason,
    message: str,
) -> None:
    if reason not in reasons:
        reasons.append(reason)
    messages.append(message)
