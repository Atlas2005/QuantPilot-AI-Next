from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REQUIRED_PREFLIGHT_FIELDS = {
    "engine_name",
    "preflight_phase",
    "install_allowed_in_this_phase",
    "import_allowed_in_this_phase",
    "prototype_allowed_in_this_phase",
    "final_selection_allowed",
    "requires_isolated_env",
    "required_env_path",
    "project_dependency_allowed",
    "pyproject_dependency_allowed",
    "network_required_for_install",
    "market_data_required_for_minimal_probe",
    "license_review_required",
    "maintenance_review_required",
    "windows_review_required",
    "live_trading_surface_review_required",
    "data_bundle_review_required",
    "a_share_rule_fit_review_required",
    "broker_live_order_path_must_remain_disabled",
    "recommended_next_action",
    "license_risk",
    "maintenance_risk",
    "dependency_risk",
    "windows_risk",
    "live_trading_risk",
    "data_dependency_risk",
    "a_share_rule_fit_risk",
    "notes",
}


def load_preflight(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Preflight metadata must be a JSON object.")
    return data


def validate_preflight(preflight: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    missing = sorted(REQUIRED_PREFLIGHT_FIELDS - set(preflight))
    for field in missing:
        errors.append(f"missing required field: {field}")

    if preflight.get("install_allowed_in_this_phase") is not False:
        errors.append("install_allowed_in_this_phase must be false")
    if preflight.get("import_allowed_in_this_phase") is not False:
        errors.append("import_allowed_in_this_phase must be false")
    if preflight.get("prototype_allowed_in_this_phase") is not False:
        errors.append("prototype_allowed_in_this_phase must be false")
    if preflight.get("final_selection_allowed") is not False:
        errors.append("final_selection_allowed must be false")
    if preflight.get("requires_isolated_env") is not True:
        errors.append("requires_isolated_env must be true")
    if not str(preflight.get("required_env_path", "")).startswith(".venv-prototypes/"):
        errors.append("required_env_path must start with .venv-prototypes/")
    if preflight.get("project_dependency_allowed") is not False:
        errors.append("project_dependency_allowed must be false")
    if preflight.get("pyproject_dependency_allowed") is not False:
        errors.append("pyproject_dependency_allowed must be false")
    if preflight.get("broker_live_order_path_must_remain_disabled") is not True:
        errors.append("broker_live_order_path_must_remain_disabled must be true")

    for key, value in preflight.items():
        normalized = str(value).lower()
        if "trading_ready" in key.lower() and value is True:
            errors.append(f"{key} must not claim trading_ready true")
        if "trading_ready" in normalized and "true" in normalized:
            errors.append(f"{key} must not claim trading_ready true")
        if "approved_for_adapter" in key.lower() and value is True:
            errors.append(f"{key} must not claim approved_for_adapter true")
        if "approved_for_adapter" in normalized and "true" in normalized:
            errors.append(f"{key} must not claim approved_for_adapter true")

    return errors
