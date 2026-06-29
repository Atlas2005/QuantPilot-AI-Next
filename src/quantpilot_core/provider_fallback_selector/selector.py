"""Deterministic provider fallback selection for optional A-share providers."""

from __future__ import annotations

from enum import Enum
from typing import Any

from quantpilot_core.provider_fallback_selector.contracts import (
    ProviderAvailability,
    ProviderCandidateName,
    ProviderCandidateStatus,
    ProviderFallbackPreference,
    ProviderFallbackSelectionRequest,
    ProviderFallbackSelectionResult,
)


def build_default_fallback_order(
    preference: ProviderFallbackPreference,
) -> tuple[ProviderCandidateName, ...]:
    if preference is ProviderFallbackPreference.BAOSTOCK_FIRST:
        return (ProviderCandidateName.BAOSTOCK, ProviderCandidateName.AKSHARE)
    return (ProviderCandidateName.AKSHARE, ProviderCandidateName.BAOSTOCK)


def build_candidate_statuses(
    akshare_status: Any,
    baostock_status: Any,
) -> tuple[ProviderCandidateStatus, ...]:
    return (
        ProviderCandidateStatus(
            name=ProviderCandidateName.AKSHARE,
            availability=_availability_from_dependency_status(akshare_status),
        ),
        ProviderCandidateStatus(
            name=ProviderCandidateName.BAOSTOCK,
            availability=_availability_from_dependency_status(baostock_status),
        ),
    )


def select_provider_candidate(
    request: ProviderFallbackSelectionRequest,
) -> ProviderFallbackSelectionResult:
    order = build_default_fallback_order(request.preference)
    statuses = _status_by_name_last_wins(request.candidates)
    normalized_statuses = {
        name: statuses.get(
            name,
            ProviderCandidateStatus(
                name=name,
                availability=ProviderAvailability.MISSING,
                reason="not reported",
            ),
        )
        for name in order
    }

    selected = next(
        (
            status.name
            for status in normalized_statuses.values()
            if status.availability is ProviderAvailability.AVAILABLE
        ),
        None,
    )
    warnings = tuple(
        _warning_for_status(status)
        for status in normalized_statuses.values()
        if status.availability is not ProviderAvailability.AVAILABLE
    )

    if selected is None:
        return ProviderFallbackSelectionResult(
            selected_provider=None,
            fallback_order=order,
            can_attempt_fetch=False,
            reasons=("no_available_provider",),
            warnings=warnings,
            suggested_next_action=(
                "Install or enable at least one optional provider, or use a fake/offline fixture."
            ),
        )

    selected_status = normalized_statuses[selected]
    can_attempt_fetch = (
        selected_status.availability is ProviderAvailability.AVAILABLE
        if request.require_available
        else selected_status.availability is not ProviderAvailability.DISABLED
    )
    return ProviderFallbackSelectionResult(
        selected_provider=selected,
        fallback_order=order,
        can_attempt_fetch=can_attempt_fetch,
        reasons=(),
        warnings=warnings,
        suggested_next_action=(
            "Attempt a small sample fetch through the selected provider, then pass "
            "normalized bars into small_sample_data_gate."
        ),
    )


def _status_by_name_last_wins(
    candidates: tuple[ProviderCandidateStatus, ...],
) -> dict[ProviderCandidateName, ProviderCandidateStatus]:
    statuses: dict[ProviderCandidateName, ProviderCandidateStatus] = {}
    for candidate in candidates:
        statuses[candidate.name] = candidate
    return statuses


def _availability_from_dependency_status(status: Any) -> ProviderAvailability:
    value = status.value if isinstance(status, Enum) else str(status)
    if value == "available":
        return ProviderAvailability.AVAILABLE
    if value == "missing":
        return ProviderAvailability.MISSING
    return ProviderAvailability.UNHEALTHY


def _warning_for_status(status: ProviderCandidateStatus) -> str:
    suffix = f": {status.reason}" if status.reason else ""
    return f"{status.name.value} {status.availability.value}{suffix}"
