import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFINITIONS_PATH = ROOT / "data" / "factor_definitions" / "toy_factors.json"


def test_toy_factor_definitions_load() -> None:
    definitions = json.loads(DEFINITIONS_PATH.read_text(encoding="utf-8"))

    assert definitions


def test_toy_factor_definition_required_fields_and_safety_flags() -> None:
    definitions = json.loads(DEFINITIONS_PATH.read_text(encoding="utf-8"))
    required_fields = {
        "name",
        "category",
        "direction",
        "status",
        "description",
        "required_fields",
        "lookback_window",
        "allowed_data_scope",
        "alpha_claim_allowed",
        "trading_ready",
        "notes",
    }

    for definition in definitions:
        assert required_fields.issubset(definition)
        assert definition["alpha_claim_allowed"] is False
        assert definition["trading_ready"] is False
        assert definition["status"] == "toy"
