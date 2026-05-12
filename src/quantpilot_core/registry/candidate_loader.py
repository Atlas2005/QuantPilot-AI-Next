"""Standard-library loader for open-source candidate metadata."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quantpilot_core.registry.candidate import (
    BENCHMARK_ROLES,
    CANDIDATE_TYPES,
    EVALUATION_STATUSES,
    INTEGRATION_POLICIES,
    PHASE_ALLOWED_VALUES,
    RECOMMENDED_ACTIONS,
    ALL_FIELDS,
    OPTIONAL_FIELD_DEFAULTS,
    REQUIRED_FIELDS,
    CandidateMetadata,
)


class CandidateRegistryError(ValueError):
    """Raised when candidate registry metadata is invalid."""


def load_candidate_registry(path: str | Path) -> list[CandidateMetadata]:
    """Load and validate candidate metadata from a local JSON file."""

    registry_path = Path(path)
    with registry_path.open("r", encoding="utf-8") as file:
        raw = json.load(file)

    if not isinstance(raw, list):
        raise CandidateRegistryError("Candidate registry must be a JSON list.")

    candidates: list[CandidateMetadata] = []
    names: set[str] = set()

    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise CandidateRegistryError(f"Candidate at index {index} must be an object.")

        normalized = _validate_candidate_mapping(item, index)
        name = normalized["name"]
        if name in names:
            raise CandidateRegistryError(f"Duplicate candidate name: {name}")
        names.add(name)

        candidates.append(CandidateMetadata.from_mapping(normalized))

    return candidates


def _validate_candidate_mapping(item: dict[str, Any], index: int) -> dict[str, str]:
    missing = [field for field in REQUIRED_FIELDS if field not in item]
    if missing:
        raise CandidateRegistryError(
            f"Candidate at index {index} is missing required fields: {', '.join(missing)}"
        )

    normalized: dict[str, str] = {
        field: default for field, default in OPTIONAL_FIELD_DEFAULTS.items()
    }
    for field in ALL_FIELDS:
        value = item.get(field, normalized.get(field))
        if not isinstance(value, str):
            raise CandidateRegistryError(
                f"Candidate at index {index} field {field!r} must be a string."
            )
        if not value.strip():
            raise CandidateRegistryError(
                f"Candidate at index {index} field {field!r} must not be empty."
            )
        normalized[field] = value

    _validate_enum(
        normalized["recommended_action"],
        RECOMMENDED_ACTIONS,
        "recommended_action",
        index,
    )
    _validate_enum(
        normalized["evaluation_status"],
        EVALUATION_STATUSES,
        "evaluation_status",
        index,
    )
    _validate_enum(
        normalized["phase_allowed"],
        PHASE_ALLOWED_VALUES,
        "phase_allowed",
        index,
    )
    _validate_enum(
        normalized["candidate_type"],
        CANDIDATE_TYPES,
        "candidate_type",
        index,
    )
    _validate_enum(
        normalized["benchmark_role"],
        BENCHMARK_ROLES,
        "benchmark_role",
        index,
    )
    _validate_enum(
        normalized["integration_policy"],
        INTEGRATION_POLICIES,
        "integration_policy",
        index,
    )

    return normalized


def _validate_enum(value: str, allowed: frozenset[str], field: str, index: int) -> None:
    if value not in allowed:
        allowed_values = ", ".join(sorted(allowed))
        raise CandidateRegistryError(
            f"Candidate at index {index} field {field!r} has invalid value "
            f"{value!r}; expected one of: {allowed_values}."
        )
