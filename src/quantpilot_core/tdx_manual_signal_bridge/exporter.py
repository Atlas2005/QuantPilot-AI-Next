"""Signal exporter that reads latest_report.json and state.json to produce per-symbol TDX signals."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from quantpilot_core.tdx_manual_signal_bridge.contracts import (
    TDX_SIGNAL_CSV_HEADER,
    TdxSignal,
    TdxSignalAction,
)

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")

# ---------------------------------------------------------------------------
# Canonical field extraction helpers
# ---------------------------------------------------------------------------


def _str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    try:
        return bool(value)
    except Exception:
        return default


# ---------------------------------------------------------------------------
# Report / state loading
# ---------------------------------------------------------------------------


def load_report(path: str) -> Mapping[str, Any]:
    import json

    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def load_state(path: str) -> Mapping[str, Any]:
    import json

    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


# ---------------------------------------------------------------------------
# Candidate extraction from report
# ---------------------------------------------------------------------------


def _candidates_from_report(report: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Extract candidate list from report, trying multiple paths."""
    # Primary: quant_firm_input_candidate_report
    qf = report.get("quant_firm_input_candidate_report", {})
    if isinstance(qf, Mapping) and qf.get("candidates"):
        return list(qf["candidates"])

    # Fallback: candidate_report
    cr = report.get("candidate_report", {})
    if isinstance(cr, Mapping) and cr.get("candidates"):
        return list(cr["candidates"])

    return []


def _candidate_by_symbol(candidates: list[Mapping[str, Any]]) -> Mapping[str, Mapping[str, Any]]:
    return {str(c["symbol"]): c for c in candidates if c.get("symbol")}


def _quant_firm_actions(report: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    actions = report.get("quant_firm_candidate_actions", ())
    if isinstance(actions, (list, tuple)):
        return list(actions)
    return []


# ---------------------------------------------------------------------------
# Position context from state / ledger_after
# ---------------------------------------------------------------------------


def _ledger_after(report: Mapping[str, Any]) -> Mapping[str, Any]:
    return dict(report.get("ledger_after", {}) or {})


def _positions_from_ledger(ledger: Mapping[str, Any]) -> dict[str, int]:
    raw = ledger.get("positions", {})
    return {str(k): int(v) for k, v in dict(raw).items() if int(v) > 0}


def _average_costs_from_ledger(ledger: Mapping[str, Any]) -> dict[str, float]:
    raw = ledger.get("average_costs", {})
    return {str(k): _float(v) for k, v in dict(raw).items()}


def _sellable_from_ledger(ledger: Mapping[str, Any]) -> dict[str, int]:
    raw = ledger.get("sellable_quantities", ledger.get("sellable_quantities_as_of", {}))
    return {str(k): int(v) for k, v in dict(raw).items()}


def _settlement_lots_from_ledger(ledger: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list(ledger.get("settlement_lots", ()) or ())


def _positions_from_state(state: Mapping[str, Any]) -> dict[str, int]:
    es = state.get("execution_state", {})
    account = es.get("account", {})
    raw = account.get("positions", {})
    return {str(k): int(v) for k, v in dict(raw).items() if int(v) > 0}


def _average_costs_from_state(state: Mapping[str, Any]) -> dict[str, float]:
    es = state.get("execution_state", {})
    account = es.get("account", {})
    raw = account.get("average_costs", {})
    return {str(k): _float(v) for k, v in dict(raw).items()}


def _sellable_from_state(state: Mapping[str, Any], decision_session: str) -> dict[str, int]:
    """Compute sellable quantities from settlement lots given decision_session."""
    es = state.get("execution_state", {})
    lots = es.get("settlement_lots", ())
    result: dict[str, int] = {}
    for lot in lots:
        symbol = str(lot["symbol"])
        if lot.get("acquisition_date", "") < decision_session:
            result[symbol] = result.get(symbol, 0) + int(lot["quantity"])
    return result


# ---------------------------------------------------------------------------
# Signal assembly
# ---------------------------------------------------------------------------


def _resolve_action(
    symbol: str,
    candidate: Mapping[str, Any] | None,
    position_quantity: int,
    t1_sellable: bool,
    sellable_quantity: int,
) -> str:
    """Determine TdxSignalAction from candidate + position state.

    Rules (exhaustive):
      - No position + long candidate  → BUY
      - No position + no candidate   → NONE
      - No position + non-long       → NONE
      - Has position + no candidate  → HOLD
      - Has position + long          → HOLD  (already holding)
      - Has position + short/exit + any sellable  → SELL
      - Has position + short/exit + fully locked   → HOLD
      - No position must NEVER SELL
    Partial T+1 sellability: if the position has 300 shares but only 200
    are sellable, SELL is emitted.  The trader must consult sellable_quantity
    and position_state for the actual amount they can sell.
    """
    # No position — can never SELL
    if position_quantity <= 0:
        if candidate is not None and str(candidate.get("direction", "")).strip().lower() == "long":
            return TdxSignalAction.BUY.value
        return TdxSignalAction.NONE.value

    # Has position
    if candidate is None:
        # Holding without a current candidate: signal HOLD to maintain awareness
        return TdxSignalAction.HOLD.value

    direction = str(candidate.get("direction", "")).strip().lower()
    metadata = dict(candidate.get("metadata", {}) or {})

    # Check for exit signal
    exit_signal = (
        direction == "short"
        or metadata.get("exit_signal") is True
        or str(metadata.get("action", "")).strip().lower() in {"sell", "exit"}
        or str(metadata.get("decision_action", "")).strip().lower() in {"sell", "exit"}
    )

    if exit_signal:
        # SELL when ANY shares are sellable.  The actual sellable quantity
        # may be less than the total position (partial T+1 lock), but the
        # trader can still act on the sellable portion.
        if sellable_quantity > 0:
            return TdxSignalAction.SELL.value
        # Fully T+1 locked: HOLD until at least one lot settles
        return TdxSignalAction.HOLD.value

    # Holding with a long candidate or no exit signal → HOLD
    return TdxSignalAction.HOLD.value


def _position_state(
    position_quantity: int,
    sellable_quantity: int,
) -> str:
    """Position state: no_position | holding | t1_locked.

    'holding' means at least some shares are sellable (may still have
    a locked portion).  't1_locked' means zero shares are sellable.
    """
    if position_quantity <= 0:
        return "no_position"
    if sellable_quantity > 0:
        return "holding"
    return "t1_locked"


def _holding_period_sessions(
    symbol: str,
    settlement_lots: list[Mapping[str, Any]],
    decision_session: str,
) -> int:
    """Count sessions since first acquisition lot for this symbol."""
    if not settlement_lots:
        return 0
    earliest: str | None = None
    for lot in settlement_lots:
        if str(lot.get("symbol", "")) != symbol:
            continue
        acq = str(lot.get("acquisition_date", ""))
        if acq and acq < "9999-00-00":
            if earliest is None or acq < earliest:
                earliest = acq
    if earliest is None or decision_session <= earliest:
        return 0
    # Approximate sessions: calendar days / 1.4 ≈ trading sessions
    try:
        from datetime import date

        d0 = date.fromisoformat(earliest)
        d1 = date.fromisoformat(decision_session[:10])
        calendar_days = (d1 - d0).days
        return max(0, int(calendar_days * 0.7))  # ~5/7 trading days ratio
    except (ValueError, TypeError):
        return 0


def _evidence_refs(candidate: Mapping[str, Any] | None, quant_actions: list[Mapping[str, Any]], symbol: str) -> tuple[str, ...]:
    refs: list[str] = []
    if candidate is not None:
        cid = str(candidate.get("metadata", {}).get("candidate_id", candidate.get("symbol", "")))
        if cid:
            refs.append(f"candidate:{cid}")
    for action in quant_actions:
        if str(action.get("symbol", "")) == symbol:
            refs.append(f"quant_firm_action:{action.get('action', action.get('side', ''))}")
    return tuple(refs)


def _factor_metrics(candidate: Mapping[str, Any] | None) -> tuple[float, int, float, float, float]:
    """Extract factor rank, composite score, risk, liquidity from candidate metadata."""
    if candidate is None:
        return (0.0, 0, 0.0, 0.0, 0.0)

    metadata = dict(candidate.get("metadata", {}) or {})
    confidence = _float(candidate.get("confidence"), 0.0)
    risk = _float(candidate.get("risk_score"), 0.0)
    liquidity = _float(candidate.get("liquidity_score"), 0.0)

    factor_rank = _int(metadata.get("factor_rank"), 0)
    factor_composite = _float(
        metadata.get("factor_composite_score_raw", metadata.get("factor_composite_score")),
        0.0,
    )

    return (confidence, factor_rank, factor_composite, risk, liquidity)


def _is_stale(generated_at: str, max_age_seconds: float | None) -> bool:
    """Check if generated_at is older than max_age_seconds.

    Only generated_at (not data_asof) is used for staleness.
    data_asof is for session/calendar validity — a signal with an old
    decision_session but a freshly-regenerated timestamp is never stale.

    Uses Asia/Shanghai timezone for now.
    """
    if max_age_seconds is None:
        return False
    try:
        gen = _to_shanghai_datetime(generated_at)
        now = datetime.now(SHANGHAI_TZ)
        age = (now - gen).total_seconds()
        return age > max_age_seconds
    except (ValueError, TypeError):
        return False


def _to_shanghai_datetime(iso_string: str) -> datetime:
    """Parse an ISO datetime or date string to an Asia/Shanghai-aware datetime."""
    try:
        dt = datetime.fromisoformat(iso_string)
    except ValueError:
        # Try date-only parse
        from datetime import date as date_cls

        dt = datetime.combine(date_cls.fromisoformat(iso_string[:10]), datetime.min.time())
    if dt.tzinfo is None:
        # Treat naive strings as Asia/Shanghai
        dt = dt.replace(tzinfo=SHANGHAI_TZ)
    else:
        # Convert any aware datetime to Shanghai for consistent comparison
        dt = dt.astimezone(SHANGHAI_TZ)
    return dt


def _decision_session(report: Mapping[str, Any]) -> str:
    return str(report.get("decision_session", report.get("state", {}).get("decision_session", "")))


def _model_version(report: Mapping[str, Any]) -> str:
    candidate_id = str(
        report.get("production_candidate_id", report.get("effective_strategy_candidate_id", ""))
    )
    version = str(report.get("production_candidate_version", ""))
    if candidate_id and version:
        return f"{candidate_id}:{version}"
    loop_version = str(report.get("loop_version", ""))
    return loop_version or "unknown"


# ---------------------------------------------------------------------------
# Main export entry point
# ---------------------------------------------------------------------------


def export_signals(
    report: Mapping[str, Any],
    state: Mapping[str, Any] | None = None,
    *,
    max_age_seconds: float | None = None,
) -> list[TdxSignal]:
    """Produce one TdxSignal per unique symbol across candidates and holdings.

    Args:
        report: Parsed latest_report.json content.
        state: Parsed state.json content (optional; falls back to ledger_after in report).
        max_age_seconds: If set, signals whose generated_at is older than this
            many seconds are marked stale.
    """
    decision_session = _decision_session(report)
    candidates = _candidates_from_report(report)
    by_symbol = _candidate_by_symbol(candidates)
    quant_actions = _quant_firm_actions(report)
    ledger = _ledger_after(report)
    generated_at = datetime.now(SHANGHAI_TZ).isoformat()

    # Position data: prefer state.json → fall back to ledger_after in report
    if state is not None:
        positions = _positions_from_state(state)
        average_costs = _average_costs_from_state(state)
        sellable = _sellable_from_state(state, decision_session)
    else:
        positions = _positions_from_ledger(ledger)
        average_costs = _average_costs_from_ledger(ledger)
        sellable = _sellable_from_ledger(ledger)

    settlement_lots = _settlement_lots_from_ledger(ledger)

    # Union of all symbols: candidates + holdings
    all_symbols: set[str] = set(by_symbol.keys()) | set(positions.keys())

    model_version = _model_version(report)
    signals: list[TdxSignal] = []

    for symbol in sorted(all_symbols):
        candidate = by_symbol.get(symbol)
        position_quantity = positions.get(symbol, 0)
        sellable_quantity = sellable.get(symbol, 0)
        avg_cost = average_costs.get(symbol, 0.0)
        # t1_sellable: true when ANY shares can be sold (partial sellability).
        # TDX formulas use position_state_code for the full lock status.
        t1_sellable = sellable_quantity > 0 if position_quantity > 0 else False

        action = _resolve_action(symbol, candidate, position_quantity, t1_sellable, sellable_quantity)
        pos_state = _position_state(position_quantity, sellable_quantity)
        holding_sessions = _holding_period_sessions(symbol, settlement_lots, decision_session)
        evidence_refs = _evidence_refs(candidate, quant_actions, symbol)
        confidence, factor_rank, factor_composite, risk, liquidity = _factor_metrics(candidate)

        # Validity logic
        data_asof = decision_session
        signal_stale = _is_stale(generated_at, max_age_seconds)

        invalid_reason = ""
        signal_valid = True

        # A signal is invalid only if there is neither a candidate nor a position
        if candidate is None and position_quantity <= 0:
            signal_valid = False
            invalid_reason = "no_candidate_no_position"

        if signal_stale:
            invalid_reason = _join_reason(invalid_reason, "stale_signal")

        signals.append(
            TdxSignal(
                symbol=symbol,
                decision_session=decision_session,
                generated_at=generated_at,
                data_asof=data_asof,
                model_version=model_version,
                signal_valid=signal_valid,
                signal_stale=signal_stale,
                invalid_reason=invalid_reason,
                action=action,
                candidate_confidence=round(confidence, 4),
                factor_rank=factor_rank,
                factor_composite_score_raw=round(factor_composite, 6),
                risk_score=round(risk, 4),
                liquidity_score=round(liquidity, 4),
                position_state=pos_state,
                current_quantity=position_quantity,
                average_cost=round(avg_cost, 4),
                holding_period_sessions=holding_sessions,
                t1_sellable=t1_sellable,
                evidence_refs=evidence_refs,
            )
        )

    return signals


def _join_reason(existing: str, new: str) -> str:
    if not existing:
        return new
    return f"{existing}; {new}"


def signal_to_row(signal: TdxSignal) -> tuple[str, ...]:
    """Convert a TdxSignal to a CSV row tuple matching TDX_SIGNAL_CSV_HEADER."""
    return (
        signal.symbol,
        signal.decision_session,
        signal.generated_at,
        signal.data_asof,
        signal.model_version,
        str(signal.signal_valid).lower(),
        str(signal.signal_stale).lower(),
        signal.invalid_reason,
        signal.action,
        str(signal.candidate_confidence),
        str(signal.factor_rank),
        str(signal.factor_composite_score_raw),
        str(signal.risk_score),
        str(signal.liquidity_score),
        signal.position_state,
        str(signal.current_quantity),
        str(signal.average_cost),
        str(signal.holding_period_sessions),
        str(signal.t1_sellable).lower(),
        "|".join(signal.evidence_refs) if signal.evidence_refs else "",
    )


def signal_to_dict(signal: TdxSignal) -> dict[str, Any]:
    """Convert a TdxSignal to a JSON-serializable dict."""
    return {
        "symbol": signal.symbol,
        "decision_session": signal.decision_session,
        "generated_at": signal.generated_at,
        "data_asof": signal.data_asof,
        "model_version": signal.model_version,
        "signal_valid": signal.signal_valid,
        "signal_stale": signal.signal_stale,
        "invalid_reason": signal.invalid_reason,
        "action": signal.action,
        "candidate_confidence": signal.candidate_confidence,
        "factor_rank": signal.factor_rank,
        "factor_composite_score_raw": signal.factor_composite_score_raw,
        "risk_score": signal.risk_score,
        "liquidity_score": signal.liquidity_score,
        "position_state": signal.position_state,
        "current_quantity": signal.current_quantity,
        "average_cost": signal.average_cost,
        "holding_period_sessions": signal.holding_period_sessions,
        "t1_sellable": signal.t1_sellable,
        "evidence_refs": list(signal.evidence_refs),
    }
