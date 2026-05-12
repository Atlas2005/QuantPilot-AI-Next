"""Types for local market rule validation."""

from dataclasses import dataclass
from enum import Enum


class MarketSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class BoardType(str, Enum):
    MAIN = "main"
    STAR = "star"
    CHINEXT = "chinext"
    BSE = "bse"
    UNKNOWN = "unknown"


class RiskFlag(str, Enum):
    NORMAL = "normal"
    ST = "st"
    DELISTING = "delisting"
    UNKNOWN = "unknown"


class RuleSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class OrderIntent:
    """Local validation input, not a broker or execution order."""

    symbol: str
    trade_date: str
    side: MarketSide
    quantity: int
    price: float
    previous_close: float
    board: BoardType = BoardType.UNKNOWN
    risk_flag: RiskFlag = RiskFlag.UNKNOWN
    is_suspended: bool = False
    acquired_today_quantity: int = 0
    available_volume: float | None = None


@dataclass(frozen=True)
class RuleViolation:
    code: str
    severity: RuleSeverity
    message: str
    rule_name: str

