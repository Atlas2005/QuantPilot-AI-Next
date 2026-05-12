"""Market rule profile loading and validation."""

import json
from pathlib import Path


REQUIRED_PROFILE_FIELDS = (
    "profile_name",
    "profile_version",
    "market",
    "source_status",
    "source_notes",
    "effective_date",
    "last_reviewed",
    "manual_review_required",
    "lot_rules",
    "t_plus_rules",
    "price_limit_rules",
    "suspension_rules",
    "fee_rules",
    "slippage_rules",
    "liquidity_rules",
)


def load_market_rule_profile(path: str | Path) -> dict:
    """Load a local market rule profile JSON file."""

    profile_path = Path(path)
    with profile_path.open("r", encoding="utf-8") as file:
        profile = json.load(file)
    if not isinstance(profile, dict):
        raise ValueError("Market rule profile must be a JSON object.")
    return profile


def validate_market_rule_profile(profile: dict) -> list[str]:
    """Validate required profile metadata and sections."""

    errors: list[str] = []
    for field in REQUIRED_PROFILE_FIELDS:
        if field not in profile:
            errors.append(f"missing:{field}")

    if errors:
        return errors

    if profile.get("manual_review_required") is not True:
        errors.append("manual_review_required_must_be_true")

    for field in (
        "lot_rules",
        "t_plus_rules",
        "price_limit_rules",
        "suspension_rules",
        "fee_rules",
        "slippage_rules",
        "liquidity_rules",
    ):
        if not isinstance(profile.get(field), dict):
            errors.append(f"section_must_be_object:{field}")

    if "trading_ready" in profile:
        errors.append("profile_must_not_mark_trading_ready")

    return errors

