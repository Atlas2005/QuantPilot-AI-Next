"""Contracts for the Market Reality Sandbox.

These contracts define QuantPilot-owned A-share safety and capital/account
boundaries only. Mature external engines and libraries such as RQAlpha,
vectorbt, Backtrader, Hikyuu, Qlib, exchange_calendars, empyrical, and
quantstats remain adapters, benchmarks, or future integration candidates.

R2 does not implement a full simulator, backtest engine, risk engine, factor
analysis engine, market calendar system, broker integration, live trading, or
order execution path.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


MATURE_EXTERNAL_BOUNDARY_NAMES = (
    "RQAlpha",
    "vectorbt",
    "Backtrader",
    "Hikyuu",
    "Qlib",
    "exchange_calendars",
    "empyrical",
    "quantstats",
)


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class SandboxRejectionReason(str, Enum):
    """Reasons a sandbox order draft can be rejected.

    Rejections are sandbox outcomes only. They are not broker responses and do
    not represent live execution.
    """

    NONE = "none"
    INVALID_LOT_SIZE = "invalid_lot_size"
    SUSPENDED_INSTRUMENT = "suspended_instrument"
    ST_OR_DELISTING_RISK = "st_or_delisting_risk"
    PRICE_LIMIT_VIOLATION = "price_limit_violation"
    T_PLUS_ONE_VIOLATION = "t_plus_one_violation"
    CASH_CONSTRAINT_MISSING = "cash_constraint_missing"
    INSUFFICIENT_CASH = "insufficient_cash"
    CAPITAL_CONSTRAINT_VIOLATION = "capital_constraint_violation"
    ACCOUNT_PERMISSION_BLOCKED = "account_permission_blocked"
    COST_MODEL_MISSING = "cost_model_missing"
    SLIPPAGE_MODEL_MISSING = "slippage_model_missing"
    PROVIDER_FAILURE_ASSUMPTION_MISSING = "provider_failure_assumption_missing"
    DATA_LATENCY_ASSUMPTION_MISSING = "data_latency_assumption_missing"
    LIVE_EXECUTION_FORBIDDEN = "live_execution_forbidden"
    ADAPTER_BOUNDARY_MISSING = "adapter_boundary_missing"


class ValidationSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class ExecutionConstraint:
    """A-share execution feasibility constraints, not an execution engine."""

    t_plus_one_required: bool
    t_zero_eligible: bool
    lot_size: int
    lot_size_required: bool
    price_limit_up: float | None
    price_limit_down: float | None
    same_day_sell_forbidden: bool
    partial_fill_allowed: bool
    rejected_order_model_required: bool


@dataclass(frozen=True)
class TradingCalendarAssumption:
    """Calendar contract boundary; external calendars remain adapters."""

    calendar_name: str
    trading_day: str
    is_trading_day: bool
    session_label: str
    source: str
    external_adapter_boundary: str


@dataclass(frozen=True)
class CostModel:
    """Explicit cost assumptions for sandbox feasibility review only."""

    commission_rate: float
    stamp_duty_rate: float
    transfer_fee_rate: float
    minimum_commission: float
    currency: str
    external_adapter_boundary: str


@dataclass(frozen=True)
class SlippageModel:
    """Explicit slippage assumptions; not a full risk or execution engine."""

    model_name: str
    slippage_bps: float
    liquidity_participation_limit: float
    external_adapter_boundary: str


@dataclass(frozen=True)
class DataLatencyAssumption:
    """Data latency and timestamp audit assumptions for sandbox inputs."""

    provider_name: str
    max_latency_seconds: int
    timestamp_source: str
    timestamp_audit_required: bool
    latency_policy: str


@dataclass(frozen=True)
class ProviderFailureAssumption:
    """Provider failure contract; no data fetching is performed by R2."""

    provider_name: str
    failure_mode: str
    fallback_policy: str
    failure_handling_required: bool


@dataclass(frozen=True)
class AccountConstraint:
    """Account permission and cash constraints for sandbox review only."""

    account_id: str
    available_cash: float | None
    cash_constraint_explicit: bool
    allowed_markets: tuple[str, ...]
    can_trade_a_shares: bool
    can_trade_t_zero_instruments: bool
    permission_notes: str


@dataclass(frozen=True)
class CapitalConstraint:
    """Capital-aware feasibility limits for sandbox order drafts."""

    max_order_notional: float
    max_position_notional: float
    max_cash_usage_ratio: float
    min_cash_reserve: float
    capital_mode: str


@dataclass(frozen=True)
class InstrumentTradingProfile:
    """A-share instrument reality flags required before sandbox acceptance."""

    symbol: str
    market: str
    board: str
    is_suspended: bool
    st_flag_explicit: bool
    is_st: bool
    delisting_risk_explicit: bool
    has_delisting_risk: bool
    price_limit_up: float | None
    price_limit_down: float | None
    t_zero_eligible: bool
    lot_size: int
    external_adapter_boundary: str


@dataclass(frozen=True)
class OrderDraft:
    """Sandbox order draft, never a live order or broker instruction."""

    draft_id: str
    symbol: str
    side: OrderSide
    quantity: int
    limit_price: float
    trade_date: str
    created_at: str
    scenario_id: str
    is_live_order: bool
    broker_instruction_id: str | None
    sandbox_instruction: str
    external_adapter_boundary: str


@dataclass(frozen=True)
class FillSimulation:
    """Fill simulation contract output, not a full execution simulator."""

    requested_quantity: int
    filled_quantity: int
    average_fill_price: float | None
    partial_fill: bool
    rejected: bool
    rejection_reason: SandboxRejectionReason
    notes: str


@dataclass(frozen=True)
class SandboxScenario:
    """Market Reality Sandbox scenario contract.

    External engines remain adapter boundaries or benchmarks. QuantPilot owns
    A-share market reality, capital/account constraints, validation, and audit
    assumptions.
    """

    scenario_id: str
    description: str
    instrument: InstrumentTradingProfile
    execution_constraint: ExecutionConstraint
    calendar: TradingCalendarAssumption
    cost_model: CostModel
    slippage_model: SlippageModel
    account_constraint: AccountConstraint
    capital_constraint: CapitalConstraint
    data_latency: DataLatencyAssumption | None
    provider_failure: ProviderFailureAssumption | None
    external_adapter_boundaries: tuple[str, ...]
    timestamp_audit_required: bool
    no_live_execution: bool


@dataclass(frozen=True)
class SandboxResult:
    """Sandbox validation result, not a live execution report."""

    scenario_id: str
    order_draft: OrderDraft
    fill_simulation: FillSimulation
    accepted_for_sandbox: bool
    rejection_reasons: tuple[SandboxRejectionReason, ...]
    live_execution_claim: bool
    broker_execution_reference: str | None
    audit_timestamp: str
    external_adapter_boundary: str


@dataclass(frozen=True)
class SandboxValidationIssue:
    code: str
    severity: ValidationSeverity
    message: str
    rejection_reason: SandboxRejectionReason
