"""Field-mapping helpers for manual data-source prototype planning."""

from quantpilot_core.data.schema import DAILY_BAR_REQUIRED_FIELDS


def normalize_field_name(name: str) -> str:
    """Normalize a field name for mapping-template comparison."""

    return "_".join(str(name).strip().lower().replace("-", "_").split())


def validate_field_mapping(mapping: dict) -> list[str]:
    """Validate a mapping template shape without source-specific logic."""

    errors: list[str] = []

    if not isinstance(mapping.get("source_name"), str) or not mapping["source_name"].strip():
        errors.append("missing_or_blank:source_name")

    if mapping.get("is_final") is not False:
        errors.append("template_must_be_provisional")

    field_mappings = mapping.get("field_mappings")
    if not isinstance(field_mappings, list) or not field_mappings:
        return errors + ["missing_or_empty:field_mappings"]

    targets_seen: set[str] = set()
    for index, item in enumerate(field_mappings):
        if not isinstance(item, dict):
            errors.append(f"field_mapping_{index}:not_object")
            continue

        source_field = item.get("source_field")
        target_field = item.get("target_field")
        if not isinstance(source_field, str) or not source_field.strip():
            errors.append(f"field_mapping_{index}:missing_source_field")
        if target_field not in DAILY_BAR_REQUIRED_FIELDS:
            errors.append(f"field_mapping_{index}:invalid_target_field")
        else:
            targets_seen.add(target_field)
        if not isinstance(item.get("required"), bool):
            errors.append(f"field_mapping_{index}:required_must_be_bool")

    missing_targets = set(DAILY_BAR_REQUIRED_FIELDS) - targets_seen
    for target in sorted(missing_targets):
        errors.append(f"missing_target_field:{target}")

    return errors

