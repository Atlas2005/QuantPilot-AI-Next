"""Load and validate backtest prototype isolation plans."""

import json
from pathlib import Path

from quantpilot_core.backtest_engines.prototype_plan import (
    PrototypePriority,
    PrototypeRunMode,
    PrototypeRisk,
)


REQUIRED_PLAN_FIELDS = (
    "engine_name",
    "priority",
    "run_mode",
    "requires_external_package",
    "requires_network",
    "requires_market_data",
    "requires_live_trading_isolation",
    "requires_license_review",
    "expected_input_contract",
    "expected_output_artifact",
    "a_share_rule_fit_questions",
    "prototype_success_criteria",
    "risks",
    "notes",
)

BOOLEAN_FIELDS = (
    "requires_external_package",
    "requires_network",
    "requires_market_data",
    "requires_live_trading_isolation",
    "requires_license_review",
)

LIST_FIELDS = (
    "a_share_rule_fit_questions",
    "prototype_success_criteria",
    "risks",
)

LIVE_TRADING_CAPABLE_ENGINES = {
    "Backtrader",
    "LEAN",
    "vn.py / VeighNa",
    "NautilusTrader",
}


def load_backtest_prototype_plans(path: str | Path) -> list[dict]:
    """Load local prototype plan metadata."""

    plan_path = Path(path)
    with plan_path.open("r", encoding="utf-8") as file:
        plans = json.load(file)
    if not isinstance(plans, list):
        raise ValueError("Backtest prototype plans must be a JSON list.")
    return plans


def validate_backtest_prototype_plan(plan: dict) -> list[str]:
    """Validate one prototype isolation plan."""

    errors: list[str] = []
    for field in REQUIRED_PLAN_FIELDS:
        if field not in plan:
            errors.append(f"missing:{field}")

    if errors:
        return errors

    _validate_enum(plan, "priority", PrototypePriority, errors)
    _validate_enum(plan, "run_mode", PrototypeRunMode, errors)

    if plan["run_mode"] not in {item.value for item in PrototypeRunMode}:
        errors.append("invalid_run_mode")

    for field in BOOLEAN_FIELDS:
        if not isinstance(plan[field], bool):
            errors.append(f"not_bool:{field}")

    for field in LIST_FIELDS:
        if not _is_non_empty_string_list(plan[field]):
            errors.append(f"not_non_empty_string_list:{field}")

    for field in ("engine_name", "expected_input_contract", "expected_output_artifact", "notes"):
        if not isinstance(plan[field], str) or not plan[field].strip():
            errors.append(f"blank_or_non_string:{field}")

    if plan.get("final_selection") is True:
        errors.append("final_selection_not_allowed")

    if plan.get("allowed_in_ci") is True:
        errors.append("ci_execution_not_allowed")

    if plan.get("trading_ready") is True:
        errors.append("trading_ready_not_allowed")

    if (
        plan["engine_name"] in LIVE_TRADING_CAPABLE_ENGINES
        and plan["requires_live_trading_isolation"] is not True
    ):
        errors.append("live_trading_capable_engine_requires_isolation")

    if plan["requires_external_package"] is True and plan["run_mode"] not in {
        PrototypeRunMode.MANUAL_ONLY.value,
        PrototypeRunMode.DISABLED_IN_CI.value,
        PrototypeRunMode.ISOLATED_ENVIRONMENT_REQUIRED.value,
        PrototypeRunMode.METADATA_ONLY.value,
    }:
        errors.append("external_package_plan_must_remain_manual_or_isolated")

    return errors


def validate_backtest_prototype_plans(plans: list[dict]) -> list[str]:
    """Validate all prototype plans and uniqueness."""

    errors: list[str] = []
    names: set[str] = set()
    for index, plan in enumerate(plans):
        if not isinstance(plan, dict):
            errors.append(f"plan_{index}:not_object")
            continue
        name = plan.get("engine_name")
        if isinstance(name, str):
            if name in names:
                errors.append(f"plan_{index}:duplicate_engine_name:{name}")
            names.add(name)
        for error in validate_backtest_prototype_plan(plan):
            errors.append(f"plan_{index}:{error}")
    return errors


def summarize_backtest_prototype_plans(plans: list[dict]) -> dict:
    """Return simple local summary counts."""

    by_priority: dict[str, int] = {}
    by_run_mode: dict[str, int] = {}
    for plan in plans:
        by_priority[plan["priority"]] = by_priority.get(plan["priority"], 0) + 1
        by_run_mode[plan["run_mode"]] = by_run_mode.get(plan["run_mode"], 0) + 1
    return {
        "count": len(plans),
        "by_priority": by_priority,
        "by_run_mode": by_run_mode,
    }


def _validate_enum(plan: dict, field: str, enum_type: type, errors: list[str]) -> None:
    allowed = {item.value for item in enum_type}
    if plan[field] not in allowed:
        errors.append(f"invalid_enum:{field}:{plan[field]}")


def _is_non_empty_string_list(value: object) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and item.strip() for item in value)
    )

