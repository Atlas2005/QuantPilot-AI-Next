from pathlib import Path

from quantpilot_core.market_rules.profile import (
    load_market_rule_profile,
    validate_market_rule_profile,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = REPO_ROOT / "data" / "market_rule_profiles" / "a_share_basic_v0_1.json"


def test_profile_loads() -> None:
    profile = load_market_rule_profile(PROFILE_PATH)

    assert profile["profile_name"] == "a_share_basic"


def test_required_metadata_exists() -> None:
    profile = load_market_rule_profile(PROFILE_PATH)

    assert validate_market_rule_profile(profile) == []
    assert profile["profile_version"] == "0.1.0"
    assert profile["market"] == "China A-share"
    assert profile["source_status"] == "manually_review_required"


def test_manual_review_required_is_true() -> None:
    profile = load_market_rule_profile(PROFILE_PATH)

    assert profile["manual_review_required"] is True


def test_rule_sections_exist() -> None:
    profile = load_market_rule_profile(PROFILE_PATH)

    for section in (
        "lot_rules",
        "t_plus_rules",
        "price_limit_rules",
        "suspension_rules",
        "fee_rules",
        "slippage_rules",
        "liquidity_rules",
    ):
        assert isinstance(profile[section], dict)


def test_source_status_does_not_claim_production_readiness() -> None:
    profile = load_market_rule_profile(PROFILE_PATH)

    assert "ready" not in profile["source_status"]
    assert "Provisional" in profile["source_notes"]


def test_profile_does_not_mark_trading_ready() -> None:
    profile = load_market_rule_profile(PROFILE_PATH)

    assert "trading_ready" not in profile

