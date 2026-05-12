from quantpilot_core import __version__, get_safety_status
from quantpilot_core.contracts import (
    BaseContract,
    ContractCategory,
    ContractMetadata,
    ContractStatus,
)
from quantpilot_core.registry import SimpleRegistry


def test_core_imports() -> None:
    metadata = ContractMetadata(
        name="example",
        category=ContractCategory.SAFETY,
        version="0.0.1",
        status=ContractStatus.DRAFT,
        description="import smoke test",
        owner="tests",
        external_dependency="none",
        notes="shape only",
    )

    assert __version__ == "0.0.1"
    assert callable(get_safety_status)
    assert BaseContract(metadata=metadata).metadata.name == "example"
    assert SimpleRegistry().list_names() == []
