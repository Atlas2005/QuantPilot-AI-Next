from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REQUIRED_CANDIDATE_FIELDS = {
    "name",
    "category",
    "direction",
    "status",
    "required_fields",
    "lookback_window",
    "computation_scope",
    "evidence_status",
    "alpha_claim_allowed",
    "trading_ready",
    "known_limitations",
    "notes",
}

ALLOWED_STATUSES = {"toy", "experimental", "deprecated", "deferred"}
ALLOWED_EVIDENCE_STATUSES = {"toy_fixture_only", "not_evaluated", "rejected", "deferred"}


@dataclass(frozen=True)
class FactorCandidateRecord:
    name: str
    category: str
    direction: str
    status: str
    required_fields: list[str]
    lookback_window: int
    computation_scope: str
    evidence_status: str
    alpha_claim_allowed: bool
    trading_ready: bool
    known_limitations: list[str]
    notes: str


def load_factor_candidates(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError("Factor candidates must be a JSON list.")
    return data


def validate_factor_candidate(candidate: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    name = str(candidate.get("name", "<unknown>"))

    missing = sorted(REQUIRED_CANDIDATE_FIELDS - set(candidate))
    for field in missing:
        errors.append(f"{name}: missing required field: {field}")

    if candidate.get("alpha_claim_allowed") is not False:
        errors.append(f"{name}: alpha_claim_allowed must be false")
    if candidate.get("trading_ready") is not False:
        errors.append(f"{name}: trading_ready must be false")
    if candidate.get("status") not in ALLOWED_STATUSES:
        errors.append(f"{name}: invalid status")
    if candidate.get("evidence_status") not in ALLOWED_EVIDENCE_STATUSES:
        errors.append(f"{name}: invalid evidence_status")
    if str(candidate.get("status", "")).lower() == "validated":
        errors.append(f"{name}: candidate must not claim validated alpha")

    joined_values = " ".join(str(value).lower() for value in candidate.values())
    if "validated alpha" in joined_values:
        errors.append(f"{name}: candidate must not claim validated alpha")
    if "production ready" in joined_values or "trading-ready" in joined_values:
        errors.append(f"{name}: candidate must not claim production readiness")

    return errors


def validate_factor_candidates(candidates: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    seen_names: set[str] = set()
    for candidate in candidates:
        name = str(candidate.get("name", ""))
        if name in seen_names:
            errors.append(f"duplicate candidate name: {name}")
        seen_names.add(name)
        errors.extend(validate_factor_candidate(candidate))
    return errors


def summarize_factor_candidates(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    by_evidence_status: dict[str, int] = {}
    for candidate in candidates:
        status = str(candidate.get("status", "unknown"))
        evidence_status = str(candidate.get("evidence_status", "unknown"))
        by_status[status] = by_status.get(status, 0) + 1
        by_evidence_status[evidence_status] = by_evidence_status.get(evidence_status, 0) + 1

    return {
        "candidate_count": len(candidates),
        "candidate_names": [candidate.get("name") for candidate in candidates],
        "by_status": by_status,
        "by_evidence_status": by_evidence_status,
        "alpha_claim_allowed_count": sum(
            1 for candidate in candidates if candidate.get("alpha_claim_allowed") is True
        ),
        "trading_ready_count": sum(
            1 for candidate in candidates if candidate.get("trading_ready") is True
        ),
    }
