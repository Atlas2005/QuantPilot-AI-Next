"""Tests for the publish_tdx_signals_tq_v1.py module.

Covers:
- Row-major data_list (each row = one timestamp = [ID1, …, ID16])
- Per-symbol send_bt_data
- tqcenter mock (not fictional tq module)
- buy_signal requires signal_valid + NOT signal_stale
- sell_signal requires signal_valid + NOT signal_stale + t1_sellable
- Order API never called
- Platform guard
- Dry-run
"""

from __future__ import annotations

import platform
import sys
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import scripts.publish_tdx_signals_tq_v1 as tq_module
from scripts.publish_tdx_signals_tq_v1 import (
    ACTION_CODE,
    POSITION_STATE_CODE,
    TQ_COLUMN_SPEC,
    build_tq_data_lists,
    build_tq_time_list,
    publish_to_tq,
    signal_to_tq_row,
    signal_to_tq_columns,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _signal(**overrides) -> dict[str, Any]:
    base = {
        "symbol": "600000.SH",
        "decision_session": "2026-01-02",
        "generated_at": "2026-01-02T14:55:00+08:00",
        "data_asof": "2026-01-02",
        "model_version": "test",
        "signal_valid": True,
        "signal_stale": False,
        "invalid_reason": "",
        "action": "BUY",
        "candidate_confidence": 0.82,
        "factor_rank": 1,
        "factor_composite_score_raw": 0.75,
        "risk_score": 0.20,
        "liquidity_score": 0.90,
        "position_state": "no_position",
        "current_quantity": 0,
        "average_cost": 0.0,
        "holding_period_sessions": 0,
        "t1_sellable": False,
        "evidence_refs": ["candidate:test"],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Row-major conversion tests
# ---------------------------------------------------------------------------


class TestSignalToTQRow:
    def test_buy_signal_row(self):
        row = signal_to_tq_row(_signal(action="BUY"))
        assert len(row) == 16
        assert row[0] == 1   # signal_valid
        assert row[1] == 1   # candidate_flag
        assert row[2] == 1   # BUY=1
        assert row[3] == 82  # confidence_pct
        assert row[14] == 1  # buy_signal
        assert row[15] == 0  # sell_signal

    def test_sell_signal_row(self):
        row = signal_to_tq_row(
            _signal(action="SELL", position_state="holding", current_quantity=200, t1_sellable=True)
        )
        assert row[2] == 3   # SELL=3
        assert row[8] == 1   # holding=1
        assert row[9] == 1   # t1_sellable
        assert row[10] == 200
        assert row[14] == 0  # not buy
        assert row[15] == 1  # sell

    def test_hold_signal_row(self):
        row = signal_to_tq_row(_signal(action="HOLD", position_state="holding"))
        assert row[2] == 2  # HOLD=2

    def test_none_signal_row(self):
        row = signal_to_tq_row(_signal(action="NONE"))
        assert row[2] == 0  # NONE=0
        assert row[1] == 0  # candidate_flag=0

    def test_invalid_no_buy_signal(self):
        """Invalid signal must NOT light buy_signal even if action=BUY."""
        row = signal_to_tq_row(_signal(action="BUY", signal_valid=False))
        assert row[14] == 0  # buy_signal off
        assert row[15] == 0  # sell_signal off

    def test_stale_no_buy_signal(self):
        """Stale signal must NOT light buy_signal even if action=BUY."""
        row = signal_to_tq_row(_signal(action="BUY", signal_stale=True))
        assert row[14] == 0  # buy_signal off
        assert row[13] == 0  # freshness_valid off

    def test_sell_signal_requires_t1_sellable(self):
        """sell_signal must be OFF when t1_sellable is false, even if action=SELL."""
        row = signal_to_tq_row(
            _signal(action="SELL", t1_sellable=False, position_state="t1_locked")
        )
        assert row[15] == 0  # sell_signal OFF despite SELL action

    def test_sell_signal_requires_not_stale(self):
        """Stale SELL must NOT light sell_signal."""
        row = signal_to_tq_row(
            _signal(action="SELL", signal_stale=True, t1_sellable=True, position_state="holding")
        )
        assert row[15] == 0

    def test_t1_locked_columns(self):
        row = signal_to_tq_row(
            _signal(action="HOLD", position_state="t1_locked", current_quantity=100, t1_sellable=False)
        )
        assert row[8] == 2  # t1_locked=2
        assert row[9] == 0  # not sellable


# ---------------------------------------------------------------------------
# Row-major data_list tests
# ---------------------------------------------------------------------------


class TestTQDataLists:
    def test_build_data_lists_row_major(self):
        """data_list is row-major: each inner list = one timestamp row."""
        signals = [_signal(action="BUY"), _signal(action="SELL", symbol="000001.SZ")]
        data_list = build_tq_data_lists(signals)
        assert len(data_list) == 2  # 2 rows (one per signal)
        assert len(data_list[0]) == 16  # each row has 16 columns
        assert len(data_list[1]) == 16
        # First row should be BUY
        assert data_list[0][2] == 1  # BUY

    def test_build_time_list(self):
        signals = [
            _signal(generated_at="2026-01-02T14:55:00+08:00"),
            _signal(generated_at="2026-01-02T14:56:00+08:00", symbol="000001.SZ"),
        ]
        time_list = build_tq_time_list(signals)
        assert len(time_list) == 2
        assert time_list[0] == "20260102145500"

    def test_build_time_list_fallback(self):
        signals = [_signal(generated_at="invalid")]
        time_list = build_tq_time_list(signals)
        assert len(time_list) == 1
        assert len(time_list[0]) == 14


class TestDeterministicOutput:
    def test_same_signal_same_row(self):
        assert signal_to_tq_row(_signal(action="BUY")) == signal_to_tq_row(_signal(action="BUY"))

    def test_same_signals_same_data_lists(self):
        signals = [_signal(action="BUY"), _signal(action="SELL", symbol="000001.SZ")]
        assert build_tq_data_lists(signals) == build_tq_data_lists(signals)


# ---------------------------------------------------------------------------
# Dry-run / platform tests
# ---------------------------------------------------------------------------


class TestDryRun:
    def test_dry_run_does_not_import_tq(self):
        result = publish_to_tq([_signal(action="BUY")], dry_run=True)
        assert result["dry_run"] is True
        assert result["signal_count"] == 1

    def test_dry_run_shows_symbols(self):
        result = publish_to_tq(
            [_signal(action="BUY"), _signal(action="SELL", symbol="000001.SZ")],
            dry_run=True,
        )
        assert result["symbol_count"] == 2
        assert "sample_rows" in result

    def test_live_on_non_windows_raises(self):
        if platform.system() != "Windows":
            with pytest.raises(RuntimeError, match="only supported on Windows"):
                publish_to_tq([_signal(action="BUY")], dry_run=False)


# ---------------------------------------------------------------------------
# tqcenter mock tests
# ---------------------------------------------------------------------------


class TestTQCenterMock:
    def test_per_symbol_send_bt_data(self):
        """Each stock_code gets its own send_bt_data call with row-major data_list."""
        mock_tqcenter = MagicMock()
        mock_tq = MagicMock()
        mock_tqcenter.tq = mock_tq

        signals = [
            _signal(action="BUY", symbol="600000.SH"),
            _signal(action="SELL", symbol="000001.SZ", t1_sellable=True, position_state="holding"),
        ]

        with patch.dict(sys.modules, {"tqcenter": mock_tqcenter}):
            with patch.object(tq_module, "platform") as mock_plat:
                mock_plat.system.return_value = "Windows"
                result = publish_to_tq(signals, dry_run=False)

        assert result["dry_run"] is False
        assert result["symbol_count"] == 2

        # tq.initialize was called
        mock_tq.initialize.assert_called_once()

        # tq.close was called
        mock_tq.close.assert_called_once()

        # send_bt_data called twice (once per symbol), sorted by symbol
        assert mock_tq.send_bt_data.call_count == 2

        # Extract calls by stock_code
        calls_by_symbol = {}
        for call in mock_tq.send_bt_data.call_args_list:
            code = call.kwargs["stock_code"]
            calls_by_symbol[code] = call.kwargs

        # 000001.SZ (sorted first)
        call_sz = calls_by_symbol["000001.SZ"]
        assert call_sz["count"] == 1
        assert call_sz["data_list"][0][2] == 3  # SELL

        # 600000.SH (sorted second)
        call_sh = calls_by_symbol["600000.SH"]
        assert call_sh["count"] == 1
        assert call_sh["data_list"][0][2] == 1  # BUY

    def test_no_order_api_called(self):
        """Verify that order_stock, cancel_order are NEVER called."""
        mock_tqcenter = MagicMock()
        mock_tq = MagicMock()
        mock_tqcenter.tq = mock_tq

        signals = [_signal(action="BUY")]

        with patch.dict(sys.modules, {"tqcenter": mock_tqcenter}):
            with patch.object(tq_module, "platform") as mock_plat:
                mock_plat.system.return_value = "Windows"
                publish_to_tq(signals, dry_run=False)

        # Only send_bt_data, initialize, close should be called
        assert mock_tq.send_bt_data.called
        assert not hasattr(mock_tq, "order_stock") or not mock_tq.order_stock.called
        assert not hasattr(mock_tq, "cancel_order") or not mock_tq.cancel_order.called

    def test_multiple_signals_same_symbol_single_call(self):
        """Multiple timestamps for the same symbol → single send_bt_data call."""
        mock_tqcenter = MagicMock()
        mock_tq = MagicMock()
        mock_tqcenter.tq = mock_tq

        signals = [
            _signal(action="BUY", symbol="600000.SH", generated_at="2026-01-02T14:55:00+08:00"),
            _signal(action="HOLD", symbol="600000.SH", generated_at="2026-01-02T14:56:00+08:00"),
        ]

        with patch.dict(sys.modules, {"tqcenter": mock_tqcenter}):
            with patch.object(tq_module, "platform") as mock_plat:
                mock_plat.system.return_value = "Windows"
                result = publish_to_tq(signals, dry_run=False)

        assert result["symbol_count"] == 1
        assert result["row_count"] == 2
        mock_tq.send_bt_data.assert_called_once()
        call = mock_tq.send_bt_data.call_args.kwargs
        assert call["count"] == 2
        assert len(call["data_list"]) == 2  # 2 rows


class TestTQColumnSpec:
    def test_16_columns(self):
        assert len(TQ_COLUMN_SPEC) == 16

    def test_ids_are_1_indexed_sequential(self):
        ids = [col_id for col_id, _, _ in TQ_COLUMN_SPEC]
        assert ids == list(range(1, 17))


class TestActionCodeMappings:
    def test_action_codes(self):
        assert ACTION_CODE == {"NONE": 0, "BUY": 1, "HOLD": 2, "SELL": 3}

    def test_position_state_codes(self):
        assert POSITION_STATE_CODE == {"no_position": 0, "holding": 1, "t1_locked": 2}
