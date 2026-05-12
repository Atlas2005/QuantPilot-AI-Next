"""Market rule contract boundary."""

from dataclasses import dataclass, field

from quantpilot_core.contracts.base import BaseContract


FUTURE_A_SHARE_RULE_SCOPE = (
    "T+1",
    "100-share lot size",
    "limit-up/limit-down",
    "suspension",
    "ST treatment",
    "fees",
    "stamp duty",
    "slippage",
    "liquidity constraints",
)


@dataclass(frozen=True)
class MarketRuleContract(BaseContract):
    """Interface shape for future A-share market rule definitions."""

    market_rules: tuple[str, ...] = FUTURE_A_SHARE_RULE_SCOPE
    assumptions: tuple[str, ...] = field(default_factory=tuple)

    def list_market_rules(self) -> list[str]:
        return list(self.market_rules)

    def explain_assumptions(self) -> list[str]:
        return list(self.assumptions)

