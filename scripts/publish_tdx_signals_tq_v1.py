#!/usr/bin/env python3
"""Publish QuantPilot signals to TDX via the TQCenter (天勤) extension interface.

This script reads latest.json (produced by export_tdx_manual_signals_v1.py)
and publishes the signal columns to TDX through tq.send_bt_data().

**Per-symbol send_bt_data**: each stock_code gets its own call with
row-major data_list (each inner list = one time point = [ID1, …, ID16]).

Critical safety properties:
- Read-only: never calls order_stock, cancel_order, or any trading API.
- Non-Windows: refuses to run unless --dry-run is used.
- tqcenter is imported lazily inside the publish function so tests can mock.
- Maximum 16 data columns per TQ protocol.

TQ Column ID Mapping (16 columns, each row = one timestamp):
    1  signal_valid           (bool → 1/0)
    2  candidate_flag         (bool → 1/0: has active candidate)
    3  action_code            (int: NONE=0, BUY=1, HOLD=2, SELL=3)
    4  confidence_pct         (int: candidate_confidence * 100)
    5  factor_score_raw       (float: factor_composite_score_raw)
    6  factor_rank            (int)
    7  risk_pct               (int: risk_score * 100)
    8  liquidity_pct          (int: liquidity_score * 100)
    9  position_state_code    (int: no_position=0, holding=1, t1_locked=2)
    10 t1_sellable            (bool → 1/0)
    11 current_quantity        (int)
    12 average_cost            (float)
    13 holding_period_sessions (int)
    14 freshness_valid        (bool → 1/0: not stale)
    15 buy_signal             (bool → 1/0)
    16 sell_signal            (bool → 1/0)

buy_signal  = action==BUY AND signal_valid AND NOT signal_stale
sell_signal = action==SELL AND signal_valid AND NOT signal_stale AND t1_sellable

Prediction records with schema_version=tdx_prediction_signal_v1 use the same
16-column transport with state/probability/zone/target fields. String reason
codes and full evidence provenance remain in the adjacent atomic JSON/CSV
artifacts because send_bt_data transports numeric formula columns.

Usage:
    # Dry-run (works on any OS):
    python scripts/publish_tdx_signals_tq_v1.py \\
        --from-signals .cache/tdx_signals/latest.json \\
        --dry-run

    # Windows live publish:
    python scripts/publish_tdx_signals_tq_v1.py \\
        --from-signals .cache/tdx_signals/latest.json \\
        --tdx-plugin-dir "D:\\TDX\\T0002\\dlls"
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")

# ---------------------------------------------------------------------------
# Action code and position-state mappings
# ---------------------------------------------------------------------------

ACTION_CODE = {"NONE": 0, "BUY": 1, "HOLD": 2, "SELL": 3}
POSITION_STATE_CODE = {"no_position": 0, "holding": 1, "t1_locked": 2}
PREDICTION_STATE_CODE = {
    "WATCH": 0,
    "ENTRY": 1,
    "HOLD": 2,
    "WEAKENING": 3,
    "EXIT": 4,
    "INVALIDATED": 5,
}

# TQ column layout (1-indexed, max 16)
TQ_COLUMN_SPEC: tuple[tuple[int, str, str], ...] = (
    (1, "signal_valid", "bool"),
    (2, "candidate_flag", "bool"),
    (3, "action_code", "int"),
    (4, "confidence_pct", "int"),
    (5, "factor_score_raw", "float"),
    (6, "factor_rank", "int"),
    (7, "risk_pct", "int"),
    (8, "liquidity_pct", "int"),
    (9, "position_state_code", "int"),
    (10, "t1_sellable", "bool"),
    (11, "current_quantity", "int"),
    (12, "average_cost", "float"),
    (13, "holding_period_sessions", "int"),
    (14, "freshness_valid", "bool"),
    (15, "buy_signal", "bool"),
    (16, "sell_signal", "bool"),
)

PREDICTION_TQ_COLUMN_SPEC: tuple[tuple[int, str, str], ...] = (
    (1, "signal_valid", "bool"),
    (2, "prediction_state_code", "int"),
    (3, "entry_probability_pct", "int"),
    (4, "continuation_probability_pct", "int"),
    (5, "exit_probability_pct", "int"),
    (6, "expected_return_bps", "float"),
    (7, "entry_zone_low", "float"),
    (8, "entry_zone_high", "float"),
    (9, "invalidation_price", "float"),
    (10, "first_target_price", "float"),
    (11, "intraday_score", "float"),
    (12, "material_change", "bool"),
    (13, "entry_signal", "bool"),
    (14, "hold_signal", "bool"),
    (15, "weakening_signal", "bool"),
    (16, "exit_or_invalidated_signal", "bool"),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bool_int(value: Any) -> int:
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, str):
        return 1 if value.strip().lower() in {"true", "1", "yes"} else 0
    return 1 if value else 0


def _int_val(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float_val(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Signal → single TQ row (one timestamp for one symbol)
# ---------------------------------------------------------------------------


def signal_to_tq_row(signal: Mapping[str, Any]) -> list[Any]:
    """Convert one signal dict to a 16-element row for send_bt_data data_list.

    Each element position matches TQ_COLUMN_SPEC (1-indexed ID).
    """
    if signal.get("schema_version") == "tdx_prediction_signal_v1":
        return prediction_signal_to_tq_row(signal)
    action = str(signal.get("action", "NONE"))
    position_state = str(signal.get("position_state", "no_position"))
    confidence = _float_val(signal.get("candidate_confidence"))
    risk = _float_val(signal.get("risk_score"))
    liquidity = _float_val(signal.get("liquidity_score"))
    signal_valid = _bool_int(signal.get("signal_valid"))
    signal_stale = _bool_int(signal.get("signal_stale"))
    t1_sellable = _bool_int(signal.get("t1_sellable"))
    not_stale = 0 if signal_stale else 1
    candidate_flag = 1 if action in {"BUY", "HOLD", "SELL"} else 0

    # buy_signal: only when valid, not stale, and action is BUY
    buy_signal = 1 if (action == "BUY" and signal_valid and not signal_stale) else 0

    # sell_signal: only when valid, not stale, t1_sellable, and action is SELL
    sell_signal = 1 if (action == "SELL" and signal_valid and not signal_stale and t1_sellable) else 0

    return [
        signal_valid,                            #  1
        candidate_flag,                          #  2
        ACTION_CODE.get(action, 0),              #  3
        int(round(confidence * 100)),            #  4
        _float_val(signal.get("factor_composite_score_raw")),  #  5
        _int_val(signal.get("factor_rank")),     #  6
        int(round(risk * 100)),                  #  7
        int(round(liquidity * 100)),             #  8
        POSITION_STATE_CODE.get(position_state, 0),  #  9
        t1_sellable,                             # 10
        _int_val(signal.get("current_quantity")),  # 11
        _float_val(signal.get("average_cost")),  # 12
        _int_val(signal.get("holding_period_sessions")),  # 13
        not_stale,                               # 14
        buy_signal,                              # 15
        sell_signal,                             # 16
    ]


def prediction_signal_to_tq_row(signal: Mapping[str, Any]) -> list[Any]:
    """Map formula-ready prediction fields onto the existing 16-column TQ path."""

    state = str(signal.get("state", "WATCH")).upper()
    return [
        1,
        PREDICTION_STATE_CODE.get(state, 0),
        int(round(_float_val(signal.get("entry_probability")) * 100)),
        int(round(_float_val(signal.get("continuation_probability")) * 100)),
        int(round(_float_val(signal.get("exit_probability")) * 100)),
        round(_float_val(signal.get("expected_return")) * 10_000, 4),
        _float_val(signal.get("entry_zone_low")),
        _float_val(signal.get("entry_zone_high")),
        _float_val(signal.get("invalidation_price")),
        _float_val(signal.get("first_target_price")),
        _float_val(signal.get("intraday_score")),
        _bool_int(signal.get("material_change")),
        1 if state == "ENTRY" else 0,
        1 if state == "HOLD" else 0,
        1 if state == "WEAKENING" else 0,
        1 if state in {"EXIT", "INVALIDATED"} else 0,
    ]


def signal_timestamp(signal: Mapping[str, Any]) -> str:
    """Extract a "YYYYMMDDHHMMSS" timestamp from generated_at, falling back to now."""
    ts = str(signal.get("generated_at") or signal.get("timestamp") or "")
    try:
        dt = datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        dt = datetime.now(SHANGHAI_TZ)
    return dt.strftime("%Y%m%d%H%M%S")


def build_tq_time_list(signals: Sequence[Mapping[str, Any]]) -> list[str]:
    """Build time_list — one timestamp per signal."""
    return [signal_timestamp(s) for s in signals]


# Legacy alias for backward compat in tests
signal_to_tq_columns = signal_to_tq_row


def build_tq_data_lists(signals: Sequence[Mapping[str, Any]]) -> list[list[Any]]:
    """Build row-major data_list: each inner list is one row = [ID1, …, ID16]."""
    return [signal_to_tq_row(s) for s in signals]


# ---------------------------------------------------------------------------
# TQ publishing (lazy import of tqcenter)
# ---------------------------------------------------------------------------


def publish_to_tq(
    signals: Sequence[Mapping[str, Any]],
    *,
    tdx_plugin_dir: str | None = None,
    dry_run: bool = False,
) -> Mapping[str, Any]:
    """Publish signals to TDX via TQCenter.

    Each symbol gets its own tq.send_bt_data() call with row-major data_list.

    In dry-run mode, returns the payload that would be sent without
    importing tqcenter or touching any TDX installation.

    On non-Windows without --dry-run, raises RuntimeError.
    """
    if not dry_run and platform.system() != "Windows":
        raise RuntimeError(
            "TQ publishing is only supported on Windows. "
            "Use --dry-run to preview the payload on this platform."
        )

    # Group signals by symbol (each symbol gets one send_bt_data call)
    by_symbol: dict[str, list[Mapping[str, Any]]] = {}
    for sig in signals:
        sym = str(sig.get("symbol", ""))
        by_symbol.setdefault(sym, []).append(sig)

    if dry_run:
        sample_rows = []
        for sym, sigs in sorted(by_symbol.items()):
            for s in sigs:
                sample_rows.append({"symbol": sym, "timestamp": signal_timestamp(s), "row": signal_to_tq_row(s)})
        prediction_schema = bool(signals) and all(
            signal.get("schema_version") == "tdx_prediction_signal_v1"
            for signal in signals
        )
        column_spec = PREDICTION_TQ_COLUMN_SPEC if prediction_schema else TQ_COLUMN_SPEC
        return {
            "dry_run": True,
            "platform": platform.system(),
            "signal_count": len(signals),
            "symbol_count": len(by_symbol),
            "symbols": sorted(by_symbol.keys()),
            "sample_rows": sample_rows[:5],
            "column_spec": {col_id: name for col_id, name, _ in column_spec},
        }

    # -- LAZY import from tqcenter (only on Windows live path) --
    try:
        from tqcenter import tq  # type: ignore[import-untyped]
    except ImportError:
        raise RuntimeError(
            "tqcenter (天勤) is not installed. "
            "Install the TDX TQ plugin package before live publishing."
        )

    symbol_count = 0
    row_count = 0

    try:
        tq.initialize(__file__)
        for symbol, sigs in sorted(by_symbol.items()):
            time_list = [signal_timestamp(s) for s in sigs]
            # Row-major: each inner list = one timestamp row [ID1, …, ID16]
            data_list = [signal_to_tq_row(s) for s in sigs]
            count = len(time_list)

            tq.send_bt_data(
                stock_code=symbol,
                time_list=time_list,
                data_list=data_list,
                count=count,
            )
            symbol_count += 1
            row_count += count
    finally:
        tq.close()

    return {
        "dry_run": False,
        "platform": platform.system(),
        "symbol_count": symbol_count,
        "row_count": row_count,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Publish QuantPilot signals to TDX via TQCenter (天勤) extension.",
    )
    parser.add_argument(
        "--from-signals",
        required=True,
        help="Path to latest.json produced by export_tdx_manual_signals_v1.py.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the TQ payload without importing tqcenter or touching TDX.",
    )
    parser.add_argument(
        "--tdx-plugin-dir",
        default=None,
        help="TDX plugin directory (informational; actual TQ config is environment-based).",
    )
    args = parser.parse_args()

    signal_path = Path(args.from_signals)
    if not signal_path.exists():
        print(json.dumps({"status": "error", "message": f"signals file not found: {signal_path}"}))
        return 1

    with open(signal_path, encoding="utf-8") as handle:
        signals = json.load(handle)

    if not isinstance(signals, list):
        print(json.dumps({"status": "error", "message": "signals file must contain a JSON array"}))
        return 1

    try:
        result = publish_to_tq(
            signals,
            tdx_plugin_dir=args.tdx_plugin_dir,
            dry_run=args.dry_run,
        )
        print(json.dumps({"status": "ok", **result}, indent=2, ensure_ascii=False))
        return 0
    except RuntimeError as exc:
        print(json.dumps({"status": "error", "message": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
