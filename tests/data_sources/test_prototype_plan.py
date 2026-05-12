import pytest

from quantpilot_core.data_sources import (
    DataSourceCandidateType,
    DataSourcePrototypePlan,
    PrototypeRunMode,
)


def test_data_source_prototype_plan_can_be_created() -> None:
    plan = DataSourcePrototypePlan(
        name="manual fixture prototype",
        candidate_type=DataSourceCandidateType.INTERNAL_FIXTURE,
        run_mode=PrototypeRunMode.MANUAL_ONLY,
        requires_network=False,
        requires_token=False,
        requires_license_review=False,
        allowed_in_ci=True,
        target_asset_scope="fake local a-share daily bars",
        expected_output_contract="daily_bar_schema_0.1.0",
        notes="local fixture only",
    )

    assert plan.name == "manual fixture prototype"
    assert plan.allowed_in_ci is True


def test_network_token_license_flags_exist() -> None:
    plan = DataSourcePrototypePlan(
        name="future public library review",
        candidate_type=DataSourceCandidateType.PUBLIC_PYTHON_LIBRARY,
        run_mode=PrototypeRunMode.DISABLED_IN_CI,
        requires_network=True,
        requires_token=False,
        requires_license_review=True,
        allowed_in_ci=False,
        target_asset_scope="a-share daily bars",
        expected_output_contract="daily_bar_schema_0.1.0",
        notes="manual only",
    )

    assert plan.requires_network is True
    assert plan.requires_token is False
    assert plan.requires_license_review is True


def test_manual_and_ci_disabled_modes_exist() -> None:
    assert PrototypeRunMode.MANUAL_ONLY.value == "manual_only"
    assert PrototypeRunMode.DISABLED_IN_CI.value == "disabled_in_ci"
    assert PrototypeRunMode.REGISTRY_ONLY.value == "registry_only"


def test_external_sources_cannot_be_allowed_in_ci() -> None:
    with pytest.raises(ValueError):
        DataSourcePrototypePlan(
            name="external source",
            candidate_type=DataSourceCandidateType.PUBLIC_PYTHON_LIBRARY,
            run_mode=PrototypeRunMode.MANUAL_ONLY,
            requires_network=True,
            requires_token=False,
            requires_license_review=True,
            allowed_in_ci=True,
            target_asset_scope="a-share daily bars",
            expected_output_contract="daily_bar_schema_0.1.0",
            notes="should fail",
        )

