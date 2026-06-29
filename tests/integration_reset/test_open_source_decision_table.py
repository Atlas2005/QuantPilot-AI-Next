from pathlib import Path

from quantpilot_core.integration_reset import (
    GENERIC_INFRASTRUCTURE_MODULES,
    REQUIRED_MODULE_AREAS,
    decisions_by_module_name,
    load_open_source_decision_table,
)


ROOT = Path(__file__).resolve().parents[2]
TABLE_PATH = (
    ROOT
    / "data"
    / "integration_reset"
    / "open_source_integration_decision_table.json"
)
FORBIDDEN_PURE_SELF_BUILD_STATUSES = {
    "pure_self_build",
    "self_build",
    "self_build_only",
    "custom_only",
}


def test_decision_table_loads() -> None:
    decisions = load_open_source_decision_table(TABLE_PATH)

    assert decisions


def test_all_required_module_areas_are_present() -> None:
    decisions = load_open_source_decision_table(TABLE_PATH)
    module_names = {decision.module_name for decision in decisions}

    assert REQUIRED_MODULE_AREAS.issubset(module_names)


def test_generic_infrastructure_modules_must_not_be_reinvented() -> None:
    decisions = decisions_by_module_name(load_open_source_decision_table(TABLE_PATH))

    for module_name in GENERIC_INFRASTRUCTURE_MODULES:
        assert decisions[module_name].must_not_reinvent is True
        assert decisions[module_name].preferred_external_projects


def test_adapter_boundaries_are_present() -> None:
    decisions = load_open_source_decision_table(TABLE_PATH)

    assert all(decision.adapter_boundary for decision in decisions)


def test_deferred_entries_have_reasons() -> None:
    decisions = load_open_source_decision_table(TABLE_PATH)

    for decision in decisions:
        if decision.integration_status == "deferred_with_reason":
            assert decision.why_not_directly_integrated_yet


def test_project_specific_market_reality_sandbox_has_external_adapter_boundaries() -> None:
    decisions = decisions_by_module_name(load_open_source_decision_table(TABLE_PATH))
    sandbox = decisions["market_reality_sandbox"]

    assert sandbox.integration_status == "project_specific_contract_layer"
    assert sandbox.preferred_external_projects
    assert "external" in sandbox.adapter_boundary.lower()
    assert "adapter" in sandbox.adapter_boundary.lower()
    assert "RQAlpha" in sandbox.preferred_external_projects


def test_no_forbidden_pure_self_build_status_exists() -> None:
    decisions = load_open_source_decision_table(TABLE_PATH)

    assert all(
        decision.integration_status not in FORBIDDEN_PURE_SELF_BUILD_STATUSES
        for decision in decisions
    )
    assert all(
        decision.integration_status != "project_specific_contract_layer"
        for decision in decisions
        if decision.module_name in GENERIC_INFRASTRUCTURE_MODULES
    )
