"""Contracts for the R14 paper ledger dry path."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class PaperOrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class PaperOrderStatus(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class PaperLedgerStatus(str, Enum):
    READY = "ready"
    REJECTED = "rejected"
    NO_GATE_PASS = "no_gate_pass"
    INSUFFICIENT_CASH = "insufficient_cash"
    INVALID_ORDER = "invalid_order"


@dataclass(frozen=True)
class PaperLedgerAccount:
    cash: float
    positions: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class PaperLedgerOrderIntent:
    symbol: str
    side: PaperOrderSide
    quantity: int
    limit_price: float


@dataclass(frozen=True)
class PaperLedgerResult:
    status: PaperLedgerStatus
    order_status: PaperOrderStatus
    symbol: str
    side: PaperOrderSide
    requested_quantity: int
    filled_quantity: int
    fill_price: float | None
    cash_before: float
    cash_after: float
    position_before: int
    position_after: int
    account_after: PaperLedgerAccount
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    suggested_next_action: str
