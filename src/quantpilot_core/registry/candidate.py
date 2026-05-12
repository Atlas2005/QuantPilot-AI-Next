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

    @classmethod
    def from_mapping(cls, value: dict[str, str]) -> "CandidateMetadata":
        return cls(**{field: value[field] for field in REQUIRED_FIELDS})

