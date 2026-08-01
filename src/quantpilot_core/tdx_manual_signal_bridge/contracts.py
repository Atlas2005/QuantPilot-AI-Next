"""Contracts for the TDX manual signal bridge.

This module defines TdxSignalAction (NONE, BUY, HOLD, SELL) and the
per-symbol TdxSignal data contract.  It does NOT add INVALID to any core
order or agent action enum — invalidity is expressed through
signal_valid=False and invalid_reason.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class TdxSignalAction(str, Enum):
    """TDX-facing signal action.

    These four values are the ONLY actions this bridge emits.
    INVALID does not exist here — stale or missing signals use
    signal_valid=False plus invalid_reason instead.
    """

    NONE = "NONE"
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"


@dataclass(frozen=True)
class TdxSignal:
    """One per-symbol signal emitted by the TDX manual signal bridge.

    Every field maps to one column in the exported CSV / one key in the
    JSON record.  Consumers (TDX formulas) must treat action as advisory
    only — QuantPilot does NOT claim it is a verified 15-minute precise
    entry/exit point.
    """

    symbol: str
    decision_session: str
    generated_at: str
    data_asof: str
    model_version: str

    # -- validity -----------------------------------------------------------
    signal_valid: bool
    signal_stale: bool
    invalid_reason: str

    # -- action -------------------------------------------------------------
    action: str  # one of TdxSignalAction values

    # -- candidate metrics --------------------------------------------------
    candidate_confidence: float
    factor_rank: int
    factor_composite_score_raw: float
    risk_score: float
    liquidity_score: float

    # -- position context ---------------------------------------------------
    position_state: str  # "no_position" | "holding" | "t1_locked"
    current_quantity: int
    average_cost: float
    holding_period_sessions: int
    t1_sellable: bool

    # -- provenance ---------------------------------------------------------
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)


TDX_SIGNAL_CSV_HEADER: tuple[str, ...] = (
    "symbol",
    "decision_session",
    "generated_at",
    "data_asof",
    "model_version",
    "signal_valid",
    "signal_stale",
    "invalid_reason",
    "action",
    "candidate_confidence",
    "factor_rank",
    "factor_composite_score_raw",
    "risk_score",
    "liquidity_score",
    "position_state",
    "current_quantity",
    "average_cost",
    "holding_period_sessions",
    "t1_sellable",
    "evidence_refs",
)
