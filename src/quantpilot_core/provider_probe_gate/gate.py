"""Decision helpers for the provider probe policy.

This module validates local probe manifests only. It does not call provider
APIs, fetch data, create provider adapters, write market data files, connect
brokers, enable live trading, or execute orders.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from quantpilot_core.provider_probe_gate.contracts import (
    ProviderProbeAllowedProvider,
    ProviderProbeAuditRecord,
    ProviderProbeEvidenceRequirement,
    ProviderProbeExecutionMode,
    ProviderProbeGateDecision,
    ProviderProbeGateRejectionReason,
    ProviderProbeGateRequest,
    ProviderProbeGateStatus,
    ProviderProbeSafetyPolicy,
    ProviderProbeScope,
)


def default_provider_probe_safety_policy() -> ProviderProbeSafetyPolicy:
    """Return the default provider probe manifest policy."""

    allowed_providers = (
        ProviderProbeAllowedProvider(
            provider_candidate_name="mock",
            provider_project_name="mock",
            allowed_endpoint_categories=("mock_daily_bar",),
            license_review_status="fixture_only",
            adapter_boundary="Mock provider stays local fixture/probe only.",
        ),
        ProviderProbeAllowedProvider(
            provider_candidate_name="AkShare",
            provider_project_name="AkShare",
            allowed_endpoint_categories=("a_share_daily_bar",),
            license_review_status="review_required_before_real_probe",
            adapter_boundary="AkShare remains an external adapter candidate.",
        ),
        ProviderProbeAllowedProvider(
            provider_candidate_name="Baostock",
            provider_project_name="Baostock",
            allowed_endpoint_categories=("a_share_daily_bar",),
            license_review_status="review_required_before_real_probe",
            adapter_boundary="Baostock remains an external adapter candidate.",
        ),
        ProviderProbeAllowedProvider(
            provider_candidate_name="Tushare",
            provider_project_name="Tushare",
            allowed_endpoint_categories=("a_share_daily_bar",),
            license_review_status="token_and_license_review_required",
            adapter_boundary="Tushare remains an external adapter candidate.",
        ),
    )
    return ProviderProbeSafetyPolicy(
        allowed_providers=allowed_providers,
        allowed_execution_modes=(
            ProviderProbeExecutionMode.MOCK_ONLY,
            ProviderProbeExecutionMode.DRY_RUN,
            ProviderProbeExecutionMode.CONTROLLED_PROBE,
        ),
        max_rows=500,
        max_symbols=5,
        max_lookback_days=30,
        allowed_storage_policy="local_artifacts_or_fixture_only",
        output_must_be_probe_fixture_only=True,
        no_broker_required=True,
        no_live_trading_required=True,
        no_order_execution_required=True,
    )


def load_provider_probe_gate_request(path: str | Path) -> ProviderProbeGateRequest:
    """Load a static local provider probe manifest fixture."""

    with Path(path).open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    if not isinstance(raw, dict):
        raise ValueError("Provider probe gate request must be a JSON object.")
    return provider_probe_gate_request_from_mapping(raw)


def provider_probe_gate_request_from_mapping(
    value: dict[str, Any],
) -> ProviderProbeGateRequest:
    """Convert a mapping into a typed provider probe policy request."""

    scope = value.get("scope", {})
    evidence = value.get("evidence", {})
    if not isinstance(scope, dict):
        scope = {}
    if not isinstance(evidence, dict):
        evidence = {}
    return ProviderProbeGateRequest(
        provider_candidate_name=str(value.get("provider_candidate_name", "")),
        execution_mode=ProviderProbeExecutionMode(
            value.get("execution_mode", ProviderProbeExecutionMode.MOCK_ONLY.value)
        ),
        scope=ProviderProbeScope(
            requested_symbols=tuple(str(item) for item in scope.get("requested_symbols", ())),
            requested_start_date=str(scope.get("requested_start_date", "")),
            requested_end_date=str(scope.get("requested_end_date", "")),
            max_rows=int(scope.get("max_rows", 0)),
            max_symbols=int(scope.get("max_symbols", 0)),
            max_lookback_days=int(scope.get("max_lookback_days", 0)),
            allowed_endpoint_category=str(scope.get("allowed_endpoint_category", "")),
        ),
        evidence=ProviderProbeEvidenceRequirement(
            license_review_status=str(evidence.get("license_review_status", "")),
            adapter_boundary_acknowledged=bool(
                evidence.get("adapter_boundary_acknowledged", False)
            ),
            timestamp_audit_required=bool(evidence.get("timestamp_audit_required", False)),
            latency_requirement_required=bool(
                evidence.get("latency_requirement_required", False)
            ),
            provider_failure_handling_required=bool(
                evidence.get("provider_failure_handling_required", False)
            ),
            sandbox_bridge_compatibility_required=bool(
                evidence.get("sandbox_bridge_compatibility_required", False)
            ),
        ),
        no_broker=bool(value.get("no_broker", False)),
        no_live_trading=bool(value.get("no_live_trading", False)),
        no_order_execution=bool(value.get("no_order_execution", False)),
        storage_policy=str(value.get("storage_policy", "")),
        output_as_probe_fixture_only=bool(value.get("output_as_probe_fixture_only", False)),
        attempts_production_data_approval=bool(
            value.get("attempts_production_data_approval", False)
        ),
        request_notes=str(value.get("request_notes", "")),
    )


def decide_provider_probe_gate(
    request: ProviderProbeGateRequest,
    policy: ProviderProbeSafetyPolicy | None = None,
) -> ProviderProbeGateDecision:
    """Return an advisory provider probe policy decision."""

    active_policy = policy or default_provider_probe_safety_policy()
    reasons, messages = validate_provider_probe_gate_request(request, active_policy)
    status = (
        ProviderProbeGateStatus.ALLOWED
        if not reasons
        else ProviderProbeGateStatus.REJECTED
    )
    audit_record = ProviderProbeAuditRecord(
        audit_id=f"provider_probe_gate:{request.provider_candidate_name or 'missing'}",
        provider_candidate_name=request.provider_candidate_name,
        execution_mode=request.execution_mode,
        status=status,
        rejection_reasons=tuple(reasons),
        message="; ".join(messages) if messages else "Provider probe manifest accepted.",
        no_external_api_call=True,
        no_data_fetch=True,
        no_broker=request.no_broker,
        no_live_trading=request.no_live_trading,
        no_order_execution=request.no_order_execution,
    )
    return ProviderProbeGateDecision(
        status=status,
        allowed_to_run_probe=status is ProviderProbeGateStatus.ALLOWED,
        allowed_for_sandbox_bridge_conversion=status is ProviderProbeGateStatus.ALLOWED,
        rejection_reasons=tuple(reasons),
        messages=tuple(messages) if messages else ("Provider probe manifest accepted.",),
        audit_record=audit_record,
    )


def validate_provider_probe_gate_request(
    request: ProviderProbeGateRequest,
    policy: ProviderProbeSafetyPolicy,
) -> tuple[list[ProviderProbeGateRejectionReason], list[str]]:
    """Return fatal rejection reasons and advisory messages for a probe request."""

    reasons: list[ProviderProbeGateRejectionReason] = []
    messages: list[str] = []

    provider = _find_allowed_provider(policy, request.provider_candidate_name)
    if not request.provider_candidate_name.strip():
        _append(
            reasons,
            messages,
            ProviderProbeGateRejectionReason.PROVIDER_NAME_MISSING,
            "Provider candidate name is required.",
        )
    elif provider is None:
        _append(
            reasons,
            messages,
            ProviderProbeGateRejectionReason.UNKNOWN_PROVIDER,
            "Provider candidate is not explicitly allowed by the gate policy.",
        )

    if request.execution_mode not in policy.allowed_execution_modes:
        _append(
            reasons,
            messages,
            ProviderProbeGateRejectionReason.EXECUTION_MODE_NOT_ALLOWED,
            "Execution mode is not allowed by the gate policy.",
        )
    if not request.evidence.license_review_status.strip():
        messages.append("Advisory: license review status is missing.")
    if not request.evidence.adapter_boundary_acknowledged:
        messages.append("Advisory: adapter boundary acknowledgement is missing.")
    if (
        not request.no_broker
        or not request.no_live_trading
        or not request.no_order_execution
    ):
        _append(
            reasons,
            messages,
            ProviderProbeGateRejectionReason.SAFETY_FLAG_VIOLATION,
            "Broker, live trading, and order execution must be explicitly disabled.",
        )
    if request.attempts_production_data_approval or not request.output_as_probe_fixture_only:
        _append(
            reasons,
            messages,
            ProviderProbeGateRejectionReason.PRODUCTION_DATA_APPROVAL_ATTEMPT,
            "Gate output must remain probe/fixture data and cannot approve production data.",
        )
    if _scope_too_broad(request.scope, policy):
        _append(
            reasons,
            messages,
            ProviderProbeGateRejectionReason.SCOPE_TOO_BROAD,
            "Requested symbol/date/row scope exceeds policy limits.",
        )
    if provider is not None and request.scope.allowed_endpoint_category not in provider.allowed_endpoint_categories:
        _append(
            reasons,
            messages,
            ProviderProbeGateRejectionReason.ENDPOINT_NOT_ALLOWED,
            "Requested endpoint/category is not allowed for this provider candidate.",
        )
    if request.storage_policy != policy.allowed_storage_policy:
        _append(
            reasons,
            messages,
            ProviderProbeGateRejectionReason.STORAGE_POLICY_MISSING,
            "Storage policy must keep outputs as local artifact or fixture-only data.",
        )
    if not request.evidence.timestamp_audit_required:
        messages.append("Advisory: timestamp audit requirement is missing.")
    if not request.evidence.latency_requirement_required:
        messages.append("Advisory: latency requirement is missing.")
    if not request.evidence.provider_failure_handling_required:
        messages.append("Advisory: provider failure handling requirement is missing.")
    if not request.evidence.sandbox_bridge_compatibility_required:
        messages.append("Advisory: sandbox bridge compatibility marker is missing.")
    return reasons, messages


def _scope_too_broad(
    scope: ProviderProbeScope,
    policy: ProviderProbeSafetyPolicy,
) -> bool:
    if not scope.requested_symbols:
        return True
    if len(scope.requested_symbols) > policy.max_symbols:
        return True
    if scope.max_symbols > policy.max_symbols or scope.max_rows > policy.max_rows:
        return True
    if scope.max_lookback_days > policy.max_lookback_days:
        return True
    if not scope.allowed_endpoint_category.strip():
        return True
    try:
        start = date.fromisoformat(scope.requested_start_date)
        end = date.fromisoformat(scope.requested_end_date)
    except ValueError:
        return True
    if end < start:
        return True
    return (end - start).days + 1 > policy.max_lookback_days


def _find_allowed_provider(
    policy: ProviderProbeSafetyPolicy,
    provider_candidate_name: str,
) -> ProviderProbeAllowedProvider | None:
    for provider in policy.allowed_providers:
        if provider.provider_candidate_name == provider_candidate_name:
            return provider
    return None


def _append(
    reasons: list[ProviderProbeGateRejectionReason],
    messages: list[str],
    reason: ProviderProbeGateRejectionReason,
    message: str,
) -> None:
    if reason not in reasons:
        reasons.append(reason)
    messages.append(message)
