"""A-share market rule validation foundations."""

from quantpilot_core.market_rules.a_share import validate_order_intent
from quantpilot_core.market_rules.profile import (
    load_market_rule_profile,
    validate_market_rule_profile,
)
from quantpilot_core.market_rules.types import (
    BoardType,
    MarketSide,
    OrderIntent,
    RiskFlag,
    RuleSeverity,
    RuleViolation,
)

__all__ = [
    "BoardType",
    "MarketSide",
    "OrderIntent",
    "RiskFlag",
    "RuleSeverity",
    "RuleViolation",
    "load_market_rule_profile",
    "validate_market_rule_profile",
    "validate_order_intent",
]

