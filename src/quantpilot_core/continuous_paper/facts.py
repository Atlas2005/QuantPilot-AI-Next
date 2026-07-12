"""Extract source facts from a daily-paper report without recalculation."""
from __future__ import annotations

from typing import Any, Mapping

from .store import payload_digest


FACT_TABLES = ("paper_orders", "paper_fills", "paper_positions", "paper_equity_curve", "paper_reconciliation")


def extract_daily_report_facts(report: Mapping[str, Any]) -> dict[str, tuple[Mapping[str, Any], ...]]:
    session_id = str(report["session_id"])
    orders = tuple(_row(session_id, item, "order_id", index) for index, item in enumerate(_items(report.get("order_intents", report.get("orders", ())))))
    fills = tuple(_row(session_id, item, "fill_id", index) for index, item in enumerate(_items(report.get("fills", ()))))
    ledger = _mapping(report.get("ledger_after"))
    positions = tuple(
        _row(session_id, {"symbol": symbol, "quantity": quantity}, "symbol", index)
        for index, (symbol, quantity) in enumerate(sorted(_mapping(ledger.get("positions")).items()))
    )
    equity_source = report.get("equity_curve", report.get("equity"))
    equity = tuple(_row(session_id, item, "timestamp", index) for index, item in enumerate(_items(equity_source)))
    if not equity and isinstance(equity_source, Mapping):
        equity = (_row(session_id, equity_source, "session_id", 0),)
    reconciliation_source = report.get("reconciliation_audit", report.get("reconciliation"))
    reconciliation = tuple(_row(session_id, item, "reconciliation_id", index) for index, item in enumerate(_items(reconciliation_source)))
    if not reconciliation and isinstance(reconciliation_source, Mapping):
        reconciliation = (_row(session_id, reconciliation_source, "session_id", 0),)
    return {"paper_orders": orders, "paper_fills": fills, "paper_positions": positions, "paper_equity_curve": equity, "paper_reconciliation": reconciliation}


def _items(value: Any) -> tuple[Mapping[str, Any], ...]:
    if isinstance(value, Mapping):
        return (dict(value),)
    return tuple(dict(item) for item in (value or ()) if isinstance(item, Mapping))


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _row(session_id: str, source: Mapping[str, Any], preferred_identity: str, index: int) -> Mapping[str, Any]:
    payload = dict(source)
    identity = payload.get(preferred_identity) or payload.get("order_id") or payload.get("fill_id")
    if identity is None:
        identity = payload.get("symbol") or payload.get("timestamp") or payload_digest(payload)[:16]
    return {"session_id": session_id, "source_identity": str(identity), "source_index": index, "payload": payload, "payload_digest": payload_digest(payload)}
