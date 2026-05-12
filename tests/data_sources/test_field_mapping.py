import json
from pathlib import Path

from quantpilot_core.data.schema import DAILY_BAR_REQUIRED_FIELDS
from quantpilot_core.data_sources import normalize_field_name, validate_field_mapping


REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_ROOT = REPO_ROOT / "data" / "source_mapping_templates"


def load_templates() -> list[dict]:
    templates: list[dict] = []
    for path in sorted(TEMPLATE_ROOT.glob("*.template.json")):
        with path.open("r", encoding="utf-8") as file:
            templates.append(json.load(file))
    return templates


def test_normalize_field_name() -> None:
    assert normalize_field_name(" Trade-Date ") == "trade_date"
    assert normalize_field_name("trade date") == "trade_date"


def test_field_mapping_templates_load() -> None:
    templates = load_templates()

    assert len(templates) == 5


def test_required_target_fields_exist() -> None:
    for template in load_templates():
        targets = {
            item["target_field"]
            for item in template["field_mappings"]
        }

        assert targets == set(DAILY_BAR_REQUIRED_FIELDS)


def test_validate_field_mapping_returns_no_errors_for_templates() -> None:
    for template in load_templates():
        assert validate_field_mapping(template) == []


def test_invalid_mapping_returns_errors() -> None:
    errors = validate_field_mapping(
        {
            "source_name": "",
            "is_final": True,
            "field_mappings": [
                {
                    "source_field": "",
                    "target_field": "not_a_target",
                    "required": "yes",
                }
            ],
        }
    )

    assert "missing_or_blank:source_name" in errors
    assert "template_must_be_provisional" in errors
    assert "field_mapping_0:missing_source_field" in errors
    assert "field_mapping_0:invalid_target_field" in errors
    assert "field_mapping_0:required_must_be_bool" in errors


def test_no_template_marks_itself_final() -> None:
    assert all(template["is_final"] is False for template in load_templates())

