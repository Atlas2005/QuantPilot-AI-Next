"""Immutable canonical records for completed QMT read-only snapshots."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, TypeAlias

from .redaction import PrimitiveMetadataValue, bounded_provider_metadata


ProviderMetadata: TypeAlias = Mapping[str, PrimitiveMetadataValue]
SourceFieldProvenance: TypeAlias = Mapping[str, Mapping[str, tuple[str, ...]]]
CodeValue: TypeAlias = str | int | None


def _empty_metadata() -> ProviderMetadata:
    return MappingProxyType({})


def _freeze_metadata(values: Mapping[str, Any]) -> ProviderMetadata:
    return MappingProxyType(bounded_provider_metadata(values))


def _freeze_provenance(values: SourceFieldProvenance) -> SourceFieldProvenance:
    sections: dict[str, Mapping[str, tuple[str, ...]]] = {}
    for section, fields in values.items():
        sections[str(section)] = MappingProxyType(
            {str(name): tuple(str(source) for source in sources) for name, sources in fields.items()}
        )
    return MappingProxyType(sections)


@dataclass(frozen=True)
class FailureInfo:
    section: str
    code: str
    message: str
    exception_type: str | None = None


@dataclass(frozen=True)
class QueryStatus:
    ok: bool
    error: str | None = None


@dataclass(frozen=True)
class QueryStatusBundle:
    account: QueryStatus
    positions: QueryStatus
    orders: QueryStatus
    trades: QueryStatus

    def for_section(self, section: str) -> QueryStatus:
        if section not in {"account", "positions", "orders", "trades"}:
            raise KeyError(section)
        return getattr(self, section)


@dataclass(frozen=True)
class RuntimeMetadata:
    python_version: str
    qmt_runtime: str
    python_implementation: str | None = None
    qmt_version: str | None = None
    platform: str | None = None
    metadata: ProviderMetadata = field(default_factory=_empty_metadata)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))


@dataclass(frozen=True)
class ReadOnlySafetyState:
    order_submission_enabled: bool = False
    cancel_enabled: bool = False
    passorder_invoked: bool = False
    cancel_invoked: bool = False


@dataclass(frozen=True)
class AccountRecord:
    redacted_account_id: str
    account_type: str
    enabled: bool | None
    login_state: str | None
    trading_date: str | None
    total_assets: float | None
    available_cash: float | None
    withdrawable_cash: float | None
    frozen_cash: float | None
    frozen_commission: float | None
    stock_market_value: float | None
    fund_market_value: float | None
    bond_market_value: float | None
    total_instrument_value: float | None
    position_profit: float | None
    entrust_asset: float | None
    assure_asset: float | None
    provider_status: str | None
    provider_metadata: ProviderMetadata = field(default_factory=_empty_metadata)

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider_metadata", _freeze_metadata(self.provider_metadata))


@dataclass(frozen=True)
class PositionRecord:
    symbol: str | None
    instrument_name: str | None
    total_quantity: int | None
    available_quantity: int | None
    frozen_quantity: int | None
    on_road_quantity: int | None
    yesterday_quantity: int | None
    average_cost: float | None
    open_cost: float | None
    latest_price: float | None
    market_value: float | None
    floating_profit: float | None
    profit_ratio: float | None
    trading_day: str | None
    provider_metadata: ProviderMetadata = field(default_factory=_empty_metadata)

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider_metadata", _freeze_metadata(self.provider_metadata))


@dataclass(frozen=True)
class OrderRecord:
    broker_order_reference: str | None
    system_order_id: str | None
    symbol: str | None
    side: str | None
    operation_label: str | None
    order_price_type: CodeValue
    limit_price: float | None
    original_quantity: int | None
    filled_quantity: int | None
    remaining_quantity: int | None
    cancelled_quantity: int | None
    average_traded_price: float | None
    order_status: CodeValue
    submission_status: CodeValue
    error_id: CodeValue
    error_message: str | None
    cancel_information: str | None
    insert_date: str | None
    insert_time: str | None
    trade_amount: float | None
    investment_remark: str | None
    provider_metadata: ProviderMetadata = field(default_factory=_empty_metadata)

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider_metadata", _freeze_metadata(self.provider_metadata))


@dataclass(frozen=True)
class TradeRecord:
    trade_id: str | None
    order_reference: str | None
    system_order_id: str | None
    symbol: str | None
    side: str | None
    operation_label: str | None
    fill_price: float | None
    fill_quantity: int | None
    fill_amount: float | None
    commission: float | None
    trade_date: str | None
    trade_time: str | None
    investment_remark: str | None
    provider_metadata: ProviderMetadata = field(default_factory=_empty_metadata)

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider_metadata", _freeze_metadata(self.provider_metadata))


@dataclass(frozen=True)
class QmtBridgeSnapshot:
    schema_version: int
    bridge_version: str
    generated_at: datetime
    sequence: int
    snapshot_id: str
    qmt_trading_date: str | None
    provider: str
    environment: str
    redacted_account_id: str
    account_type: str
    account_status: str | None
    account: AccountRecord | None
    positions: tuple[PositionRecord, ...]
    orders: tuple[OrderRecord, ...]
    trades: tuple[TradeRecord, ...]
    query_status: QueryStatusBundle
    runtime: RuntimeMetadata
    source_field_provenance: SourceFieldProvenance
    safety: ReadOnlySafetyState
    failures: tuple[FailureInfo, ...]
    source_path: Path | None = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "positions", tuple(self.positions))
        object.__setattr__(self, "orders", tuple(self.orders))
        object.__setattr__(self, "trades", tuple(self.trades))
        object.__setattr__(self, "failures", tuple(self.failures))
        object.__setattr__(
            self,
            "source_field_provenance",
            _freeze_provenance(self.source_field_provenance),
        )
        if self.source_path is not None:
            object.__setattr__(self, "source_path", Path(self.source_path))

    def age_seconds(self, now: datetime) -> float:
        """Return heartbeat age relative to an aware clock value."""

        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        return (now - self.generated_at).total_seconds()


def snapshot_to_mapping(snapshot: QmtBridgeSnapshot) -> dict[str, Any]:
    """Convert a validated snapshot record back to the exact JSON protocol."""

    def metadata(value: Mapping[str, PrimitiveMetadataValue]) -> dict[str, PrimitiveMetadataValue]:
        return dict(value)

    def failure(value: FailureInfo) -> dict[str, Any]:
        return {
            "section": value.section,
            "code": value.code,
            "message": value.message,
            "exception_type": value.exception_type,
        }

    account = None
    if snapshot.account is not None:
        account = {
            "redacted_account_id": snapshot.account.redacted_account_id,
            "account_type": snapshot.account.account_type,
            "enabled": snapshot.account.enabled,
            "login_state": snapshot.account.login_state,
            "trading_date": snapshot.account.trading_date,
            "total_assets": snapshot.account.total_assets,
            "available_cash": snapshot.account.available_cash,
            "withdrawable_cash": snapshot.account.withdrawable_cash,
            "frozen_cash": snapshot.account.frozen_cash,
            "frozen_commission": snapshot.account.frozen_commission,
            "stock_market_value": snapshot.account.stock_market_value,
            "fund_market_value": snapshot.account.fund_market_value,
            "bond_market_value": snapshot.account.bond_market_value,
            "total_instrument_value": snapshot.account.total_instrument_value,
            "position_profit": snapshot.account.position_profit,
            "entrust_asset": snapshot.account.entrust_asset,
            "assure_asset": snapshot.account.assure_asset,
            "provider_status": snapshot.account.provider_status,
            "provider_metadata": metadata(snapshot.account.provider_metadata),
        }

    positions = [
        {
            "symbol": item.symbol,
            "instrument_name": item.instrument_name,
            "total_quantity": item.total_quantity,
            "available_quantity": item.available_quantity,
            "frozen_quantity": item.frozen_quantity,
            "on_road_quantity": item.on_road_quantity,
            "yesterday_quantity": item.yesterday_quantity,
            "average_cost": item.average_cost,
            "open_cost": item.open_cost,
            "latest_price": item.latest_price,
            "market_value": item.market_value,
            "floating_profit": item.floating_profit,
            "profit_ratio": item.profit_ratio,
            "trading_day": item.trading_day,
            "provider_metadata": metadata(item.provider_metadata),
        }
        for item in snapshot.positions
    ]
    orders = [
        {
            "broker_order_reference": item.broker_order_reference,
            "system_order_id": item.system_order_id,
            "symbol": item.symbol,
            "side": item.side,
            "operation_label": item.operation_label,
            "order_price_type": item.order_price_type,
            "limit_price": item.limit_price,
            "original_quantity": item.original_quantity,
            "filled_quantity": item.filled_quantity,
            "remaining_quantity": item.remaining_quantity,
            "cancelled_quantity": item.cancelled_quantity,
            "average_traded_price": item.average_traded_price,
            "order_status": item.order_status,
            "submission_status": item.submission_status,
            "error_id": item.error_id,
            "error_message": item.error_message,
            "cancel_information": item.cancel_information,
            "insert_date": item.insert_date,
            "insert_time": item.insert_time,
            "trade_amount": item.trade_amount,
            "investment_remark": item.investment_remark,
            "provider_metadata": metadata(item.provider_metadata),
        }
        for item in snapshot.orders
    ]
    trades = [
        {
            "trade_id": item.trade_id,
            "order_reference": item.order_reference,
            "system_order_id": item.system_order_id,
            "symbol": item.symbol,
            "side": item.side,
            "operation_label": item.operation_label,
            "fill_price": item.fill_price,
            "fill_quantity": item.fill_quantity,
            "fill_amount": item.fill_amount,
            "commission": item.commission,
            "trade_date": item.trade_date,
            "trade_time": item.trade_time,
            "investment_remark": item.investment_remark,
            "provider_metadata": metadata(item.provider_metadata),
        }
        for item in snapshot.trades
    ]
    generated_at = snapshot.generated_at.isoformat().replace("+00:00", "Z")
    return {
        "schema_version": snapshot.schema_version,
        "bridge_version": snapshot.bridge_version,
        "generated_at": generated_at,
        "sequence": snapshot.sequence,
        "snapshot_id": snapshot.snapshot_id,
        "qmt_trading_date": snapshot.qmt_trading_date,
        "provider": snapshot.provider,
        "environment": snapshot.environment,
        "redacted_account_id": snapshot.redacted_account_id,
        "account_type": snapshot.account_type,
        "account_status": snapshot.account_status,
        "account": account,
        "positions": positions,
        "orders": orders,
        "trades": trades,
        "query_status": {
            section: {
                "ok": snapshot.query_status.for_section(section).ok,
                "error": snapshot.query_status.for_section(section).error,
            }
            for section in ("account", "positions", "orders", "trades")
        },
        "runtime": {
            "python_version": snapshot.runtime.python_version,
            "python_implementation": snapshot.runtime.python_implementation,
            "qmt_runtime": snapshot.runtime.qmt_runtime,
            "qmt_version": snapshot.runtime.qmt_version,
            "platform": snapshot.runtime.platform,
            "metadata": metadata(snapshot.runtime.metadata),
        },
        "source_field_provenance": {
            section: {name: list(sources) for name, sources in fields.items()}
            for section, fields in snapshot.source_field_provenance.items()
        },
        "safety": {
            "order_submission_enabled": snapshot.safety.order_submission_enabled,
            "cancel_enabled": snapshot.safety.cancel_enabled,
            "passorder_invoked": snapshot.safety.passorder_invoked,
            "cancel_invoked": snapshot.safety.cancel_invoked,
        },
        "failures": [failure(item) for item in snapshot.failures],
    }


def serialize_snapshot(snapshot: QmtBridgeSnapshot) -> str:
    """Return deterministic UTF-8 JSON text for audit fixtures and reports."""

    return json.dumps(
        snapshot_to_mapping(snapshot),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ) + "\n"
