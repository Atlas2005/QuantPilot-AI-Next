"""Versioned state serialization and atomic persistence for the daily paper loop."""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from quantpilot_core.a_share_market_reality_execution import AShareExecutionAccountState, SettlementLot
from quantpilot_core.daily_paper_loop.contracts import DAILY_LOOP_SCHEMA_VERSION, DailyPaperStateError
from quantpilot_core.paper_trading import PaperAccount, PaperTrade


@dataclass(frozen=True)
class DailyPaperLoopState:
    """Durable wrapper around existing paper account and A-share execution state."""

    schema_version: int
    initial_capital: float
    execution_state: AShareExecutionAccountState
    applied_sessions: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    last_completed_session: str | None = None
    last_decision_session: str | None = None
    last_execution_session: str | None = None
    prior_state_hash: str | None = None
    state_hash: str | None = None


def initialize_daily_state(initial_capital: float) -> DailyPaperLoopState:
    if initial_capital <= 0 or not math.isfinite(float(initial_capital)):
        raise DailyPaperStateError("initial_capital must be positive and finite")
    account = PaperAccount(cash=round(float(initial_capital), 6))
    state = DailyPaperLoopState(
        schema_version=DAILY_LOOP_SCHEMA_VERSION,
        initial_capital=round(float(initial_capital), 6),
        execution_state=AShareExecutionAccountState(account=account),
        applied_sessions={},
    )
    return _with_hash(state)


def load_daily_state(path: str | Path, *, initial_capital: float) -> DailyPaperLoopState:
    state_path = Path(path)
    if not state_path.exists():
        return initialize_daily_state(initial_capital)
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DailyPaperStateError("daily paper state is not valid JSON") from exc
    state = state_from_payload(payload)
    expected = _payload_hash(_state_payload(state, include_hash=False))
    if state.state_hash != expected:
        raise DailyPaperStateError("daily paper state hash mismatch")
    if round(float(state.initial_capital), 6) != round(float(initial_capital), 6):
        raise DailyPaperStateError("initial_capital mismatch with existing daily paper state")
    return state


def save_daily_state_atomic(state: DailyPaperLoopState, path: str | Path) -> DailyPaperLoopState:
    hashed = _with_hash(state)
    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json(_state_payload(hashed, include_hash=True))
    temp_path = state_path.with_name(f".{state_path.name}.tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        handle.write(payload)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, state_path)
    return hashed


def state_to_payload(state: DailyPaperLoopState) -> Mapping[str, Any]:
    return _state_payload(state, include_hash=True)


def state_from_payload(payload: Mapping[str, Any]) -> DailyPaperLoopState:
    if not isinstance(payload, Mapping):
        raise DailyPaperStateError("daily paper state payload must be a mapping")
    version = int(payload.get("schema_version", -1))
    if version != DAILY_LOOP_SCHEMA_VERSION:
        raise DailyPaperStateError(f"unsupported daily paper state schema_version: {version}")
    execution_state = execution_state_from_payload(payload.get("execution_state", {}))
    state = DailyPaperLoopState(
        schema_version=version,
        initial_capital=_finite_float(payload.get("initial_capital"), "initial_capital"),
        execution_state=execution_state,
        applied_sessions=dict(payload.get("applied_sessions", {}) or {}),
        last_completed_session=payload.get("last_completed_session"),
        last_decision_session=payload.get("last_decision_session"),
        last_execution_session=payload.get("last_execution_session"),
        prior_state_hash=payload.get("prior_state_hash"),
        state_hash=payload.get("state_hash"),
    )
    _validate_state(state)
    return state


def replace_state_hash(state: DailyPaperLoopState, prior_state_hash: str | None = None) -> DailyPaperLoopState:
    return _with_hash(
        DailyPaperLoopState(
            schema_version=state.schema_version,
            initial_capital=state.initial_capital,
            execution_state=state.execution_state,
            applied_sessions=state.applied_sessions,
            last_completed_session=state.last_completed_session,
            last_decision_session=state.last_decision_session,
            last_execution_session=state.last_execution_session,
            prior_state_hash=prior_state_hash if prior_state_hash is not None else state.prior_state_hash,
        )
    )


def canonical_json(value: Any) -> str:
    return json.dumps(_json_ready(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def payload_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def account_to_payload(account: PaperAccount) -> Mapping[str, Any]:
    return {
        "cash": round(float(account.cash), 6),
        "positions": {symbol: int(quantity) for symbol, quantity in sorted(account.positions.items())},
        "average_costs": {symbol: round(float(value), 6) for symbol, value in sorted(account.average_costs.items())},
        "realized_pnl_by_symbol": {
            symbol: round(float(value), 6)
            for symbol, value in sorted(account.realized_pnl_by_symbol.items())
        },
        "realized_pnl": round(float(account.realized_pnl), 6),
        "unrealized_pnl": round(float(account.unrealized_pnl), 6),
        "trade_log": tuple(_trade_payload(trade) for trade in account.trade_log),
    }


def account_from_payload(payload: Mapping[str, Any]) -> PaperAccount:
    return PaperAccount(
        cash=_finite_float(payload.get("cash", 0.0), "account.cash"),
        positions={str(symbol): int(quantity) for symbol, quantity in dict(payload.get("positions", {}) or {}).items()},
        average_costs={
            str(symbol): _finite_float(value, f"average_costs.{symbol}")
            for symbol, value in dict(payload.get("average_costs", {}) or {}).items()
        },
        realized_pnl_by_symbol={
            str(symbol): _finite_float(value, f"realized_pnl_by_symbol.{symbol}")
            for symbol, value in dict(payload.get("realized_pnl_by_symbol", {}) or {}).items()
        },
        realized_pnl=_finite_float(payload.get("realized_pnl", 0.0), "realized_pnl"),
        unrealized_pnl=_finite_float(payload.get("unrealized_pnl", 0.0), "unrealized_pnl"),
        trade_log=tuple(_trade_from_payload(row) for row in tuple(payload.get("trade_log", ()) or ())),
    )


def execution_state_to_payload(state: AShareExecutionAccountState) -> Mapping[str, Any]:
    return {
        "account": account_to_payload(state.account),
        "settlement_lots": tuple(
            {
                "symbol": lot.symbol,
                "quantity": int(lot.quantity),
                "acquisition_date": lot.acquisition_date,
            }
            for lot in state.settlement_lots
        ),
        "frozen_cash": round(float(state.frozen_cash), 6),
        "seen_order_ids": tuple(sorted(state.seen_order_ids)),
    }


def execution_state_from_payload(payload: Any) -> AShareExecutionAccountState:
    if not isinstance(payload, Mapping):
        raise DailyPaperStateError("execution_state must be a mapping")
    account = account_from_payload(dict(payload.get("account", {}) or {}))
    lots = tuple(
        SettlementLot(
            symbol=str(row["symbol"]),
            quantity=int(row["quantity"]),
            acquisition_date=str(row["acquisition_date"]),
        )
        for row in tuple(payload.get("settlement_lots", ()) or ())
    )
    state = AShareExecutionAccountState(
        account=account,
        settlement_lots=lots,
        frozen_cash=_finite_float(payload.get("frozen_cash", 0.0), "frozen_cash"),
        seen_order_ids=frozenset(str(value) for value in tuple(payload.get("seen_order_ids", ()) or ())),
    )
    _validate_execution_state(state)
    return state


def snapshot_from_execution_state(
    state: AShareExecutionAccountState,
    valuation_prices: Mapping[str, float] | None = None,
    *,
    as_of_session: str | None = None,
    next_session: str | None = None,
) -> Mapping[str, Any]:
    prices = valuation_prices or {}
    positions = {symbol: int(quantity) for symbol, quantity in sorted(state.account.positions.items())}
    missing_prices = tuple(symbol for symbol, quantity in positions.items() if int(quantity) > 0 and symbol not in prices)
    if missing_prices:
        raise DailyPaperStateError(f"missing valuation prices for held symbols: {missing_prices}")
    market_value = round(
        sum(quantity * float(prices[symbol]) for symbol, quantity in positions.items()),
        6,
    )
    equity = round(float(state.account.cash) + market_value, 6)
    sellable_as_of = _sellable_by_symbol(state.settlement_lots, as_of_session=as_of_session)
    sellable_next = _sellable_by_symbol(state.settlement_lots, as_of_session=next_session)
    unsettled = {
        symbol: int(quantity) - int(sellable_as_of.get(symbol, 0))
        for symbol, quantity in positions.items()
        if int(quantity) - int(sellable_as_of.get(symbol, 0)) > 0
    }
    return {
        "cash": round(float(state.account.cash), 6),
        "frozen_cash": round(float(state.frozen_cash), 6),
        "positions": positions,
        "sellable_as_of_session": as_of_session,
        "sellable_next_session": next_session,
        "sellable_quantities": sellable_as_of,
        "sellable_quantities_as_of": sellable_as_of,
        "sellable_quantities_next_session": sellable_next,
        "unsettled_quantities": dict(sorted(unsettled.items())),
        "average_costs": dict(sorted(account_to_payload(state.account)["average_costs"].items())),
        "realized_pnl": round(float(state.account.realized_pnl), 6),
        "realized_pnl_by_symbol": dict(sorted(account_to_payload(state.account)["realized_pnl_by_symbol"].items())),
        "unrealized_pnl": round(float(state.account.unrealized_pnl), 6),
        "market_value": market_value,
        "total_equity": equity,
        "settlement_lots": execution_state_to_payload(state)["settlement_lots"],
        "seen_order_ids": tuple(sorted(state.seen_order_ids)),
        "trade_log_count": len(state.account.trade_log),
    }


def _state_payload(state: DailyPaperLoopState, *, include_hash: bool) -> Mapping[str, Any]:
    payload = {
        "schema_version": int(state.schema_version),
        "initial_capital": round(float(state.initial_capital), 6),
        "execution_state": execution_state_to_payload(state.execution_state),
        "applied_sessions": dict(sorted(state.applied_sessions.items())),
        "last_completed_session": state.last_completed_session,
        "last_decision_session": state.last_decision_session,
        "last_execution_session": state.last_execution_session,
        "prior_state_hash": state.prior_state_hash,
    }
    if include_hash:
        payload["state_hash"] = state.state_hash
    return payload


def _with_hash(state: DailyPaperLoopState) -> DailyPaperLoopState:
    _validate_state(state)
    digest = _payload_hash(_state_payload(state, include_hash=False))
    return DailyPaperLoopState(
        schema_version=state.schema_version,
        initial_capital=state.initial_capital,
        execution_state=state.execution_state,
        applied_sessions=dict(state.applied_sessions),
        last_completed_session=state.last_completed_session,
        last_decision_session=state.last_decision_session,
        last_execution_session=state.last_execution_session,
        prior_state_hash=state.prior_state_hash,
        state_hash=digest,
    )


def _payload_hash(payload: Mapping[str, Any]) -> str:
    return payload_digest(payload)


def _validate_state(state: DailyPaperLoopState) -> None:
    if state.schema_version != DAILY_LOOP_SCHEMA_VERSION:
        raise DailyPaperStateError("unsupported daily paper state schema version")
    if state.initial_capital <= 0 or not math.isfinite(float(state.initial_capital)):
        raise DailyPaperStateError("initial capital must be positive and finite")
    _validate_execution_state(state.execution_state)


def _validate_execution_state(state: AShareExecutionAccountState) -> None:
    account = state.account
    if not math.isfinite(float(account.cash)):
        raise DailyPaperStateError("account cash must be finite")
    if not math.isfinite(float(state.frozen_cash)) or state.frozen_cash < 0:
        raise DailyPaperStateError("frozen cash must be finite and non-negative")
    for symbol, quantity in account.positions.items():
        if int(quantity) < 0:
            raise DailyPaperStateError(f"position quantity cannot be negative: {symbol}")
    lot_totals: dict[str, int] = {}
    for lot in state.settlement_lots:
        if int(lot.quantity) <= 0:
            raise DailyPaperStateError("settlement lot quantity must be positive")
        lot_totals[lot.symbol] = lot_totals.get(lot.symbol, 0) + int(lot.quantity)
    for symbol, lot_quantity in lot_totals.items():
        if symbol not in account.positions:
            raise DailyPaperStateError(f"settlement lot exists without open position: {symbol}")
        if lot_quantity != int(account.positions.get(symbol, 0)):
            raise DailyPaperStateError(f"settlement lots must exactly match position quantity: {symbol}")
    for symbol, quantity in account.positions.items():
        if int(quantity) > 0 and lot_totals.get(symbol, 0) != int(quantity):
            raise DailyPaperStateError(f"settlement lots must exactly match position quantity: {symbol}")
    for symbol in account.average_costs:
        if symbol not in account.positions:
            raise DailyPaperStateError(f"average cost exists without open position: {symbol}")


def _sellable_by_symbol(lots: tuple[SettlementLot, ...], *, as_of_session: str | None = None) -> Mapping[str, int]:
    values: dict[str, int] = {}
    for lot in lots:
        if as_of_session is not None and lot.acquisition_date >= as_of_session:
            continue
        values[lot.symbol] = values.get(lot.symbol, 0) + int(lot.quantity)
    return dict(sorted(values.items()))


def _finite_float(value: Any, field_name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise DailyPaperStateError(f"{field_name} must be numeric") from exc
    if not math.isfinite(result):
        raise DailyPaperStateError(f"{field_name} must be finite")
    return round(result, 6)


def _trade_payload(trade: Any) -> Mapping[str, Any]:
    return {
        "symbol": trade.symbol,
        "side": trade.side,
        "quantity": int(trade.quantity),
        "reference_price": round(float(trade.reference_price), 6),
        "fill_price": round(float(trade.fill_price), 6),
        "gross_notional": round(float(trade.gross_notional), 6),
        "fee": round(float(trade.fee), 6),
        "slippage_cost": round(float(trade.slippage_cost), 6),
        "total_cost": round(float(trade.total_cost), 6),
        "cash_impact": round(float(trade.cash_impact), 6),
        "realized_pnl": round(float(trade.realized_pnl), 6),
        "reason": trade.reason,
        "source_agent": trade.source_agent,
        "metadata": dict(trade.metadata),
    }


def _trade_from_payload(payload: Mapping[str, Any]) -> PaperTrade:
    return PaperTrade(
        symbol=str(payload["symbol"]),
        side=str(payload["side"]),
        quantity=int(payload["quantity"]),
        reference_price=_finite_float(payload.get("reference_price"), "trade.reference_price"),
        fill_price=_finite_float(payload.get("fill_price"), "trade.fill_price"),
        gross_notional=_finite_float(payload.get("gross_notional"), "trade.gross_notional"),
        fee=_finite_float(payload.get("fee"), "trade.fee"),
        slippage_cost=_finite_float(payload.get("slippage_cost"), "trade.slippage_cost"),
        total_cost=_finite_float(payload.get("total_cost"), "trade.total_cost"),
        cash_impact=_finite_float(payload.get("cash_impact"), "trade.cash_impact"),
        realized_pnl=_finite_float(payload.get("realized_pnl"), "trade.realized_pnl"),
        reason=str(payload.get("reason", "")),
        source_agent=str(payload.get("source_agent", "")),
        metadata=dict(payload.get("metadata", {}) or {}),
    )


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_json_ready(item) for item in value]
    if hasattr(value, "value"):
        return value.value
    return value
