"""Provider probe snapshot to sandbox fixture bridge.

This module performs local validation and transformation only. It does not
fetch market data, call provider APIs, implement a provider, connect brokers,
submit orders, or create live execution paths.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quantpilot_core.provider_sandbox_bridge.contracts import (
    ProviderDataQualitySignal,
    ProviderFailureSignal,
    ProviderLatencySignal,
    ProviderProbeSnapshot,
    ProviderProbeStatus,
    ProviderSandboxAdapterBoundary,
    ProviderSandboxBridgeRejectionReason,
    ProviderSandboxBridgeResult,
    SandboxFixtureInput,
)


ACCEPTABLE_PROBE_STATUSES = frozenset(
    {
        ProviderProbeStatus.MOCK_FIXTURE,
        ProviderProbeStatus.MANUAL_PROBE,
        ProviderProbeStatus.CONTROLLED_PROBE,
    }
)

FORBIDDEN_LIVE_LANGUAGE = (
    "broker",
    "live trading",
    "order execution",
    "submit order",
    "place order",
)


def load_provider_probe_snapshot(path: str | Path) -> ProviderProbeSnapshot:
    """Load a local static provider probe snapshot fixture."""

    with Path(path).open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    if not isinstance(raw, dict):
        raise ValueError("Provider probe snapshot must be a JSON object.")
    return provider_probe_snapshot_from_mapping(raw)


def provider_probe_snapshot_from_mapping(
    value: dict[str, Any],
) -> ProviderProbeSnapshot:
    """Convert a mapping into a typed snapshot contract."""

    boundary = value.get("adapter_boundary", {})
    if not isinstance(boundary, dict):
        boundary = {}
    return ProviderProbeSnapshot(
        provider_name=str(value.get("provider_name", "")),
        provider_project_name=str(value.get("provider_project_name", "")),
        probe_status=ProviderProbeStatus(value.get("probe_status", "unknown")),
        probe_timestamp=str(value.get("probe_timestamp", "")),
        symbol=str(value.get("symbol", "")),
        trading_date=str(value.get("trading_date", "")),
        open_price=_optional_float(value.get("open_price")),
        high_price=_optional_float(value.get("high_price")),
        low_price=_optional_float(value.get("low_price")),
        close_price=_optional_float(value.get("close_price")),
        volume=_optional_float(value.get("volume")),
        amount=_optional_float(value.get("amount")),
        adjustment_policy=str(value.get("adjustment_policy", "")),
        symbol_mapping_confidence=float(value.get("symbol_mapping_confidence", 0.0)),
        timestamp_audit_status=bool(value.get("timestamp_audit_status", False)),
        latency_signal=ProviderLatencySignal(value.get("latency_signal", "unknown")),
        provider_failure_signal=ProviderFailureSignal(
            value.get("provider_failure_signal", "unknown")
        ),
        data_quality_signal=ProviderDataQualitySignal(
            value.get("data_quality_signal", "unknown")
        ),
        adapter_boundary=ProviderSandboxAdapterBoundary(
            provider_project_name=str(boundary.get("provider_project_name", "")),
            adapter_role=str(boundary.get("adapter_role", "")),
            boundary_description=str(boundary.get("boundary_description", "")),
            external_project_reference=str(boundary.get("external_project_reference", "")),
        ),
        is_fixture_mock_or_probe=bool(value.get("is_fixture_mock_or_probe", False)),
        approved_production_data=bool(value.get("approved_production_data", False)),
        source_notes=str(value.get("source_notes", "")),
    )


def bridge_snapshot_to_fixture(
    snapshot: ProviderProbeSnapshot,
) -> ProviderSandboxBridgeResult:
    """Validate and transform a provider probe snapshot to sandbox fixture input."""

    reasons, messages = validate_provider_probe_snapshot(snapshot)
    boundary_text = _adapter_boundary_text(snapshot.adapter_boundary)
    if reasons:
        return ProviderSandboxBridgeResult(
            accepted=False,
            fixture_input=None,
            rejection_reasons=tuple(reasons),
            messages=tuple(messages),
            latency_signal=snapshot.latency_signal,
            provider_failure_signal=snapshot.provider_failure_signal,
            external_adapter_boundary=boundary_text,
        )

    fixture = SandboxFixtureInput(
        provider_name=snapshot.provider_name,
        provider_project_name=snapshot.provider_project_name,
        source_probe_status=snapshot.probe_status,
        source_probe_timestamp=snapshot.probe_timestamp,
        symbol=snapshot.symbol,
        trading_date=snapshot.trading_date,
        open_price=float(snapshot.open_price),
        high_price=float(snapshot.high_price),
        low_price=float(snapshot.low_price),
        close_price=float(snapshot.close_price),
        volume=float(snapshot.volume),
        amount=snapshot.amount,
        adjustment_policy=snapshot.adjustment_policy,
        symbol_mapping_confidence=snapshot.symbol_mapping_confidence,
        timestamp_audit_status=snapshot.timestamp_audit_status,
        latency_signal=snapshot.latency_signal,
        provider_failure_signal=snapshot.provider_failure_signal,
        data_quality_signal=snapshot.data_quality_signal,
        external_adapter_boundary=boundary_text,
        is_fixture_mock_or_probe=snapshot.is_fixture_mock_or_probe,
        approved_production_data=snapshot.approved_production_data,
        source_notes=snapshot.source_notes,
    )
    return ProviderSandboxBridgeResult(
        accepted=True,
        fixture_input=fixture,
        rejection_reasons=(),
        messages=("Snapshot accepted as local sandbox fixture input.",),
        latency_signal=snapshot.latency_signal,
        provider_failure_signal=snapshot.provider_failure_signal,
        external_adapter_boundary=boundary_text,
    )


def validate_provider_probe_snapshot(
    snapshot: ProviderProbeSnapshot,
) -> tuple[
    list[ProviderSandboxBridgeRejectionReason],
    list[str],
]:
    """Validate a snapshot for fixture conversion."""

    reasons: list[ProviderSandboxBridgeRejectionReason] = []
    messages: list[str] = []

    required_strings = {
        "provider_name": snapshot.provider_name,
        "provider_project_name": snapshot.provider_project_name,
        "probe_timestamp": snapshot.probe_timestamp,
        "symbol": snapshot.symbol,
        "trading_date": snapshot.trading_date,
        "adjustment_policy": snapshot.adjustment_policy,
    }
    for field, value in required_strings.items():
        if not value.strip():
            _append(
                reasons,
                messages,
                ProviderSandboxBridgeRejectionReason.REQUIRED_FIELD_MISSING,
                f"{field} is required.",
            )

    if not snapshot.timestamp_audit_status:
        _append(
            reasons,
            messages,
            ProviderSandboxBridgeRejectionReason.TIMESTAMP_AUDIT_MISSING,
            "Timestamp audit status must be true for sandbox fixture conversion.",
        )
    if (
        snapshot.approved_production_data
        or not snapshot.is_fixture_mock_or_probe
        or snapshot.probe_status not in ACCEPTABLE_PROBE_STATUSES
    ):
        _append(
            reasons,
            messages,
            ProviderSandboxBridgeRejectionReason.PRODUCTION_DATA_FORBIDDEN,
            "Snapshot must be explicitly fixture/mock/probe data, not approved production data.",
        )
    if not _adapter_boundary_text(snapshot.adapter_boundary):
        _append(
            reasons,
            messages,
            ProviderSandboxBridgeRejectionReason.ADAPTER_BOUNDARY_MISSING,
            "External provider adapter boundary must be documented.",
        )
    if snapshot.provider_failure_signal is not ProviderFailureSignal.NONE:
        _append(
            reasons,
            messages,
            ProviderSandboxBridgeRejectionReason.PROVIDER_FAILURE,
            "Provider failure signal is not acceptable for sandbox conversion.",
        )
    if snapshot.data_quality_signal in {
        ProviderDataQualitySignal.POOR,
        ProviderDataQualitySignal.UNKNOWN,
    }:
        _append(
            reasons,
            messages,
            ProviderSandboxBridgeRejectionReason.POOR_DATA_QUALITY,
            "Data quality signal must not be poor or unknown.",
        )
    if not _valid_ohlcv(snapshot):
        _append(
            reasons,
            messages,
            ProviderSandboxBridgeRejectionReason.INVALID_OHLCV,
            "OHLCV-like fields are missing or impossible.",
        )
    if _contains_forbidden_live_language(snapshot.source_notes):
        _append(
            reasons,
            messages,
            ProviderSandboxBridgeRejectionReason.REQUIRED_FIELD_MISSING,
            "Snapshot notes must not contain live trading, broker, or execution language.",
        )
    return reasons, messages


def _append(
    reasons: list[ProviderSandboxBridgeRejectionReason],
    messages: list[str],
    reason: ProviderSandboxBridgeRejectionReason,
    message: str,
) -> None:
    if reason not in reasons:
        reasons.append(reason)
    messages.append(message)


def _valid_ohlcv(snapshot: ProviderProbeSnapshot) -> bool:
    prices = [
        snapshot.open_price,
        snapshot.high_price,
        snapshot.low_price,
        snapshot.close_price,
    ]
    if any(price is None or price <= 0 for price in prices):
        return False
    if snapshot.volume is None or snapshot.volume < 0:
        return False
    if snapshot.amount is not None and snapshot.amount < 0:
        return False
    high = float(snapshot.high_price)
    low = float(snapshot.low_price)
    open_price = float(snapshot.open_price)
    close_price = float(snapshot.close_price)
    return high >= max(open_price, close_price, low) and low <= min(open_price, close_price, high)


def _adapter_boundary_text(boundary: ProviderSandboxAdapterBoundary) -> str:
    parts = (
        boundary.provider_project_name,
        boundary.adapter_role,
        boundary.boundary_description,
        boundary.external_project_reference,
    )
    if not all(part.strip() for part in parts):
        return ""
    return " | ".join(parts)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _contains_forbidden_live_language(text: str) -> bool:
    normalized = text.lower()
    return any(term in normalized for term in FORBIDDEN_LIVE_LANGUAGE)
