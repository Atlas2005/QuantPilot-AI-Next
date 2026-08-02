"""Shared TQCenter formula-data publisher used by the CLI and live shadow."""

from __future__ import annotations

import json
import platform
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from quantpilot_core.real_data_provider import canonicalize_tdx_level1_symbol


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")

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
PREDICTION_STATE_LABEL_ZH = {
    "ENTRY": "买",
    "HOLD": "持",
    "WEAKENING": "弱",
    "EXIT": "卖",
    "INVALIDATED": "失效",
}

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


def signal_to_tq_row(signal: Mapping[str, Any]) -> list[Any]:
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
    candidate_flag = 1 if action in {"BUY", "HOLD", "SELL"} else 0
    buy_signal = 1 if action == "BUY" and signal_valid and not signal_stale else 0
    sell_signal = (
        1
        if action == "SELL" and signal_valid and not signal_stale and t1_sellable
        else 0
    )
    return [
        signal_valid,
        candidate_flag,
        ACTION_CODE.get(action, 0),
        int(round(confidence * 100)),
        _float_val(signal.get("factor_composite_score_raw")),
        _int_val(signal.get("factor_rank")),
        int(round(risk * 100)),
        int(round(liquidity * 100)),
        POSITION_STATE_CODE.get(position_state, 0),
        t1_sellable,
        _int_val(signal.get("current_quantity")),
        _float_val(signal.get("average_cost")),
        _int_val(signal.get("holding_period_sessions")),
        0 if signal_stale else 1,
        buy_signal,
        sell_signal,
    ]


def prediction_signal_to_tq_row(signal: Mapping[str, Any]) -> list[Any]:
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


signal_to_tq_columns = signal_to_tq_row


def signal_timestamp(signal: Mapping[str, Any]) -> str:
    value = str(signal.get("generated_at") or signal.get("timestamp") or "")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        parsed = datetime.now(SHANGHAI_TZ)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=SHANGHAI_TZ)
    else:
        parsed = parsed.astimezone(SHANGHAI_TZ)
    return parsed.strftime("%Y%m%d%H%M%S")


def build_tq_time_list(signals: Sequence[Mapping[str, Any]]) -> list[str]:
    return [signal_timestamp(signal) for signal in signals]


def build_tq_data_lists(signals: Sequence[Mapping[str, Any]]) -> list[list[str]]:
    """Build official TQ row-major records, one string row per timestamp."""

    rows = [
        [_protocol_numeric_string(value) for value in signal_to_tq_row(signal)]
        for signal in signals
    ]
    if any(len(row) != len(TQ_COLUMN_SPEC) for row in rows):
        raise ValueError(
            f"every QuantPilot TQ row must contain exactly {len(TQ_COLUMN_SPEC)} columns"
        )
    return rows


def build_tq_send_payload(
    symbol: str,
    signals: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return the exact keyword payload accepted by ``tq.send_bt_data``."""

    if not signals:
        raise ValueError("signals must contain at least one record")
    canonical_symbol = canonicalize_tdx_level1_symbol(symbol)
    ordered = sorted(signals, key=signal_timestamp)
    time_list = build_tq_time_list(ordered)
    data_list = build_tq_data_lists(ordered)
    if not data_list:
        raise ValueError("TQ payload must contain at least one timestamp record")
    payload = {
        "stock_code": canonical_symbol,
        "time_list": time_list,
        "data_list": data_list,
        "count": len(time_list),
    }
    validate_tq_send_payload(payload, expected_column_count=len(TQ_COLUMN_SPEC))
    return payload


def validate_tq_send_payload(
    payload: Mapping[str, Any],
    *,
    expected_column_count: int,
) -> None:
    """Reject any non-official shape or non-string scalar before TQ is called."""

    time_list = payload.get("time_list")
    data_list = payload.get("data_list")
    count = payload.get("count")
    if not isinstance(time_list, list) or not all(
        isinstance(value, str) for value in time_list
    ):
        raise ValueError("TQ time_list must be a list of timestamp strings")
    if not isinstance(data_list, list) or len(data_list) != len(time_list):
        raise ValueError("TQ data_list must contain exactly one row per timestamp")
    if isinstance(count, bool) or not isinstance(count, int) or count != len(time_list):
        raise ValueError("TQ count must equal the number of timestamp records")
    for row in data_list:
        if not isinstance(row, list) or len(row) != expected_column_count:
            raise ValueError(
                f"every TQ row must contain exactly {expected_column_count} signal columns"
            )
        for value in row:
            if not isinstance(value, str):
                raise TypeError("every TQ scalar must be a numeric string")
            _validate_numeric_string(value)


def normalize_tq_response(raw: Any) -> dict[str, Any]:
    """Normalize a TQ JSON/mapping result without treating it as chart proof."""

    value = raw
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError as exc:
            return {
                "accepted": False,
                "error_type": type(exc).__name__,
                "sanitized_error": "TQ response is not valid UTF-8",
            }
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            return {
                "accepted": False,
                "error_type": type(exc).__name__,
                "sanitized_error": "TQ response is not valid JSON",
            }
    if value is False:
        return {
            "accepted": False,
            "error_type": "ExplicitFalseResponse",
            "sanitized_error": "TQ returned False",
        }
    if value is None:
        return {"accepted": None, "response_type": "NoneType"}
    if not isinstance(value, Mapping):
        return {
            "accepted": False,
            "error_type": "UnexpectedResponseType",
            "sanitized_error": f"unexpected TQ response type: {type(value).__name__}",
        }
    error_id = value.get("ErrorId", value.get("error_id"))
    accepted = str(error_id).strip() in {"0", "0.0"} if error_id is not None else None
    result: dict[str, Any] = {
        "accepted": accepted,
        "error_id": error_id,
        "message": _sanitize_text(value.get("Msg", value.get("message", ""))),
    }
    run_id = value.get("run_id", value.get("RunId"))
    if run_id is not None:
        result["run_id"] = run_id
    if accepted is False:
        result["error_type"] = "TQApiError"
        result["sanitized_error"] = result["message"] or f"TQ ErrorId={error_id}"
    return result


def publish_to_tq(
    signals: Sequence[Mapping[str, Any]],
    *,
    tdx_plugin_dir: str | None = None,
    dry_run: bool = False,
    manage_tq_lifecycle: bool = True,
    platform_name: str | None = None,
) -> Mapping[str, Any]:
    """Publish through the supported 16-column TQ API without any order call."""

    del tdx_plugin_dir  # TQ configuration remains environment-owned.
    runtime_platform = platform_name or platform.system()
    if not dry_run and runtime_platform != "Windows":
        raise RuntimeError(
            "TQ publishing is only supported on Windows. "
            "Use --dry-run to preview the payload on this platform."
        )
    by_symbol: dict[str, list[Mapping[str, Any]]] = {}
    for signal in signals:
        symbol = canonicalize_tdx_level1_symbol(signal.get("symbol", ""))
        by_symbol.setdefault(symbol, []).append(signal)
    if dry_run:
        sample_rows = [
            {
                "symbol": symbol,
                "timestamp": signal_timestamp(signal),
                "row": signal_to_tq_row(signal),
            }
            for symbol, rows in sorted(by_symbol.items())
            for signal in rows
        ]
        prediction_schema = bool(signals) and all(
            signal.get("schema_version") == "tdx_prediction_signal_v1"
            for signal in signals
        )
        column_spec = PREDICTION_TQ_COLUMN_SPEC if prediction_schema else TQ_COLUMN_SPEC
        return {
            "dry_run": True,
            "platform": runtime_platform,
            "signal_count": len(signals),
            "symbol_count": len(by_symbol),
            "symbols": sorted(by_symbol),
            "sample_rows": sample_rows[:5],
            "column_spec": {column: name for column, name, _ in column_spec},
            "prediction_state_labels_zh": dict(PREDICTION_STATE_LABEL_ZH),
            "visible_marker_policy": "lifecycle_state_transitions_only",
            "data_orientation": "row_major_by_timestamp",
            "count_semantics": "timestamp_record_count",
            "ordinary_chart_overlay_status": "not_exercised_dry_run",
        }
    try:
        from tqcenter import tq  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "tqcenter (天勤) is not installed. "
            "Install the TDX TQ plugin package before live publishing."
        ) from exc
    symbol_count = 0
    row_count = 0
    responses: list[dict[str, Any]] = []
    try:
        if manage_tq_lifecycle:
            tq.initialize(__file__)
        for symbol, rows in sorted(by_symbol.items()):
            payload = build_tq_send_payload(symbol, rows)
            raw_response = tq.send_bt_data(**payload)
            response = normalize_tq_response(raw_response)
            response["symbol"] = symbol
            responses.append(response)
            if response.get("accepted") is False:
                raise RuntimeError(
                    "TQ send_bt_data rejected the payload: "
                    f"{response.get('sanitized_error', 'unknown TQ error')}"
                )
            symbol_count += 1
            row_count += len(payload["time_list"])
    finally:
        if manage_tq_lifecycle:
            tq.close()
    return {
        "dry_run": False,
        "platform": runtime_platform,
        "symbol_count": symbol_count,
        "row_count": row_count,
        "manage_tq_lifecycle": manage_tq_lifecycle,
        "visible_marker_policy": "lifecycle_state_transitions_only",
        "data_orientation": "row_major_by_timestamp",
        "count_semantics": "timestamp_record_count",
        "transport_responses": responses,
        "transport_accepted": bool(responses) and all(
            response.get("accepted") is True for response in responses
        ),
        "ordinary_chart_overlay_status": "pending_windows_visual_confirmation",
    }


def _protocol_numeric_string(value: Any) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        converted = Decimal(str(value))
        if not converted.is_finite():
            raise ValueError("TQ signal values must be finite")
        return format(converted, "f")
    if isinstance(value, str):
        _validate_numeric_string(value)
        return value
    raise TypeError("TQ signal values must be numeric strings or numeric primitives")


def _validate_numeric_string(value: str) -> None:
    if not value or value.strip() != value:
        raise ValueError("TQ numeric strings must be non-empty and unpadded")
    try:
        converted = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("TQ scalar is not a numeric string") from exc
    if not converted.is_finite():
        raise ValueError("TQ numeric strings must be finite")


def _sanitize_text(value: Any) -> str:
    return " ".join(str(value or "").split())[:500]


def _bool_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
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
