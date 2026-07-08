"""Platform-neutral account-aware runtime contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class FeeProfileProvenance(str, Enum):
    """Ordered sources used to resolve runtime fees."""

    ACTUAL_BROKER_FILL_FEE = "actual_broker_fill_fee"
    BROKER_RETURNED_ACCOUNT_PROFILE = "broker_returned_account_fee_profile"
    PERSISTED_USER_ACCOUNT_CONFIG = "persisted_user_account_fee_configuration"
    ENGINEERING_FALLBACK = "engineering_fallback"


@dataclass(frozen=True)
class AccountCapabilities:
    """Neutral description of what an account is permitted to trade."""

    account_id: str = "offline-fixture-account"
    main_board: bool = True
    chinext: bool = False
    star_market: bool = False
    beijing_stock_exchange: bool = False
    etf: bool = True
    lof: bool = False
    convertible_bond: bool = False
    risk_warning_st: bool = False
    hong_kong_stock_connect: bool = False
    margin_trading: bool = False
    supported_order_types: tuple[str, ...] = ("limit",)
    can_buy: bool = True
    can_sell: bool = True


@dataclass(frozen=True)
class AccountSnapshot:
    """Serializable account state passed into runtime decisions."""

    account_id: str
    cash: float
    total_equity: float
    positions: Mapping[str, int] = field(default_factory=dict)
    frozen_cash: float = 0.0
    capabilities: AccountCapabilities | None = None


@dataclass(frozen=True)
class RuntimeFeeModel:
    """One side/instrument fee model used for cost and affordability checks."""

    commission_rate: float = 0.0003
    min_commission: float = 5.0
    stamp_duty_rate: float = 0.0
    transfer_fee_rate: float = 0.0
    exchange_fee_rate: float = 0.0
    slippage_bps: float = 5.0


@dataclass(frozen=True)
class PreTradeCostEstimate:
    """Canonical pre-trade cash and cost estimate for one order candidate."""

    instrument_type: str
    side: str
    quantity: int
    reference_price: float
    estimated_fill_price: float
    gross_notional: float
    commission: float
    stamp_duty: float
    transfer_fee: float
    exchange_fee: float
    slippage_cost: float
    total_cost: float
    cash_required: float
    cash_impact: float


@dataclass(frozen=True)
class BrokerFeeProfile:
    """Instrument- and side-aware fee profile without binding to any SDK."""

    profile_id: str = "engineering-fallback-a-share-v1"
    provenance: FeeProfileProvenance = FeeProfileProvenance.ENGINEERING_FALLBACK
    default_buy: RuntimeFeeModel = field(default_factory=RuntimeFeeModel)
    default_sell: RuntimeFeeModel = field(default_factory=RuntimeFeeModel)
    instrument_side_overrides: Mapping[str, Mapping[str, RuntimeFeeModel]] = field(default_factory=dict)
    notes: tuple[str, ...] = ("Deterministic engineering fallback; not broker truth.",)


@dataclass(frozen=True)
class InstrumentTradingRules:
    """Runtime trading rules inferred from metadata/provider rows."""

    symbol: str
    instrument_type: str = "stock"
    board: str = "main_board"
    lot_size: int = 100
    buy_allowed: bool = True
    sell_allowed: bool = True
    is_suspended: bool = False
    is_st: bool = False
    price: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
