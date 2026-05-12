from quantpilot_core import __version__, get_safety_status
from quantpilot_core.contracts import BaseContract
from quantpilot_core.registry import SimpleRegistry


def test_core_imports() -> None:
    assert __version__ == "0.0.1"
    assert callable(get_safety_status)
    assert BaseContract(name="example").name == "example"
    assert SimpleRegistry().list_names() == []

