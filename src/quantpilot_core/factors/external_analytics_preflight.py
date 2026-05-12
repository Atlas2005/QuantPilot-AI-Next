from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class AnalyticsCandidateType(str, Enum):
    factor_analysis = "factor_analysis"
    portfolio_performance = "portfolio_performance"
    risk_metrics = "risk_metrics"
    ml_research_platform = "ml_research_platform"
    unknown = "unknown"


class AnalyticsIntegrationPolicy(str, Enum):
    preflight_only = "preflight_only"
    isolated_prototype_later = "isolated_prototype_later"
    adapter_later = "adapter_later"
    defer_until_real_data = "defer_until_real_data"
    defer_until_real_returns = "defer_until_real_returns"
    avoid_for_now = "avoid_for_now"


class AnalyticsRiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    unknown = "unknown"


@dataclass(frozen=True)
class ExternalAnalyticsCandidate:
    name: str
    candidate_type: AnalyticsCandidateType
    integration_policy: AnalyticsIntegrationPolicy
    license_risk: AnalyticsRiskLevel
    dependency_risk: AnalyticsRiskLevel
    data_shape_risk: AnalyticsRiskLevel
    a_share_fit_risk: AnalyticsRiskLevel
    runtime_risk: AnalyticsRiskLevel
    requires_real_data: bool
    requires_pandas_like_input: bool
    approved_for_install: bool
    approved_for_adapter: bool
    alpha_claim_allowed: bool
    trading_ready: bool
    notes: str


REQUIRED_ANALYTICS_FIELDS = {
    "name",
    "candidate_type",
    "integration_policy",
    "license_risk",
    "dependency_risk",
    "data_shape_risk",
    "a_share_fit_risk",
    "runtime_risk",
    "requires_real_data",
    "requires_pandas_like_input",
    "approved_for_install",
    "approved_for_adapter",
    "alpha_claim_allowed",
    "trading_ready",
    "notes",
}


def load_external_analytics_preflight(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError("External analytics preflight metadata must be a JSON list.")
    return data


def validate_external_analytics_candidate(candidate: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    name = str(candidate.get("name", "<unknown>"))

    missing = sorted(REQUIRED_ANALYTICS_FIELDS - set(candidate))
    for field in missing:
        errors.append(f"{name}: missing required field: {field}")

    if candidate.get("approved_for_install") is not False:
        errors.append(f"{name}: approved_for_install must be false in Phase 7D")
    if candidate.get("approved_for_adapter") is not False:
        errors.append(f"{name}: approved_for_adapter must be false in Phase 7D")
    if candidate.get("alpha_claim_allowed") is not False:
        errors.append(f"{name}: alpha_claim_allowed must be false")
    if candidate.get("trading_ready") is not False:
        errors.append(f"{name}: trading_ready must be false")
    if candidate.get("final_selected") is True:
        errors.append(f"{name}: final_selected must not be true")
    if name == "Qlib" and candidate.get("approved_for_install") is not False:
        errors.append("Qlib must not be approved for installation in Phase 7D")
    if not str(candidate.get("notes", "")).strip():
        errors.append(f"{name}: notes must explain deferred status")

    enum_checks = [
        ("candidate_type", AnalyticsCandidateType),
        ("integration_policy", AnalyticsIntegrationPolicy),
        ("license_risk", AnalyticsRiskLevel),
        ("dependency_risk", AnalyticsRiskLevel),
        ("data_shape_risk", AnalyticsRiskLevel),
        ("a_share_fit_risk", AnalyticsRiskLevel),
        ("runtime_risk", AnalyticsRiskLevel),
    ]
    for field, enum_class in enum_checks:
        try:
            enum_class(candidate.get(field))
        except ValueError:
            errors.append(f"{name}: invalid {field}")

    return errors


def validate_external_analytics_preflight(candidates: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    seen_names: set[str] = set()
    for candidate in candidates:
        name = str(candidate.get("name", ""))
        if name in seen_names:
            errors.append(f"duplicate analytics candidate name: {name}")
        seen_names.add(name)
        errors.extend(validate_external_analytics_candidate(candidate))
    return errors


def summarize_external_analytics_preflight(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    by_type: dict[str, int] = {}
    by_policy: dict[str, int] = {}
    for candidate in candidates:
        candidate_type = str(candidate.get("candidate_type", "unknown"))
        policy = str(candidate.get("integration_policy", "unknown"))
        by_type[candidate_type] = by_type.get(candidate_type, 0) + 1
        by_policy[policy] = by_policy.get(policy, 0) + 1

    return {
        "candidate_count": len(candidates),
        "candidate_names": [candidate.get("name") for candidate in candidates],
        "by_type": by_type,
        "by_policy": by_policy,
        "approved_for_install_count": sum(
            1 for candidate in candidates if candidate.get("approved_for_install") is True
        ),
        "approved_for_adapter_count": sum(
            1 for candidate in candidates if candidate.get("approved_for_adapter") is True
        ),
        "alpha_claim_allowed_count": sum(
            1 for candidate in candidates if candidate.get("alpha_claim_allowed") is True
        ),
        "trading_ready_count": sum(
            1 for candidate in candidates if candidate.get("trading_ready") is True
        ),
    }
