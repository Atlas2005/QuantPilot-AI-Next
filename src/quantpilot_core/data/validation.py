"""Standard-library validation for local daily bar fixtures."""

from datetime import datetime

from quantpilot_core.data.schema import (
    DAILY_BAR_NUMERIC_FIELDS,
    DAILY_BAR_REQUIRED_FIELDS,
)
from quantpilot_core.data.types import AdjustmentType, AssetType


def validate_daily_bar_record(record: dict) -> list[str]:
    """Validate one local daily bar record without checking market truth."""

    errors: list[str] = []

    for field in DAILY_BAR_REQUIRED_FIELDS:
        value = record.get(field)
        if value is None or str(value).strip() == "":
            errors.append(f"missing_or_blank:{field}")

    if errors:
        return errors

    numeric_values: dict[str, float] = {}
    for field in DAILY_BAR_NUMERIC_FIELDS:
        try:
            numeric_values[field] = float(record[field])
        except (TypeError, ValueError):
            errors.append(f"invalid_numeric:{field}")

    if errors:
        return errors

    for field in ("open", "high", "low", "close"):
        if numeric_values[field] < 0:
            errors.append(f"negative_price:{field}")

    if numeric_values["high"] < numeric_values["low"]:
        errors.append("invalid_price_range:high_lt_low")

    if numeric_values["volume"] < 0:
        errors.append("negative_volume")

    if numeric_values["amount"] < 0:
        errors.append("negative_amount")

    if not _is_valid_date(record["trade_date"]):
        errors.append("invalid_trade_date")

    if record["adjustment"] not in {item.value for item in AdjustmentType}:
        errors.append("invalid_adjustment")

    if record["asset_type"] not in {item.value for item in AssetType}:
        errors.append("invalid_asset_type")

    return errors


def validate_daily_bar_sequence(records: list[dict]) -> list[str]:
    """Validate daily bar rows as a sequence without using exchange calendars."""

    errors: list[str] = []
    seen_keys: set[tuple[str, str]] = set()
    last_date_by_symbol: dict[str, str] = {}

    for index, record in enumerate(records):
        record_errors = validate_daily_bar_record(record)
        errors.extend(f"row_{index}:{error}" for error in record_errors)

        symbol = str(record.get("symbol", "")).strip()
        trade_date = str(record.get("trade_date", "")).strip()
        if not symbol or not trade_date:
            continue

        key = (symbol, trade_date)
        if key in seen_keys:
            errors.append(f"row_{index}:duplicate_symbol_trade_date:{symbol}:{trade_date}")
        seen_keys.add(key)

        previous_date = last_date_by_symbol.get(symbol)
        if previous_date is not None and trade_date < previous_date:
            errors.append(f"row_{index}:unsorted_trade_date:{symbol}")
        last_date_by_symbol[symbol] = trade_date

    return errors


def _is_valid_date(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return True

