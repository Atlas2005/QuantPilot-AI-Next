"""Standard-library loader and validator for the R1 integration reset matrix."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROPOSED_ACTIONS = frozenset(
    {"adopt", "wrap", "prototype", "benchmark_only", "defer", "avoid"}
)
A_SHARE_FIT_VALUES = frozenset({"high", "medium", "low", "unknown"})
CAPITAL_TEST_MVP_RELEVANCE_VALUES = frozenset({"high", "medium", "low"})
RISK_VALUES = frozenset({"low", "medium", "high", "unknown"})

REQUIRED_FIELDS = (
    "name",
    "category",
    "target_role",
    "proposed_action",
    "replaced_or_wrapped_internal_modules",
    "a_share_fit",
    "capital_test_mvp_relevance",
    "integration_stage",
    "install_allowed_in_r1",
    "live_trading_allowed_in_r1",
    "broker_connection_allowed_in_r1",
    "raw_data_fetch_allowed_in_r1",
    "license_risk",
    "maintenance_risk",
    "dependency_risk",
    "requires_isolated_prototype",
    "update_policy_required",
    "notes",
)

R1_FALSE_SAFETY_FIELDS = (
    "install_allowed_in_r1",
    "live_trading_allowed_in_r1",
    "broker_connection_allowed_in_r1",
    "raw_data_fetch_allowed_in_r1",
)


class IntegrationMatrixError(ValueError):
    """Raised when the R1 integration reset matrix is invalid."""


@dataclass(frozen=True)
class IntegrationCandidate:
    """Static R1 integration candidate metadata.

    R1 records architecture intent only. It does not approve installs, data
    fetches, broker connections, live trading, or real order execution.
    """

    name: str
    category: str
    target_role: str
    proposed_action: str
    replaced_or_wrapped_internal_modules: tuple[str, ...]
    a_share_fit: str
    capital_test_mvp_relevance: str
    integration_stage: str
    install_allowed_in_r1: bool
    live_trading_allowed_in_r1: bool
    broker_connection_allowed_in_r1: bool
    raw_data_fetch_allowed_in_r1: bool
    license_risk: str
    maintenance_risk: str
    dependency_risk: str
    requires_isolated_prototype: bool
    update_policy_required: bool
    notes: str

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "IntegrationCandidate":
        normalized = dict(value)
        normalized["replaced_or_wrapped_internal_modules"] = tuple(
            normalized["replaced_or_wrapped_internal_modules"]
        )
        return cls(**{field: normalized[field] for field in REQUIRED_FIELDS})


def load_integration_matrix(path: str | Path) -> list[IntegrationCandidate]:
    """Load and validate the R1 integration reset matrix."""

    matrix_path = Path(path)
    with matrix_path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)

    errors = validate_integration_matrix(raw)
    if errors:
        raise IntegrationMatrixError("; ".join(errors))

    return [IntegrationCandidate.from_mapping(item) for item in raw]


def validate_integration_matrix(raw: Any) -> list[str]:
    """Return validation errors for raw matrix data."""

    errors: list[str] = []
    if not isinstance(raw, list):
        return ["integration matrix must be a JSON list"]
    if not raw:
        return ["integration matrix must not be empty"]

    names: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            errors.append(f"candidate at index {index} must be an object")
            continue

        missing = [field for field in REQUIRED_FIELDS if field not in item]
        if missing:
            errors.append(
                f"candidate at index {index} is missing required fields: {', '.join(missing)}"
            )
            continue

        name = _require_string(item, "name", index, errors)
        if name:
            if name in names:
                errors.append(f"duplicate candidate name: {name}")
            names.add(name)

        for field in (
            "category",
            "target_role",
            "proposed_action",
            "a_share_fit",
            "capital_test_mvp_relevance",
            "integration_stage",
            "license_risk",
            "maintenance_risk",
            "dependency_risk",
            "notes",
        ):
            _require_string(item, field, index, errors)

        modules = item["replaced_or_wrapped_internal_modules"]
        if (
            not isinstance(modules, list)
            or not modules
            or not all(isinstance(module, str) and module.strip() for module in modules)
        ):
            errors.append(
                f"candidate at index {index} field 'replaced_or_wrapped_internal_modules' "
                "must be a non-empty list of strings"
            )

        for field in R1_FALSE_SAFETY_FIELDS:
            if item[field] is not False:
                errors.append(f"{item['name']}: {field} must be false in R1")

        for field in ("requires_isolated_prototype", "update_policy_required"):
            if not isinstance(item[field], bool):
                errors.append(f"{item['name']}: {field} must be a boolean")

        if item["update_policy_required"] is not True:
            errors.append(f"{item['name']}: update_policy_required must be true")

        _validate_enum(item, "proposed_action", PROPOSED_ACTIONS, index, errors)
        _validate_enum(item, "a_share_fit", A_SHARE_FIT_VALUES, index, errors)
        _validate_enum(
            item,
            "capital_test_mvp_relevance",
            CAPITAL_TEST_MVP_RELEVANCE_VALUES,
            index,
            errors,
        )
        for field in ("license_risk", "maintenance_risk", "dependency_risk"):
            _validate_enum(item, field, RISK_VALUES, index, errors)

    return errors


def summarize_by_proposed_action(
    candidates: list[IntegrationCandidate],
) -> dict[str, int]:
    """Count candidates by R1 proposed action."""

    return _summarize(candidates, "proposed_action")


def summarize_by_category(candidates: list[IntegrationCandidate]) -> dict[str, int]:
    """Count candidates by integration category."""

    return _summarize(candidates, "category")


def _summarize(candidates: list[IntegrationCandidate], field: str) -> dict[str, int]:
    summary: dict[str, int] = {}
    for candidate in candidates:
        value = str(getattr(candidate, field))
        summary[value] = summary.get(value, 0) + 1
    return dict(sorted(summary.items()))


def _require_string(
    item: dict[str, Any], field: str, index: int, errors: list[str]
) -> str:
    value = item[field]
    if not isinstance(value, str) or not value.strip():
        errors.append(f"candidate at index {index} field {field!r} must be a non-empty string")
        return ""
    return value


def _validate_enum(
    item: dict[str, Any],
    field: str,
    allowed: frozenset[str],
    index: int,
    errors: list[str],
) -> None:
    value = item[field]
    if value not in allowed:
        allowed_values = ", ".join(sorted(allowed))
        errors.append(
            f"candidate at index {index} field {field!r} has invalid value "
            f"{value!r}; expected one of: {allowed_values}"
        )
