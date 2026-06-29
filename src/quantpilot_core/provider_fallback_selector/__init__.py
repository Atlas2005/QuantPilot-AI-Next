"""Provider fallback selector preflight for optional A-share providers."""

from quantpilot_core.provider_fallback_selector.contracts import (
    ProviderAvailability,
    ProviderCandidateName,
    ProviderCandidateStatus,
    ProviderFallbackPreference,
    ProviderFallbackSelectionRequest,
    ProviderFallbackSelectionResult,
)
from quantpilot_core.provider_fallback_selector.selector import (
    build_candidate_statuses,
    build_default_fallback_order,
    select_provider_candidate,
)

__all__ = [
    "ProviderAvailability",
    "ProviderCandidateName",
    "ProviderCandidateStatus",
    "ProviderFallbackPreference",
    "ProviderFallbackSelectionRequest",
    "ProviderFallbackSelectionResult",
    "build_candidate_statuses",
    "build_default_fallback_order",
    "select_provider_candidate",
]
