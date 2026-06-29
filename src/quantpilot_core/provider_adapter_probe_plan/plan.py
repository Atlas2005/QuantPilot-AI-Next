"""Validation helpers for R6 provider adapter probe plans."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from quantpilot_core.provider_adapter_probe_plan.contracts import (
    ProviderAdapterBoundary,
    ProviderAdapterCandidate,
    ProviderAdapterProbePlan,
    ProviderAdapterProbePlanAuditRecord,
    ProviderAdapterProbePlanResult,
    ProviderAdapterProbeRejectionReason,
    ProviderAdapterProbeStatus,
    ProviderAdjustmentPolicyReview,
    ProviderEndpointCategory,
    ProviderLicenseReview,
    ProviderSchemaRequirement,
    ProviderSymbolMappingReview,
    ProviderTimestampAuditReview,
)


MATURE_PROVIDER_CANDIDATES = frozenset({"AkShare", "Baostock", "Tushare"})
MOCK_PROVIDER_NAME = "mock"
OUTPUT_CLASSIFICATION = "adapter_probe_plan_only"
MAX_ROWS = 500
MAX_SYMBOLS = 5
MAX_LOOKBACK_DAYS = 30


def load_provider_adapter_probe_plan(path: str | Path) -> ProviderAdapterProbePlan:
    """Load a static local provider adapter probe plan."""

    with Path(path).open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    if not isinstance(raw, dict):
        raise ValueError("Provider adapter probe plan must be a JSON object.")
    return provider_adapter_probe_plan_from_mapping(raw)


def provider_adapter_probe_plan_from_mapping(
    value: dict[str, Any],
) -> ProviderAdapterProbePlan:
    """Convert a mapping into a typed adapter probe plan."""

    provider = _mapping_or_empty(value.get("provider", {}))
    schema = _mapping_or_empty(value.get("schema_requirement", {}))
    license_review = _mapping_or_empty(value.get("license_review", {}))
    adjustment = _mapping_or_empty(value.get("adjustment_policy_review", {}))
    symbol_mapping = _mapping_or_empty(value.get("symbol_mapping_review", {}))
    timestamp = _mapping_or_empty(value.get("timestamp_audit_review", {}))
    boundary = _mapping_or_empty(value.get("adapter_boundary", {}))
    return ProviderAdapterProbePlan(
        provider=ProviderAdapterCandidate(
            provider_candidate_name=str(provider.get("provider_candidate_name", "")),
            provider_project_name=str(provider.get("provider_project_name", "")),
            project_url_or_docs=str(provider.get("project_url_or_docs", "")),
            explicitly_mock=bool(provider.get("explicitly_mock", False)),
        ),
        endpoint_category=ProviderEndpointCategory(
            value.get("endpoint_category", ProviderEndpointCategory.UNKNOWN.value)
        ),
        schema_requirement=ProviderSchemaRequirement(
            expected_fields=tuple(str(field) for field in schema.get("expected_fields", ())),
            schema_notes=str(schema.get("schema_notes", "")),
        ),
        symbol_universe_scope=tuple(
            str(symbol) for symbol in value.get("symbol_universe_scope", ())
        ),
        start_date=str(value.get("start_date", "")),
        end_date=str(value.get("end_date", "")),
        max_rows=int(value.get("max_rows", 0)),
        max_symbols=int(value.get("max_symbols", 0)),
        max_lookback_days=int(value.get("max_lookback_days", 0)),
        adjustment_policy_review=ProviderAdjustmentPolicyReview(
            adjustment_policy=str(adjustment.get("adjustment_policy", "")),
            review_notes=str(adjustment.get("review_notes", "")),
            explicit=bool(adjustment.get("explicit", False)),
        ),
        symbol_mapping_review=ProviderSymbolMappingReview(
            symbol_format=str(symbol_mapping.get("symbol_format", "")),
            mapping_notes=str(symbol_mapping.get("mapping_notes", "")),
            explicit=bool(symbol_mapping.get("explicit", False)),
        ),
        timestamp_audit_review=ProviderTimestampAuditReview(
            timestamp_source=str(timestamp.get("timestamp_source", "")),
            audit_notes=str(timestamp.get("audit_notes", "")),
            explicit=bool(timestamp.get("explicit", False)),
        ),
        license_review=ProviderLicenseReview(
            review_status=str(license_review.get("review_status", "")),
            commercial_use_notes=str(license_review.get("commercial_use_notes", "")),
            approved_for_production=bool(
                license_review.get("approved_for_production", False)
            ),
        ),
        adapter_boundary=ProviderAdapterBoundary(
            boundary_statement=str(boundary.get("boundary_statement", "")),
            external_project_remains_candidate=bool(
                boundary.get("external_project_remains_candidate", False)
            ),
            no_self_built_provider=bool(boundary.get("no_self_built_provider", False)),
        ),
        no_real_data_fetch=bool(value.get("no_real_data_fetch", False)),
        no_provider_api_call=bool(value.get("no_provider_api_call", False)),
        no_broker=bool(value.get("no_broker", False)),
        no_live_trading=bool(value.get("no_live_trading", False)),
        no_order_execution=bool(value.get("no_order_execution", False)),
        output_classification=str(value.get("output_classification", "")),
        compatible_with_r4_gate=bool(value.get("compatible_with_r4_gate", False)),
        compatible_with_r3_bridge=bool(value.get("compatible_with_r3_bridge", False)),
        compatible_with_r2_sandbox_fixture=bool(
            value.get("compatible_with_r2_sandbox_fixture", False)
        ),
        plan_notes=str(value.get("plan_notes", "")),
    )


def _mapping_or_empty(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def validate_provider_adapter_probe_plan(
    plan: ProviderAdapterProbePlan,
) -> ProviderAdapterProbePlanResult:
    """Validate an R6 adapter probe plan without running any provider code."""

    reasons: list[ProviderAdapterProbeRejectionReason] = []
    messages: list[str] = []

    _validate_provider(plan, reasons, messages)
    _validate_required_reviews(plan, reasons, messages)
    _validate_scope(plan, reasons, messages)
    _validate_safety(plan, reasons, messages)

    status = (
        ProviderAdapterProbeStatus.ACCEPTED
        if not reasons
        else ProviderAdapterProbeStatus.REJECTED
    )
    audit = ProviderAdapterProbePlanAuditRecord(
        provider_candidate_name=plan.provider.provider_candidate_name,
        status=status,
        rejection_reasons=tuple(reasons),
        no_real_data_fetch=plan.no_real_data_fetch,
        no_provider_api_call=plan.no_provider_api_call,
        no_broker=plan.no_broker,
        no_live_trading=plan.no_live_trading,
        no_order_execution=plan.no_order_execution,
        no_production_data_asset=plan.output_classification == OUTPUT_CLASSIFICATION,
        notes=plan.plan_notes,
    )
    return ProviderAdapterProbePlanResult(
        status=status,
        accepted_for_r4_gate_submission=status is ProviderAdapterProbeStatus.ACCEPTED,
        rejection_reasons=tuple(reasons),
        messages=tuple(messages) if messages else ("Provider adapter probe plan accepted.",),
        audit_record=audit,
    )


def _validate_provider(
    plan: ProviderAdapterProbePlan,
    reasons: list[ProviderAdapterProbeRejectionReason],
    messages: list[str],
) -> None:
    name = plan.provider.provider_candidate_name
    if name == MOCK_PROVIDER_NAME and plan.provider.explicitly_mock:
        return
    if name not in MATURE_PROVIDER_CANDIDATES:
        _append(
            reasons,
            messages,
            ProviderAdapterProbeRejectionReason.UNKNOWN_PROVIDER,
            "Provider must be AkShare, Baostock, Tushare, or explicitly marked mock.",
        )


def _validate_required_reviews(
    plan: ProviderAdapterProbePlan,
    reasons: list[ProviderAdapterProbeRejectionReason],
    messages: list[str],
) -> None:
    if (
        not plan.license_review.review_status.strip()
        or plan.license_review.approved_for_production
    ):
        _append(
            reasons,
            messages,
            ProviderAdapterProbeRejectionReason.LICENSE_REVIEW_MISSING,
            "License review must exist and must not approve production use in R6.",
        )
    if plan.endpoint_category is ProviderEndpointCategory.UNKNOWN:
        _append(
            reasons,
            messages,
            ProviderAdapterProbeRejectionReason.ENDPOINT_MISSING,
            "Endpoint/category must be explicit.",
        )
    if not plan.schema_requirement.expected_fields or not plan.schema_requirement.schema_notes.strip():
        _append(
            reasons,
            messages,
            ProviderAdapterProbeRejectionReason.SCHEMA_REQUIREMENT_MISSING,
            "Schema requirements must be explicit.",
        )
    if (
        not plan.adjustment_policy_review.explicit
        or not plan.adjustment_policy_review.adjustment_policy.strip()
    ):
        _append(
            reasons,
            messages,
            ProviderAdapterProbeRejectionReason.ADJUSTMENT_POLICY_REVIEW_MISSING,
            "Adjustment policy review must be explicit.",
        )
    if (
        not plan.symbol_mapping_review.explicit
        or not plan.symbol_mapping_review.symbol_format.strip()
    ):
        _append(
            reasons,
            messages,
            ProviderAdapterProbeRejectionReason.SYMBOL_MAPPING_REVIEW_MISSING,
            "Symbol mapping review must be explicit.",
        )
    if (
        not plan.timestamp_audit_review.explicit
        or not plan.timestamp_audit_review.timestamp_source.strip()
    ):
        _append(
            reasons,
            messages,
            ProviderAdapterProbeRejectionReason.TIMESTAMP_AUDIT_REVIEW_MISSING,
            "Timestamp audit review must be explicit.",
        )
    if (
        not plan.adapter_boundary.boundary_statement.strip()
        or not plan.adapter_boundary.external_project_remains_candidate
        or not plan.adapter_boundary.no_self_built_provider
    ):
        _append(
            reasons,
            messages,
            ProviderAdapterProbeRejectionReason.ADAPTER_BOUNDARY_MISSING,
            "Adapter boundary must keep provider as external candidate.",
        )


def _validate_scope(
    plan: ProviderAdapterProbePlan,
    reasons: list[ProviderAdapterProbeRejectionReason],
    messages: list[str],
) -> None:
    too_broad = False
    if not plan.symbol_universe_scope or len(plan.symbol_universe_scope) > MAX_SYMBOLS:
        too_broad = True
    if plan.max_rows <= 0 or plan.max_rows > MAX_ROWS:
        too_broad = True
    if plan.max_symbols <= 0 or plan.max_symbols > MAX_SYMBOLS:
        too_broad = True
    if plan.max_lookback_days <= 0 or plan.max_lookback_days > MAX_LOOKBACK_DAYS:
        too_broad = True
    try:
        start = date.fromisoformat(plan.start_date)
        end = date.fromisoformat(plan.end_date)
    except ValueError:
        too_broad = True
    else:
        if end < start or (end - start).days + 1 > MAX_LOOKBACK_DAYS:
            too_broad = True
    if too_broad:
        _append(
            reasons,
            messages,
            ProviderAdapterProbeRejectionReason.SCOPE_TOO_BROAD,
            "Symbol/date/row scope is too broad for R6 planning.",
        )


def _validate_safety(
    plan: ProviderAdapterProbePlan,
    reasons: list[ProviderAdapterProbeRejectionReason],
    messages: list[str],
) -> None:
    if not plan.no_real_data_fetch:
        _append(
            reasons,
            messages,
            ProviderAdapterProbeRejectionReason.REAL_DATA_FETCH_FORBIDDEN,
            "R6 must not allow real data fetch.",
        )
    if not plan.no_provider_api_call:
        _append(
            reasons,
            messages,
            ProviderAdapterProbeRejectionReason.PROVIDER_CALL_FORBIDDEN,
            "R6 must not allow provider API calls.",
        )
    if not plan.no_broker or not plan.no_live_trading or not plan.no_order_execution:
        _append(
            reasons,
            messages,
            ProviderAdapterProbeRejectionReason.SAFETY_FLAG_VIOLATION,
            "Broker, live trading, and order execution must remain disabled.",
        )
    if plan.output_classification != OUTPUT_CLASSIFICATION:
        _append(
            reasons,
            messages,
            ProviderAdapterProbeRejectionReason.OUTPUT_CLASSIFICATION_INVALID,
            "Output classification must be adapter_probe_plan_only.",
        )
    if (
        not plan.compatible_with_r4_gate
        or not plan.compatible_with_r3_bridge
        or not plan.compatible_with_r2_sandbox_fixture
    ):
        _append(
            reasons,
            messages,
            ProviderAdapterProbeRejectionReason.COMPATIBILITY_MISSING,
            "R4 gate, R3 bridge, and R2 sandbox fixture compatibility are required.",
        )


def _append(
    reasons: list[ProviderAdapterProbeRejectionReason],
    messages: list[str],
    reason: ProviderAdapterProbeRejectionReason,
    message: str,
) -> None:
    if reason not in reasons:
        reasons.append(reason)
    messages.append(message)
