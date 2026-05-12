"""Candidate metadata structures for the Phase 1 registry."""

from dataclasses import dataclass


RECOMMENDED_ACTIONS = frozenset(
    {
        "adopt_directly",
        "wrap_with_adapter",
        "borrow_architecture_only",
        "prototype_required",
        "defer_until_foundation_ready",
        "avoid_for_now",
    }
)

EVALUATION_STATUSES = frozenset(
    {
        "not_evaluated",
        "preliminary_review",
        "prototype_required",
        "rejected",
        "approved_for_adapter",
    }
)

PHASE_ALLOWED_VALUES = frozenset(
    {
        "registry_only",
        "prototype_later",
        "adapter_later",
        "deferred",
    }
)

CANDIDATE_TYPES = frozenset(
    {
        "open_source_project",
        "commercial_product_benchmark",
        "professional_terminal_benchmark",
        "open_source_terminal_candidate",
        "data_vendor_candidate",
        "tooling_reference",
    }
)

BENCHMARK_ROLES = frozenset(
    {
        "not_a_benchmark",
        "product_workflow_reference",
        "data_terminal_reference",
        "analytics_terminal_reference",
        "trading_workflow_reference",
        "ui_dashboard_reference",
    }
)

INTEGRATION_POLICIES = frozenset(
    {
        "no_integration_reference_only",
        "registry_only",
        "prototype_later",
        "adapter_later",
        "license_review_required",
        "avoid_for_now",
    }
)

REQUIRED_FIELDS = (
    "name",
    "category",
    "subcategory",
    "homepage",
    "repository",
    "description",
    "primary_use",
    "current_phase_action",
    "evaluation_status",
    "recommended_action",
    "license_review_status",
    "commercial_risk",
    "maintenance_risk",
    "windows_risk",
    "a_share_relevance",
    "integration_risk",
    "phase_allowed",
    "notes",
)

OPTIONAL_FIELD_DEFAULTS = {
    "candidate_type": "open_source_project",
    "benchmark_role": "not_a_benchmark",
    "integration_policy": "registry_only",
}

ALL_FIELDS = REQUIRED_FIELDS + tuple(OPTIONAL_FIELD_DEFAULTS)


@dataclass(frozen=True)
class CandidateMetadata:
    """Static metadata for an open-source candidate.

    Phase 1 records evaluation inputs only. It does not approve integration.
    """

    name: str
    category: str
    subcategory: str
    homepage: str
    repository: str
    description: str
    primary_use: str
    current_phase_action: str
    evaluation_status: str
    recommended_action: str
    license_review_status: str
    commercial_risk: str
    maintenance_risk: str
    windows_risk: str
    a_share_relevance: str
    integration_risk: str
    phase_allowed: str
    notes: str
    candidate_type: str = "open_source_project"
    benchmark_role: str = "not_a_benchmark"
    integration_policy: str = "registry_only"

    @classmethod
    def from_mapping(cls, value: dict[str, str]) -> "CandidateMetadata":
        return cls(**{field: value[field] for field in ALL_FIELDS})
