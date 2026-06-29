from pathlib import Path

from quantpilot_core.provider_adapter_probe_plan import (
    ProviderAdapterBoundary,
    ProviderAdapterCandidate,
    ProviderAdapterProbePlan,
    ProviderEndpointCategory,
    ProviderLicenseReview,
    ProviderSchemaRequirement,
    load_provider_adapter_probe_plan,
)


ROOT = Path(__file__).resolve().parents[2]
PLAN_PATH = (
    ROOT
    / "data"
    / "provider_adapter_probe_plan"
    / "mock_provider_adapter_probe_plan.json"
)


def test_provider_adapter_probe_plan_contract_can_be_constructed() -> None:
    plan = load_provider_adapter_probe_plan(PLAN_PATH)

    assert isinstance(plan, ProviderAdapterProbePlan)
    assert isinstance(plan.provider, ProviderAdapterCandidate)
    assert isinstance(plan.schema_requirement, ProviderSchemaRequirement)
    assert isinstance(plan.license_review, ProviderLicenseReview)
    assert isinstance(plan.adapter_boundary, ProviderAdapterBoundary)
    assert plan.endpoint_category is ProviderEndpointCategory.MOCK_DAILY_BAR


def test_static_mock_plan_fixture_loads() -> None:
    plan = load_provider_adapter_probe_plan(PLAN_PATH)

    assert plan.provider.provider_candidate_name == "mock"
    assert plan.provider.explicitly_mock is True
    assert plan.output_classification == "adapter_probe_plan_only"


def test_contract_fields_do_not_create_adapter_or_execution_surface() -> None:
    field_names = " ".join(ProviderAdapterProbePlan.__dataclass_fields__).lower()

    assert "token" not in field_names
    assert "client" not in field_names
    assert "submit" not in field_names

