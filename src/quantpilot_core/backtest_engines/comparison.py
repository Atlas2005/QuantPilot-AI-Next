from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REQUIRED_COMPARISON_FIELDS = {
    "engine_name",
    "evidence_stage",
    "prototype_status",
    "install_environment",
    "fake_fixture_consumed",
    "toy_metrics_available",
    "direct_fake_fixture_support_observed",
    "data_bundle_or_platform_blocker",
    "live_trading_surface_risk",
    "a_share_rule_fit_evidence",
    "unresolved_a_share_rules",
    "license_commercial_status",
    "maintenance_status",
    "dependency_risk",
    "language_runtime_fit",
    "recommended_next_action",
    "not_recommended_action",
    "rationale",
}


def load_prototype_comparison(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError("Prototype comparison must be a JSON list.")
    return data


def validate_prototype_comparison(records: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    seen_names: set[str] = set()

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append(f"record {index} must be an object")
            continue

        name = str(record.get("engine_name", "")).strip()
        if not name:
            errors.append(f"record {index} missing engine_name")
        elif name in seen_names:
            errors.append(f"duplicate engine_name: {name}")
        else:
            seen_names.add(name)

        missing = sorted(REQUIRED_COMPARISON_FIELDS - set(record))
        for field in missing:
            errors.append(f"{name or index}: missing required field: {field}")

        normalized = {key.lower(): str(value).lower() for key, value in record.items()}
        for key, value in normalized.items():
            if key == "final_selected" and value == "true":
                errors.append(f"{name}: must not be final_selected")
            if "trading_ready" in key and value == "true":
                errors.append(f"{name}: must not be trading_ready")
            if "approved_for_adapter" in key and value == "true":
                errors.append(f"{name}: must not be approved_for_adapter")
            if "final_selected" in value and "true" in value:
                errors.append(f"{name}: text must not claim final_selected true")
            if "trading_ready" in value and "true" in value:
                errors.append(f"{name}: text must not claim trading_ready true")
            if "approved_for_adapter" in value and "true" in value:
                errors.append(f"{name}: text must not claim approved_for_adapter true")

        if (
            record.get("live_trading_surface_risk") == "high"
            and record.get("recommended_next_action") == "create_adapter_now"
        ):
            errors.append(f"{name}: high live risk cannot recommend create_adapter_now")

        if name == "RQAlpha" and record.get("fake_fixture_consumed") is not False:
            errors.append("RQAlpha must not be marked fake_fixture_consumed true")

        if name == "Qlib":
            if record.get("prototype_status") != "not_run":
                errors.append("Qlib prototype_status must remain not_run")
            if record.get("evidence_stage") not in {"metadata_only", "preflight_later"}:
                errors.append("Qlib evidence_stage must remain metadata_only or preflight_later")

        gaps = record.get("unresolved_a_share_rules")
        if not isinstance(gaps, list) or not gaps:
            errors.append(f"{name}: unresolved_a_share_rules must be a non-empty list")

    return errors


def summarize_prototype_comparison(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "engine_count": len(records),
        "engines": [record.get("engine_name") for record in records],
        "toy_success_engines": [
            record.get("engine_name")
            for record in records
            if record.get("prototype_status") == "toy_success"
        ],
        "install_import_only_engines": [
            record.get("engine_name")
            for record in records
            if record.get("prototype_status") == "install_import_success_only"
        ],
        "metadata_only_engines": [
            record.get("engine_name")
            for record in records
            if record.get("evidence_stage") == "metadata_only"
        ],
        "final_selection_made": False,
        "adapter_approved": False,
    }
