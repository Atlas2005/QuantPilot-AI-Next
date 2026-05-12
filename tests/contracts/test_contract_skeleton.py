from quantpilot_core.contracts import (
    BaseContract,
    ContractCategory,
    ContractMetadata,
    ContractStatus,
)
from quantpilot_core.registry import SimpleRegistry


def test_base_contract_describe() -> None:
    metadata = ContractMetadata(
        name="base",
        category=ContractCategory.SAFETY,
        version="0.0.1",
        status=ContractStatus.DRAFT,
        description="Base contract test.",
        owner="tests",
        external_dependency="none",
        notes="shape only",
    )
    contract = BaseContract(metadata=metadata)

    description = contract.describe()

    assert description["metadata"] == metadata.as_dict()
    assert description["trading_ready"] is False


def test_simple_registry_register_and_retrieve_metadata() -> None:
    registry = SimpleRegistry()

    registry.register("base", {"kind": "contract", "version": "0.0.1"})

    assert registry.get("base") == {"kind": "contract", "version": "0.0.1"}
    assert registry.list_names() == ["base"]
