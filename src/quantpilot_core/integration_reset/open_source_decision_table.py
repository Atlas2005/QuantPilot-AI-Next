"""Loader and validator for the R1.1 open-source integration decision table."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REQUIRED_MODULE_AREAS = frozenset(
    {
        "data_provider",
        "market_calendar",
        "backtest_engine",
        "factor_analysis",
        "risk_metrics",
        "portfolio_accounting",
        "order_simulation",
        "agent_orchestration",
        "market_reality_sandbox",
    }
)

GENERIC_INFRASTRUCTURE_MODULES = frozenset(
    {
        "data_provider",
        "market_calendar",
        "backtest_engine",
        "factor_analysis",
        "risk_metrics",
        "portfolio_accounting",
    }
)

PROJECT_SPECIFIC_MODULES = frozenset({"market_reality_sandbox", "order_simulation"})

INTEGRATION_STATUSES = frozenset(
    {
        "candidate_identified",
        "prototype_completed",
        "adapter_required",
        "project_specific_contract_layer",
        "deferred_with_reason",
    }
)

FORBIDDEN_PURE_SELF_BUILD_STATUSES = frozenset(
    {"pure_self_build", "self_build", "self_build_only", "custom_only"}
)

REQUIRED_FIELDS = (
    "module_name",
    "role",
    "preferred_external_projects",
    "integration_status",
    "adapter_boundary",
    "why_not_directly_integrated_yet",
    "must_not_reinvent",
    "next_required_action",
)


class OpenSourceDecisionTableError(ValueError):
    """Raised when the open-source integration decision table is invalid."""


@dataclass(frozen=True)
class OpenSourceIntegrationDecision:
    """R1.1 integration decision for one module area."""

    module_name: str
    role: str
    preferred_external_projects: tuple[str, ...]
    integration_status: str
    adapter_boundary: str
    why_not_directly_integrated_yet: str
    must_not_reinvent: bool
    next_required_action: str

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "OpenSourceIntegrationDecision":
        normalized = dict(value)
        normalized["preferred_external_projects"] = tuple(
            normalized["preferred_external_projects"]
        )
        return cls(**{field: normalized[field] for field in REQUIRED_FIELDS})


def load_open_source_decision_table(
    path: str | Path,
) -> list[OpenSourceIntegrationDecision]:
    """Load and validate the R1.1 open-source integration decision table."""

    table_path = Path(path)
    with table_path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)

    errors = validate_open_source_decision_table(raw)
    if errors:
        raise OpenSourceDecisionTableError("; ".join(errors))

    return [OpenSourceIntegrationDecision.from_mapping(item) for item in raw]


def validate_open_source_decision_table(raw: Any) -> list[str]:
    """Return validation errors for raw decision table data."""

    errors: list[str] = []
    if not isinstance(raw, list):
        return ["open-source decision table must be a JSON list"]
    if not raw:
        return ["open-source decision table must not be empty"]

    module_names: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            errors.append(f"entry at index {index} must be an object")
            continue

        missing = [field for field in REQUIRED_FIELDS if field not in item]
        if missing:
            errors.append(
                f"entry at index {index} is missing required fields: {', '.join(missing)}"
            )
            continue

        module_name = _require_string(item, "module_name", index, errors)
        if module_name:
            if module_name in module_names:
                errors.append(f"duplicate module_name: {module_name}")
            module_names.add(module_name)

        for field in (
            "role",
            "integration_status",
            "adapter_boundary",
            "why_not_directly_integrated_yet",
            "next_required_action",
        ):
            _require_string(item, field, index, errors)

        projects = item["preferred_external_projects"]
        if not isinstance(projects, list):
            errors.append(
                f"{module_name or index}: preferred_external_projects must be a list"
            )
        elif (
            module_name not in PROJECT_SPECIFIC_MODULES
            and not _has_non_empty_strings(projects)
        ):
            errors.append(
                f"{module_name}: preferred_external_projects must be non-empty "
                "unless explicitly project-specific"
            )
        elif projects and not _has_non_empty_strings(projects):
            errors.append(
                f"{module_name}: preferred_external_projects must contain non-empty strings"
            )

        if not isinstance(item["must_not_reinvent"], bool):
            errors.append(f"{module_name or index}: must_not_reinvent must be a boolean")
        elif (
            module_name in GENERIC_INFRASTRUCTURE_MODULES
            and item["must_not_reinvent"] is not True
        ):
            errors.append(
                f"{module_name}: generic infrastructure must be marked must_not_reinvent"
            )

        integration_status = item["integration_status"]
        if integration_status in FORBIDDEN_PURE_SELF_BUILD_STATUSES:
            errors.append(f"{module_name}: pure self-build status is forbidden")
        elif integration_status not in INTEGRATION_STATUSES:
            allowed = ", ".join(sorted(INTEGRATION_STATUSES))
            errors.append(
                f"{module_name}: integration_status {integration_status!r} "
                f"must be one of: {allowed}"
            )

        if (
            module_name in GENERIC_INFRASTRUCTURE_MODULES
            and integration_status == "project_specific_contract_layer"
        ):
            errors.append(
                f"{module_name}: generic infrastructure cannot be marked as a "
                "project-specific self-build contract layer"
            )

        if (
            integration_status == "deferred_with_reason"
            and not str(item["why_not_directly_integrated_yet"]).strip()
        ):
            errors.append(f"{module_name}: deferred entries require a reason")

    missing_modules = sorted(REQUIRED_MODULE_AREAS - module_names)
    for module_name in missing_modules:
        errors.append(f"missing required module area: {module_name}")

    return errors


def decisions_by_module_name(
    decisions: list[OpenSourceIntegrationDecision],
) -> dict[str, OpenSourceIntegrationDecision]:
    """Return decisions keyed by module name."""

    return {decision.module_name: decision for decision in decisions}


def _require_string(
    item: dict[str, Any], field: str, index: int, errors: list[str]
) -> str:
    value = item[field]
    if not isinstance(value, str) or not value.strip():
        errors.append(f"entry at index {index} field {field!r} must be a non-empty string")
        return ""
    return value


def _has_non_empty_strings(values: list[Any]) -> bool:
    return bool(values) and all(isinstance(value, str) and value.strip() for value in values)
