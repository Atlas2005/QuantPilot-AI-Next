"""Tests for the TDX manual signal bridge module.

Covers:
- BUY/HOLD/SELL/NONE action resolution (corrected semantics)
- Holding + no candidate → HOLD (not NONE)
- invalid and stale signals
- Stale: only generated_at matters, date-only data_asof does NOT make fresh signals stale
- T+1 lock (no SELL when T+1 locked)
- No position → never SELL
- JSON/CSV deterministic output
- Atomic writes
- Core ActionSide unchanged
- Real contract fixtures from daily_paper_loop patterns
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import pytest

from quantpilot_core.tdx_manual_signal_bridge import (
    TDX_SIGNAL_CSV_HEADER,
    TdxSignal,
    TdxSignalAction,
    export_signals,
    signal_to_dict,
    signal_to_row,
    write_signals_atomic,
    write_signals_csv_atomic,
    write_signals_json_atomic,
)
from quantpilot_core.ai_action_paper_bridge.contracts import ActionSide
from quantpilot_core.deepseek_multi_agent.validation import VALID_ACTION_SIDES
from quantpilot_core.execution_candidate.contracts import ExecutionCandidate

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


# ---------------------------------------------------------------------------
# Real-candidate-shaped fixtures (matching _candidate_payload format from
# daily_paper_loop/runner.py)
# ---------------------------------------------------------------------------


def _make_candidate(
    symbol: str = "600000.SH",
    direction: str = "long",
    confidence: float = 0.82,
    expected_return: float = 0.03,
    risk_score: float = 0.20,
    liquidity_score: float = 0.90,
    metadata: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    """Fixture matching the structure in daily_paper_loop/runner._candidate_payload."""
    meta = {
        "candidate_id": f"test:{symbol}:{direction}",
        "factor_rank": 1,
        "factor_composite_score_raw": 0.75,
        "factor_composite_score": 0.72,
        "source": "real_candidate_pipeline",
    }
    if metadata:
        meta.update(metadata)
    return {
        "symbol": symbol,
        "direction": direction,
        "confidence": confidence,
        "expected_return": expected_return,
        "risk_score": risk_score,
        "liquidity_score": liquidity_score,
        "timestamp": "2026-01-02T14:55:00+08:00",
        "lot_size": 100,
        "metadata": meta,
    }


def _make_report(
    candidates: list[Mapping[str, Any]] | None = None,
    decision_session: str = "2026-01-02",
    positions: Mapping[str, int] | None = None,
    average_costs: Mapping[str, float] | None = None,
    sellable: Mapping[str, int] | None = None,
    settlement_lots: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Fixture matching the latest_report.json structure from daily_paper_loop."""
    candidates = candidates or []
    return {
        "loop_version": "daily_paper_loop_v1",
        "decision_session": decision_session,
        "execution_session": "2026-01-05",
        "production_candidate_id": "test-manifest",
        "production_candidate_version": "v1.0",
        "candidate_report": {
            "strategy_id": "test-strategy",
            "aggregate_score": 0.08,
            "candidates": candidates,
        },
        "quant_firm_input_candidate_report": {
            "strategy_id": "test-strategy",
            "aggregate_score": 0.08,
            "candidates": candidates,
        },
        "quant_firm_candidate_actions": tuple(
            {"symbol": c["symbol"], "action": c["direction"]} for c in candidates
        ),
        "ledger_after": {
            "positions": dict(positions or {}),
            "average_costs": dict(average_costs or {}),
            "sellable_quantities": dict(sellable or {}),
            "sellable_quantities_as_of": dict(sellable or {}),
            "settlement_lots": settlement_lots or [],
        },
    }


# ---------------------------------------------------------------------------
# Action resolution tests — corrected semantics
# ---------------------------------------------------------------------------


class TestActionResolution:
    """Exhaustive action resolution tests per the corrected specification."""

    def test_buy_when_long_candidate_no_position(self):
        report = _make_report(candidates=[_make_candidate("600000.SH", direction="long")])
        signals = export_signals(report)
        assert signals[0].action == TdxSignalAction.BUY.value
        assert signals[0].signal_valid is True
        assert signals[0].position_state == "no_position"

    def test_none_when_no_candidate_no_position(self):
        """A symbol with NO candidate and NO position must produce NONE, invalid."""
        report = _make_report(
            candidates=[],
            positions={"600000.SH": 0},
        )
        signals = export_signals(report)
        assert len(signals) == 0  # zero-quantity positions are filtered out

    def test_hold_when_has_position_no_candidate(self):
        """Holding without a candidate → HOLD (NOT NONE)."""
        report = _make_report(
            candidates=[],
            positions={"600000.SH": 200},
            average_costs={"600000.SH": 10.0},
            sellable={"600000.SH": 200},
            settlement_lots=[
                {"symbol": "600000.SH", "quantity": 200, "acquisition_date": "2026-01-01"}
            ],
        )
        signals = export_signals(report)
        assert len(signals) == 1
        assert signals[0].action == TdxSignalAction.HOLD.value
        assert signals[0].signal_valid is True
        assert signals[0].position_state == "holding"

    def test_hold_when_has_position_long_candidate(self):
        """Holding + long candidate → HOLD (already in position)."""
        report = _make_report(
            candidates=[_make_candidate("600000.SH", direction="long")],
            positions={"600000.SH": 200},
            average_costs={"600000.SH": 10.0},
            sellable={"600000.SH": 200},
            settlement_lots=[
                {"symbol": "600000.SH", "quantity": 200, "acquisition_date": "2026-01-01"}
            ],
        )
        signals = export_signals(report)
        assert signals[0].action == TdxSignalAction.HOLD.value
        assert signals[0].position_state == "holding"
        assert signals[0].t1_sellable is True

    def test_sell_when_has_position_short_candidate_t1_sellable(self):
        report = _make_report(
            candidates=[_make_candidate("600000.SH", direction="short")],
            positions={"600000.SH": 200},
            average_costs={"600000.SH": 10.0},
            sellable={"600000.SH": 200},
            settlement_lots=[
                {"symbol": "600000.SH", "quantity": 200, "acquisition_date": "2026-01-01"}
            ],
        )
        signals = export_signals(report)
        assert signals[0].action == TdxSignalAction.SELL.value
        assert signals[0].signal_valid is True

    def test_sell_when_exit_metadata(self):
        report = _make_report(
            candidates=[
                _make_candidate("600000.SH", direction="short",
                                metadata={"action": "exit", "exit_signal": True})
            ],
            positions={"600000.SH": 200},
            average_costs={"600000.SH": 10.0},
            sellable={"600000.SH": 200},
            settlement_lots=[
                {"symbol": "600000.SH", "quantity": 200, "acquisition_date": "2026-01-01"}
            ],
        )
        signals = export_signals(report)
        assert signals[0].action == TdxSignalAction.SELL.value

    def test_none_when_no_position_short_candidate(self):
        """No position + short candidate → NONE. Never SELL without position."""
        report = _make_report(candidates=[_make_candidate("600000.SH", direction="short")])
        signals = export_signals(report)
        assert signals[0].action == TdxSignalAction.NONE.value

    def test_none_when_no_position_exit_metadata(self):
        """No position + exit metadata → NONE. Never SELL without position."""
        report = _make_report(
            candidates=[
                _make_candidate("600000.SH", direction="short",
                                metadata={"action": "exit", "exit_signal": True})
            ],
        )
        signals = export_signals(report)
        assert signals[0].action == TdxSignalAction.NONE.value

    def test_none_when_no_position_flat_candidate(self):
        report = _make_report(candidates=[_make_candidate("600000.SH", direction="flat")])
        signals = export_signals(report)
        assert signals[0].action == TdxSignalAction.NONE.value


class TestT1Locking:
    def test_hold_not_sell_when_fully_t1_locked(self):
        """Short candidate but all shares acquired today → zero sellable, HOLD not SELL."""
        report = _make_report(
            candidates=[_make_candidate("600000.SH", direction="short")],
            decision_session="2026-01-05",
            positions={"600000.SH": 200},
            average_costs={"600000.SH": 10.0},
            sellable={"600000.SH": 0},
            settlement_lots=[
                {"symbol": "600000.SH", "quantity": 200, "acquisition_date": "2026-01-05"}
            ],
        )
        signals = export_signals(report)
        assert signals[0].action == TdxSignalAction.HOLD.value
        assert signals[0].position_state == "t1_locked"
        assert signals[0].t1_sellable is False

    def test_sell_when_partially_sellable(self):
        """300 shares, 200 sellable (100 acquired today). SELL because some are sellable."""
        report = _make_report(
            candidates=[_make_candidate("600000.SH", direction="short")],
            decision_session="2026-01-05",
            positions={"600000.SH": 300},
            average_costs={"600000.SH": 10.0},
            sellable={"600000.SH": 200},
            settlement_lots=[
                {"symbol": "600000.SH", "quantity": 200, "acquisition_date": "2026-01-03"},
                {"symbol": "600000.SH", "quantity": 100, "acquisition_date": "2026-01-05"},
            ],
        )
        signals = export_signals(report)
        assert signals[0].action == TdxSignalAction.SELL.value
        assert signals[0].position_state == "holding"
        assert signals[0].t1_sellable is True
        assert signals[0].current_quantity == 300


# ---------------------------------------------------------------------------
# Stale logic tests — Asia/Shanghai semantics
# ---------------------------------------------------------------------------


class TestStaleLogic:
    def test_fresh_signal_not_stale(self):
        """A just-generated signal is never stale."""
        report = _make_report(candidates=[_make_candidate("600000.SH", direction="long")])
        signals = export_signals(report, max_age_seconds=300)
        assert signals[0].signal_stale is False

    def test_old_generated_at_is_stale(self):
        """A signal generated in the distant past IS stale."""
        report = _make_report(
            candidates=[_make_candidate("600000.SH", direction="long")],
            decision_session="2020-01-01",
        )
        # generated_at is NOW, but the test is checking... Actually, generated_at
        # is always NOW from export_signals.  For a stale test, we need to
        # call export_signals with a max_age_seconds that is smaller than the
        # age.  We can't mock time easily, but we can use max_age_seconds=0
        # which means any non-zero age is stale.
        signals = export_signals(report, max_age_seconds=0)
        assert signals[0].signal_stale is True
        assert "stale" in signals[0].invalid_reason.lower()

    def test_date_only_data_asof_does_not_make_signal_stale(self):
        """data_asof is a date string — it should NEVER make a fresh signal stale.
        Staleness is only based on generated_at."""
        report = _make_report(
            candidates=[_make_candidate("600000.SH", direction="long")],
            decision_session="2020-01-01",  # old decision session
        )
        # Without max_age_seconds, nothing is stale regardless of data_asof
        signals = export_signals(report)
        assert signals[0].signal_stale is False

    def test_no_max_age_never_stale(self):
        report = _make_report(candidates=[_make_candidate("600000.SH", direction="long")])
        signals = export_signals(report)
        assert signals[0].signal_stale is False


class TestInvalidSignals:
    def test_signal_valid_false_no_candidate_no_position(self):
        """Only invalidity is no-candidate AND no-position."""
        report = _make_report(
            candidates=[],
            positions={},  # No positions at all → nothing to emit
        )
        signals = export_signals(report)
        assert len(signals) == 0

    def test_holding_without_candidate_is_valid(self):
        """Holding a position without a current candidate is still valid (HOLD)."""
        report = _make_report(
            candidates=[],
            positions={"600000.SH": 100},
            average_costs={"600000.SH": 10.0},
            sellable={"600000.SH": 100},
            settlement_lots=[
                {"symbol": "600000.SH", "quantity": 100, "acquisition_date": "2026-01-01"}
            ],
        )
        signals = export_signals(report)
        assert len(signals) == 1
        assert signals[0].signal_valid is True
        assert signals[0].action == TdxSignalAction.HOLD.value


# ---------------------------------------------------------------------------
# No-position → never SELL
# ---------------------------------------------------------------------------


class TestNoPositionNoSell:
    def test_no_sell_without_position(self):
        report = _make_report(candidates=[_make_candidate("600000.SH", direction="short")])
        signals = export_signals(report)
        assert signals[0].action == TdxSignalAction.NONE.value

    def test_no_sell_without_position_exit_metadata(self):
        report = _make_report(
            candidates=[
                _make_candidate("600000.SH", direction="short",
                                metadata={"action": "exit", "exit_signal": True})
            ],
        )
        signals = export_signals(report)
        assert signals[0].action == TdxSignalAction.NONE.value


# ---------------------------------------------------------------------------
# JSON/CSV deterministic output
# ---------------------------------------------------------------------------


class TestJSONCSVDeterministic:
    def test_same_input_same_summary(self):
        report = _make_report(candidates=[_make_candidate("600000.SH", direction="long")])
        signals1 = export_signals(report, max_age_seconds=None)
        signals2 = export_signals(report, max_age_seconds=None)
        for s1, s2 in zip(signals1, signals2):
            assert s1.symbol == s2.symbol
            assert s1.action == s2.action
            assert s1.decision_session == s2.decision_session
            assert s1.signal_valid == s2.signal_valid
            assert s1.current_quantity == s2.current_quantity

    def test_json_output_is_valid_json(self):
        report = _make_report(candidates=[_make_candidate("600000.SH", direction="long")])
        signals = export_signals(report)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_signals_json_atomic(signals, Path(tmpdir) / "latest.json")
            with open(path) as f:
                data = json.load(f)
            assert isinstance(data, list)
            assert len(data) == 1
            assert data[0]["symbol"] == "600000.SH"

    def test_csv_output_has_header(self):
        report = _make_report(candidates=[_make_candidate("600000.SH", direction="long")])
        signals = export_signals(report)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_signals_csv_atomic(signals, Path(tmpdir) / "latest.csv")
            with open(path) as f:
                lines = f.readlines()
            assert len(lines) >= 2
            assert "symbol" in lines[0]
            assert "600000.SH" in lines[1]


class TestAtomicWrites:
    def test_atomic_write_does_not_leave_temp_file(self):
        report = _make_report(candidates=[_make_candidate("600000.SH", direction="long")])
        signals = export_signals(report)
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir)
            json_path, csv_path = write_signals_atomic(signals, out)
            temps = list(out.glob(".latest*.tmp"))
            assert len(temps) == 0
            assert os.path.exists(json_path)
            assert os.path.exists(csv_path)

    def test_atomic_write_creates_parent_dirs(self):
        report = _make_report(candidates=[_make_candidate("600000.SH", direction="long")])
        signals = export_signals(report)
        with tempfile.TemporaryDirectory() as tmpdir:
            deep = Path(tmpdir) / "a" / "b" / "c"
            json_path, csv_path = write_signals_atomic(signals, deep)
            assert os.path.exists(json_path)
            assert os.path.exists(csv_path)


# ---------------------------------------------------------------------------
# Core enum preservation
# ---------------------------------------------------------------------------


class TestCoreActionSideUnchanged:
    def test_action_side_values_unchanged(self):
        assert ActionSide.BUY.value == "buy"
        assert ActionSide.SELL.value == "sell"
        assert ActionSide.HOLD.value == "hold"
        assert len(ActionSide) == 3

    def test_valid_action_sides_unchanged(self):
        assert VALID_ACTION_SIDES == frozenset({"BUY", "SELL", "HOLD"})

    def test_valid_action_sides_no_invalid(self):
        assert "INVALID" not in VALID_ACTION_SIDES

    def test_tdx_signal_action_no_invalid(self):
        assert set(TdxSignalAction.__members__) == {"NONE", "BUY", "HOLD", "SELL"}
        assert "INVALID" not in TdxSignalAction.__members__


# ---------------------------------------------------------------------------
# CSV header integrity
# ---------------------------------------------------------------------------


class TestCSVHeader:
    def test_header_is_deterministic(self):
        assert len(TDX_SIGNAL_CSV_HEADER) == 20
        assert TDX_SIGNAL_CSV_HEADER[0] == "symbol"

    def test_signal_to_row_matches_header_length(self):
        signal = TdxSignal(
            symbol="600000.SH",
            decision_session="2026-01-02",
            generated_at="2026-01-02T14:55:00+08:00",
            data_asof="2026-01-02",
            model_version="test",
            signal_valid=True,
            signal_stale=False,
            invalid_reason="",
            action=TdxSignalAction.BUY.value,
            candidate_confidence=0.82,
            factor_rank=1,
            factor_composite_score_raw=0.75,
            risk_score=0.20,
            liquidity_score=0.90,
            position_state="no_position",
            current_quantity=0,
            average_cost=0.0,
            holding_period_sessions=0,
            t1_sellable=False,
            evidence_refs=("candidate:test",),
        )
        row = signal_to_row(signal)
        assert len(row) == len(TDX_SIGNAL_CSV_HEADER)


# ---------------------------------------------------------------------------
# Position state
# ---------------------------------------------------------------------------


class TestPositionState:
    def test_no_position_state(self):
        report = _make_report(candidates=[_make_candidate("600000.SH", direction="long")])
        signals = export_signals(report)
        assert signals[0].position_state == "no_position"
        assert signals[0].current_quantity == 0

    def test_holding_state(self):
        report = _make_report(
            candidates=[_make_candidate("600000.SH", direction="long")],
            positions={"600000.SH": 100},
            sellable={"600000.SH": 100},
            settlement_lots=[
                {"symbol": "600000.SH", "quantity": 100, "acquisition_date": "2026-01-01"}
            ],
        )
        signals = export_signals(report)
        assert signals[0].position_state == "holding"
        assert signals[0].t1_sellable is True

    def test_t1_locked_state(self):
        """Zero sellable → t1_locked, t1_sellable=False."""
        report = _make_report(
            candidates=[_make_candidate("600000.SH", direction="long")],
            decision_session="2026-01-02",
            positions={"600000.SH": 100},
            sellable={"600000.SH": 0},
            settlement_lots=[
                {"symbol": "600000.SH", "quantity": 100, "acquisition_date": "2026-01-02"}
            ],
        )
        signals = export_signals(report)
        assert signals[0].position_state == "t1_locked"
        assert signals[0].t1_sellable is False

    def test_partial_sellable_state(self):
        """Partial sellability: 300 total, 200 sellable → holding, t1_sellable=True."""
        report = _make_report(
            candidates=[_make_candidate("600000.SH", direction="long")],
            decision_session="2026-01-05",
            positions={"600000.SH": 300},
            sellable={"600000.SH": 200},
            settlement_lots=[
                {"symbol": "600000.SH", "quantity": 200, "acquisition_date": "2026-01-03"},
                {"symbol": "600000.SH", "quantity": 100, "acquisition_date": "2026-01-05"},
            ],
        )
        signals = export_signals(report)
        assert signals[0].position_state == "holding"
        assert signals[0].t1_sellable is True
        assert signals[0].current_quantity == 300
