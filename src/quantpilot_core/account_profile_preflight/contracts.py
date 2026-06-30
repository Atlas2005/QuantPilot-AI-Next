"""Contracts for the R20 account profile and broker config preflight."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AccountStatus(str, Enum):
    ACTIVE = "active"
    READ_ONLY = "read_only"
    SUSPENDED = "suspended"
    KILL_SWITCHED = "kill_switched"


class BrokerCapability(str, Enum):
    A_SHARE_CASH_EQUITY = "a_share_cash_equity"
    ETF = "etf"
    STAR_MARKET = "star_market"
    CHINEXT = "chinext"
    MARGIN_TRADING = "margin_trading"
    SHORT_SELLING = "short_selling"
    CONVERTIBLE_BOND = "convertible_bond"


class TradePermission(str, Enum):
    BUY = "buy"
    SELL = "sell"
    CANCEL = "cancel"
    QUERY_ONLY = "query_only"


class RiskSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class AccountCashProfile:
    currency: str
    available_cash: float
    frozen_cash: float
    total_equity: float


@dataclass(frozen=True)
class AccountPosition:
    symbol: str
    quantity: int
    sellable_quantity: int
    avg_cost: float
    market_value: float
    industry: str | None = None


@dataclass(frozen=True)
class BrokerFeeProfile:
    commission_rate: float
    min_commission: float
    stamp_tax_rate: float
    transfer_fee_rate: float = 0.0
    slippage_bps: float = 0.0


@dataclass(frozen=True)
class BrokerCapabilityProfile:
    broker_name: str
    market: str
    capabilities: tuple[str, ...]
    permissions: tuple[str, ...]


@dataclass(frozen=True)
class AccountRiskLimits:
    max_single_symbol_weight: float
    max_industry_weight: float
    max_total_position_weight: float
    max_daily_turnover: float | None = None
    max_order_value: float | None = None


@dataclass(frozen=True)
class AccountProfile:
    account_id: str
    status: str
    cash: AccountCashProfile
    positions: tuple[AccountPosition, ...]
    broker_fee: BrokerFeeProfile
    broker_capability: BrokerCapabilityProfile
    risk_limits: AccountRiskLimits
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class AccountProfileRiskFlag:
    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class AccountProfilePreflightResult:
    ok: bool
    reason: str
    account_id: str
    risk_flags: tuple[AccountProfileRiskFlag, ...]
    normalized_sellable_by_symbol: dict[str, int]
    normalized_position_weight_by_symbol: dict[str, float]
    normalized_industry_weight: dict[str, float]
