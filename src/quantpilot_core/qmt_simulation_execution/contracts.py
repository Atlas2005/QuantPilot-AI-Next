"""Immutable records for the QMT broker-simulation execution protocol."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TypeAlias


CodeValue: TypeAlias = str | int | None


@dataclass(frozen=True)
class QmtSimulationOrderIntent:
    schema_version: int
    protocol_version: str
    intent_id: str
    created_at: datetime
    expires_at: datetime
    environment: str
    expected_redacted_account_id: str
    account_type: str
    symbol: str
    side: str
    quantity: int
    order_kind: str
    limit_price: float
    source_order_digest: str
    explicit_submit: bool
    intent_hmac: str
    run_label: str | None = None
    source_path: Path | None = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        if self.source_path is not None:
            object.__setattr__(self, "source_path", Path(self.source_path))


@dataclass(frozen=True)
class QmtSimulationOrderState:
    schema_version: int
    protocol_version: str
    intent_id: str
    updated_at: datetime
    status: str
    expected_redacted_account_id: str
    passorder_attempted: bool
    failure_code: str | None
    source_path: Path | None = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        if self.source_path is not None:
            object.__setattr__(self, "source_path", Path(self.source_path))


@dataclass(frozen=True)
class QmtSimulationOrderResult:
    schema_version: int
    protocol_version: str
    intent_id: str
    generated_at: datetime
    status: str
    expected_redacted_account_id: str
    symbol: str
    side: str
    requested_quantity: int
    limit_price: float
    strategy_name: str
    user_order_id: str
    passorder_attempted: bool
    broker_order_reference: str | None
    system_order_id: str | None
    order_status: CodeValue
    submission_status: CodeValue
    filled_quantity: int
    average_fill_price: float | None
    deal_count: int
    failure_code: str | None
    failure_type: str | None
    latest_snapshot_sequence: int | None
    acceptance_limitation: str
    source_path: Path | None = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        if self.source_path is not None:
            object.__setattr__(self, "source_path", Path(self.source_path))


@dataclass(frozen=True)
class BrokerOrderEvidence:
    """Only bounded broker-order fields used for reconciliation."""

    user_order_id: str
    broker_order_reference: str | None = None
    system_order_id: str | None = None
    order_status: CodeValue = None
    submission_status: CodeValue = None
    filled_quantity: int | None = None
    average_fill_price: float | None = None


@dataclass(frozen=True)
class BrokerDealEvidence:
    """Only bounded broker-deal fields used for reconciliation."""

    user_order_id: str
    deal_id: str | None
    fill_quantity: int
    fill_price: float
    broker_order_reference: str | None = None
    system_order_id: str | None = None


# Concise aliases for callers that already operate inside this package boundary.
SimulationOrderIntent = QmtSimulationOrderIntent
SimulationOrderState = QmtSimulationOrderState
SimulationOrderResult = QmtSimulationOrderResult
