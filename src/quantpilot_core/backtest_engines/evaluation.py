"""Standard-library helpers for backtest engine candidate metadata."""

import json
from pathlib import Path

from quantpilot_core.backtest_engines.types import (
    BacktestEngineCategory,
    BacktestIntegrationPolicy,
    BacktestReadinessStatus,
    BacktestRiskLevel,
)


REQUIRED_FIELDS = (
    "name",
    "category",
    "integration_policy",
    "readiness_status",
    "license_risk",
    "live_trading_risk",
    "a_share_fit_risk",
    "windows_risk",
    "dependency_risk",
    "notes",
)

FULL_TRADING_CATEGORIES = {
    BacktestEngineCategory.FULL_TRADING_PLATFORM.value,
}

LIVE_CAPABLE_MARKERS = (
    "live trading",
    "broker",
    "trading platform",
    "full trading",
)


def load_backtest_engine_candidates(path: str | Path) -> list[dict]:
    """Load local backtest engine candidate metadata."""

    candidate_path = Path(path)
    with candidate_path.open("r", encoding="utf-8") as file:
        candidates = json.load(file)
    if not isinstance(candidates, list):
        raise ValueError("Backtest engine candidate registry must be a JSON list.")
    return candidates


def validate_backtest_engine_candidate(candidate: dict) -> list[str]:
    """Validate one candidate metadata record."""

    errors: list[str] = []
    for field in REQUIRED_FIELDS:
        if field not in candidate:
            errors.append(f"missing:{field}")
        elif not isinstance(candidate[field], str) or not candidate[field].strip():
            errors.append(f"blank_or_non_string:{field}")

    if errors:
        return errors

    _validate_enum(candidate, "category", BacktestEngineCategory, errors)
    _validate_enum(candidate, "integration_policy", BacktestIntegrationPolicy, errors)
    _validate_enum(candidate, "readiness_status", BacktestReadinessStatus, errors)
    for field in (
        "license_risk",
        "live_trading_risk",
        "a_share_fit_risk",
        "windows_risk",
        "dependency_risk",
    ):
        _validate_enum(candidate, field, BacktestRiskLevel, errors)

    if candidate["readiness_status"] == BacktestReadinessStatus.APPROVED_FOR_ADAPTER_LATER.value:
        errors.append("approved_for_adapter_later_not_allowed_in_phase_6a")

    if candidate.get("trading_ready") is True:
        errors.append("candidate_must_not_be_trading_ready")

    if candidate.get("final_selection") is True:
        errors.append("final_selection_not_allowed_in_phase_6a")

    if _is_live_capable(candidate) and candidate["live_trading_risk"] == BacktestRiskLevel.LOW.value:
        errors.append("live_capable_engine_requires_medium_or_high_live_trading_risk")

    if _requires_license_review(candidate) and candidate["license_risk"] == BacktestRiskLevel.LOW.value:
        errors.append("license_review_candidate_must_not_be_low_license_risk")

    return errors


def validate_backtest_engine_candidates(candidates: list[dict]) -> list[str]:
    """Validate all candidate records and uniqueness."""

    errors: list[str] = []
    names: set[str] = set()
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            errors.append(f"candidate_{index}:not_object")
            continue
        name = candidate.get("name")
        if isinstance(name, str):
            if name in names:
                errors.append(f"candidate_{index}:duplicate_name:{name}")
            names.add(name)
        for error in validate_backtest_engine_candidate(candidate):
            errors.append(f"candidate_{index}:{error}")
    return errors


def summarize_backtest_engine_candidates(candidates: list[dict]) -> dict:
    """Return simple counts for local review summaries."""

    by_category: dict[str, int] = {}
    by_policy: dict[str, int] = {}
    by_readiness: dict[str, int] = {}
    for candidate in candidates:
        by_category[candidate["category"]] = by_category.get(candidate["category"], 0) + 1
        by_policy[candidate["integration_policy"]] = (
            by_policy.get(candidate["integration_policy"], 0) + 1
        )
        by_readiness[candidate["readiness_status"]] = (
            by_readiness.get(candidate["readiness_status"], 0) + 1
        )
    return {
        "count": len(candidates),
        "by_category": by_category,
        "by_integration_policy": by_policy,
        "by_readiness_status": by_readiness,
    }


def _validate_enum(candidate: dict, field: str, enum_type: type, errors: list[str]) -> None:
    allowed = {item.value for item in enum_type}
    if candidate[field] not in allowed:
        errors.append(f"invalid_enum:{field}:{candidate[field]}")


def _is_live_capable(candidate: dict) -> bool:
    notes = candidate["notes"].lower()
    return (
        candidate["category"] in FULL_TRADING_CATEGORIES
        or any(marker in notes for marker in LIVE_CAPABLE_MARKERS)
    )


def _requires_license_review(candidate: dict) -> bool:
    return "license review" in candidate["notes"].lower()

