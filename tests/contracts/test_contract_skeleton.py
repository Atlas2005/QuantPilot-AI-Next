from quantpilot_core.contracts import BaseContract
from quantpilot_core.registry import SimpleRegistry


def test_base_contract_describe() -> None:
    contract = BaseContract(name="base")

    assert contract.describe() == {"name": "base", "version": "0.0.1"}


def test_simple_registry_register_and_retrieve_metadata() -> None:
    registry = SimpleRegistry()

    registry.register("base", {"kind": "contract", "version": "0.0.1"})

    assert registry.get("base") == {"kind": "contract", "version": "0.0.1"}
    assert registry.list_names() == ["base"]

