import json

from quantpilot_core.contracts import (
    AdapterAction,
    AgentSkillContract,
    BacktestEngineContract,
    BaseContract,
    ContractCategory,
    ContractMetadata,
    ContractStatus,
    DataSourceContract,
    DataValidatorContract,
    FactorEngineContract,
    MarketRuleContract,
    PortfolioEngineContract,
)


def metadata_for(category: ContractCategory) -> ContractMetadata:
    return ContractMetadata(
        name=f"{category.value}_contract",
        category=category,
        version="0.0.1",
        status=ContractStatus.DRAFT,
        description=f"Boundary for {category.value}.",
        owner="architecture_review",
        external_dependency="none",
        notes="contract shape only",
    )


def test_metadata_can_be_created_and_serialized() -> None:
    metadata = metadata_for(ContractCategory.DATA_SOURCE)

    serialized = metadata.as_dict()

    assert serialized["name"] == "data_source_contract"
    assert serialized["category"] == "data_source"
    assert serialized["status"] == "draft"
    json.dumps(serialized)


def test_base_contract_describe_returns_serializable_dict() -> None:
    contract = BaseContract(
        metadata=metadata_for(ContractCategory.SAFETY),
        scope_warnings=("no implementation",),
    )

    description = contract.describe()

    assert description["metadata"]["category"] == "safety"
    assert description["scope_warnings"] == ["no implementation"]
    assert description["trading_ready"] is False
    json.dumps(description)


def test_all_contract_classes_instantiate_with_expected_categories() -> None:
    contracts = [
        DataSourceContract(metadata=metadata_for(ContractCategory.DATA_SOURCE)),
        DataValidatorContract(metadata=metadata_for(ContractCategory.DATA_VALIDATOR)),
        MarketRuleContract(metadata=metadata_for(ContractCategory.MARKET_RULE)),
        BacktestEngineContract(metadata=metadata_for(ContractCategory.BACKTEST_ENGINE)),
        FactorEngineContract(metadata=metadata_for(ContractCategory.FACTOR_ENGINE)),
        PortfolioEngineContract(metadata=metadata_for(ContractCategory.PORTFOLIO_ENGINE)),
        AgentSkillContract(metadata=metadata_for(ContractCategory.AGENT_SKILL)),
    ]

    assert [contract.metadata.category for contract in contracts] == [
        ContractCategory.DATA_SOURCE,
        ContractCategory.DATA_VALIDATOR,
        ContractCategory.MARKET_RULE,
        ContractCategory.BACKTEST_ENGINE,
        ContractCategory.FACTOR_ENGINE,
        ContractCategory.PORTFOLIO_ENGINE,
        ContractCategory.AGENT_SKILL,
    ]


def test_contract_methods_are_descriptive_only() -> None:
    assert DataSourceContract(
        metadata=metadata_for(ContractCategory.DATA_SOURCE),
        supported_assets=("a_share_equity",),
        required_fields=("symbol", "date"),
        data_limitations=("no data fetching",),
    ).list_supported_assets() == ["a_share_equity"]

    assert DataValidatorContract(
        metadata=metadata_for(ContractCategory.DATA_VALIDATOR),
        validation_rules=("schema completeness",),
        failure_policy=("fail closed",),
    ).explain_failure_policy() == ["fail closed"]

    market_contract = MarketRuleContract(
        metadata=metadata_for(ContractCategory.MARKET_RULE),
        assumptions=("future scope only",),
    )
    assert "T+1" in market_contract.list_market_rules()
    assert market_contract.explain_assumptions() == ["future scope only"]

    assert BacktestEngineContract(
        metadata=metadata_for(ContractCategory.BACKTEST_ENGINE),
        engine_assumptions=("no engine selected",),
        execution_model_notes=("no execution model",),
    ).list_engine_assumptions() == ["no engine selected"]

    assert FactorEngineContract(
        metadata=metadata_for(ContractCategory.FACTOR_ENGINE),
        factor_inputs=("future data contract",),
        factor_limitations=("no factor calculation",),
    ).explain_factor_limitations() == ["no factor calculation"]

    assert PortfolioEngineContract(
        metadata=metadata_for(ContractCategory.PORTFOLIO_ENGINE),
        risk_constraints=("future risk policy",),
        allocation_assumptions=("no optimizer",),
    ).list_risk_constraints() == ["future risk policy"]

    assert AgentSkillContract(
        metadata=metadata_for(ContractCategory.AGENT_SKILL),
        allowed_tools=("none",),
    ).list_allowed_tools() == ["none"]


def test_no_contract_marks_trading_ready() -> None:
    contracts = [
        BaseContract(metadata=metadata_for(ContractCategory.SAFETY)),
        DataSourceContract(metadata=metadata_for(ContractCategory.DATA_SOURCE)),
        BacktestEngineContract(metadata=metadata_for(ContractCategory.BACKTEST_ENGINE)),
        AgentSkillContract(metadata=metadata_for(ContractCategory.AGENT_SKILL)),
    ]

    assert all(contract.describe()["trading_ready"] is False for contract in contracts)


def test_adapter_action_enum_matches_phase_1_classification_language() -> None:
    assert {action.value for action in AdapterAction} == {
        "adopt_directly",
        "wrap_with_adapter",
        "borrow_architecture_only",
        "prototype_required",
        "defer_until_foundation_ready",
        "avoid_for_now",
    }

