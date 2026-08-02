"""Windows-only qualification probe for TQ ``SIGNALS_TQ`` chart data."""

from __future__ import annotations

import hashlib
import inspect
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from quantpilot_core.real_data_provider import canonicalize_tdx_level1_symbol
from quantpilot_core.tdx_manual_signal_bridge.tq_publisher import (
    normalize_tq_response,
    validate_tq_send_payload,
)


MINIMAL_FORMULA = "T1:SIGNALS_TQ(1,0);\nT2:SIGNALS_TQ(2,0);"
MINIMAL_VALUES: tuple[tuple[str, str], ...] = (
    ("11.51", "11.61"),
    ("11.52", "11.62"),
    ("11.53", "11.63"),
)
OFFICIAL_SHAPE_ROWS: tuple[tuple[str, ...], ...] = (
    ("1", "143.41", "200", "0", "0", "0"),
    ("0", "0", "0", "1", "143.48", "200"),
)
SMOKE_STATE_LABELS_ZH = ("买", "持", "弱", "卖", "失效")


def minute_timestamps(start: str, *, count: int = 7) -> list[str]:
    """Build consecutive TQ timestamps from a compact Shanghai wall-clock time."""

    parsed = datetime.strptime(start, "%Y%m%d%H%M%S")
    if parsed.second != 0:
        raise ValueError("start timestamp must be aligned to a whole minute")
    return [
        (parsed + timedelta(minutes=index)).strftime("%Y%m%d%H%M%S")
        for index in range(count)
    ]


def build_minimal_smoke_payload(
    symbol: str,
    timestamps: Sequence[str],
) -> dict[str, Any]:
    """Build a non-square three-timestamp/two-column orientation probe."""

    if len(timestamps) < 3:
        raise ValueError("minimal TQ smoke requires three timestamps")
    selected = [str(value) for value in timestamps[:3]]
    _validate_timestamps(selected)
    payload = {
        "stock_code": canonicalize_tdx_level1_symbol(symbol),
        "time_list": selected,
        "data_list": [list(row) for row in MINIMAL_VALUES],
        "count": 3,
    }
    validate_tq_send_payload(payload, expected_column_count=2)
    return payload


def build_official_shape_smoke_payload(
    symbol: str,
    timestamps: Sequence[str],
) -> dict[str, Any]:
    """Build the exact official two-timestamp/six-column example shape."""

    if len(timestamps) < 2:
        raise ValueError("official-shape TQ smoke requires two timestamps")
    selected = [str(value) for value in timestamps[:2]]
    _validate_timestamps(selected)
    payload = {
        "stock_code": canonicalize_tdx_level1_symbol(symbol),
        "time_list": selected,
        "data_list": [list(row) for row in OFFICIAL_SHAPE_ROWS],
        "count": 2,
    }
    validate_tq_send_payload(payload, expected_column_count=6)
    return payload


def build_quantpilot_smoke_payload(
    symbol: str,
    timestamps: Sequence[str],
) -> dict[str, Any]:
    """Build two neutral rows followed by five 16-column lifecycle states."""

    if len(timestamps) != 7:
        raise ValueError("QuantPilot TQ smoke requires exactly seven timestamps")
    selected = [str(value) for value in timestamps]
    _validate_timestamps(selected)
    rows = [
        ["0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0"],
        ["0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0"],
        ["1", "1", "72", "61", "28", "35", "9.90", "10.10", "9.70", "10.60", "0.72", "1", "1", "0", "0", "0"],
        ["1", "2", "68", "70", "24", "28", "9.90", "10.10", "9.70", "10.60", "0.68", "1", "0", "1", "0", "0"],
        ["1", "3", "52", "48", "51", "5", "9.90", "10.10", "9.70", "10.60", "0.12", "1", "0", "0", "1", "0"],
        ["1", "4", "30", "25", "75", "-35", "9.90", "10.10", "9.70", "10.60", "-0.55", "1", "0", "0", "0", "1"],
        ["1", "5", "20", "15", "86", "-60", "9.90", "10.10", "9.70", "10.60", "-0.82", "1", "0", "0", "0", "1"],
    ]
    payload = {
        "stock_code": canonicalize_tdx_level1_symbol(symbol),
        "time_list": selected,
        "data_list": rows,
        "count": 7,
    }
    validate_tq_send_payload(payload, expected_column_count=16)
    return payload


def inspect_tqcenter_api(api: Any, module_path: Path) -> dict[str, Any]:
    """Record the exact installed adapter surface used by the smoke probe."""

    names = (
        "initialize",
        "send_bt_data",
        "formula_set_data_info",
        "exec_to_tdx",
        "send_warn",
        "create_sector",
        "send_user_block",
        "send_message",
        "close",
    )
    functions: dict[str, Any] = {}
    for name in names:
        member = getattr(api, name, None)
        if not callable(member):
            functions[name] = {"available": False}
            continue
        details: dict[str, Any] = {"available": True}
        try:
            details["signature"] = str(inspect.signature(member))
        except (TypeError, ValueError):
            details["signature"] = "unavailable"
        docstring = inspect.getdoc(member)
        if docstring:
            details["docstring"] = docstring[:2_000]
            details["docstring_length"] = len(docstring)
            details["docstring_truncated"] = len(docstring) > 2_000
        try:
            source_lines, first_line = inspect.getsourcelines(member)
        except (OSError, TypeError) as exc:
            details["source_available"] = False
            details["source_unavailable_reason"] = type(exc).__name__
        else:
            source = "".join(source_lines)
            details.update(
                {
                    "source_available": True,
                    "source_first_line": first_line,
                    "source_last_line": first_line + len(source_lines) - 1,
                    "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
                    "source_mentions_formula_set_data_info": "formula_set_data_info" in source,
                    "source_mentions_exec_to_tdx": "exec_to_tdx" in source,
                    "source_mentions_run_id": "run_id" in source,
                    "source_excerpt": source[:8_000],
                    "source_length": len(source),
                    "source_excerpt_truncated": len(source) > 8_000,
                }
            )
        functions[name] = details
    module_source = module_path.read_text(encoding="utf-8", errors="replace")
    return {
        "module_path": str(module_path.resolve()),
        "module_sha256": hashlib.sha256(module_path.read_bytes()).hexdigest(),
        "module_mentions_outside": "Outside" in module_source,
        "module_mentions_signals_tq": "SIGNALS_TQ" in module_source,
        "module_outside_occurrence_count": module_source.lower().count("outside"),
        "module_signals_tq_occurrence_count": module_source.lower().count("signals_tq"),
        "functions": functions,
    }


def load_installed_tqcenter(tdx_user_dir: str | Path) -> tuple[Any, Any, Path]:
    """Import the exact configured ``tqcenter.py`` through normal Python import."""

    user_dir = Path(tdx_user_dir).resolve()
    module_path = user_dir / "tqcenter.py"
    if not module_path.is_file():
        raise RuntimeError(f"tqcenter.py not found: {module_path}")
    existing = sys.modules.get("tqcenter")
    if existing is not None:
        existing_path = getattr(existing, "__file__", None)
        if existing_path is None or Path(existing_path).resolve() != module_path:
            raise RuntimeError("an incompatible tqcenter module is already imported")
    user_dir_text = str(user_dir)
    path_was_prepended = not sys.path or sys.path[0] != user_dir_text
    if path_was_prepended:
        sys.path.insert(0, user_dir_text)
    try:
        module = __import__("tqcenter", fromlist=("tq",))
    finally:
        if path_was_prepended:
            try:
                sys.path.remove(user_dir_text)
            except ValueError:
                pass
    origin = getattr(module, "__file__", None)
    if origin is None or Path(origin).resolve() != module_path:
        raise RuntimeError("tqcenter import did not resolve to the configured tqcenter.py")
    api = getattr(module, "tq", None)
    if api is None:
        raise RuntimeError("installed tqcenter.py does not expose tqcenter.tq")
    return module, api, module_path


def run_tq_display_smoke(
    api: Any,
    *,
    module_path: Path,
    symbol: str,
    timestamps: Sequence[str],
    initialize_path: str,
    hold_seconds: float = 0.0,
    probe: str = "all",
    sleeper: Callable[[float], None] = time.sleep,
    ready_callback: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Send selected official-shape probes while keeping one TQ session open."""

    send_bt_data = getattr(api, "send_bt_data", None)
    if not callable(send_bt_data):
        raise RuntimeError("installed tqcenter.tq does not expose send_bt_data")
    initialize = getattr(api, "initialize", None)
    close = getattr(api, "close", None)
    if not callable(initialize) or not callable(close):
        raise RuntimeError("installed tqcenter.tq must expose initialize and close")

    if probe not in {"all", "non-square", "official-shape", "quantpilot"}:
        raise ValueError("unsupported TQ smoke probe")
    minimal_payload = build_minimal_smoke_payload(symbol, timestamps)
    official_shape_payload = build_official_shape_smoke_payload(symbol, timestamps)
    quantpilot_payload = build_quantpilot_smoke_payload(symbol, timestamps)
    probe_payloads = {
        "non-square": minimal_payload,
        "official-shape": official_shape_payload,
        "quantpilot": quantpilot_payload,
    }
    selected_probes = tuple(probe_payloads) if probe == "all" else (probe,)
    selected_payload = probe_payloads[selected_probes[-1]]
    audit = inspect_tqcenter_api(api, module_path)
    initialized = False
    minimal_response: dict[str, Any] = {}
    quantpilot_response: dict[str, Any] = {}
    official_shape_response: dict[str, Any] = {}
    probe_responses: dict[str, dict[str, Any]] = {}
    interrupted = False
    try:
        initialize(str(Path(initialize_path).resolve()))
        initialized = True
        for probe_name in selected_probes:
            response = normalize_tq_response(send_bt_data(**probe_payloads[probe_name]))
            probe_responses[probe_name] = response
            if response.get("accepted") is False:
                raise RuntimeError(
                    f"{probe_name} send_bt_data call failed: "
                    f"{response.get('sanitized_error', 'unknown TQ error')}"
                )
        minimal_response = probe_responses.get("non-square", {})
        official_shape_response = probe_responses.get("official-shape", {})
        quantpilot_response = probe_responses.get("quantpilot", {})
        ready_evidence = {
            "event": "tq_display_smoke_ready",
            "symbol": selected_payload["stock_code"],
            "timestamps": selected_payload["time_list"],
            "selected_probes": list(selected_probes),
            "minimal_values": [list(row) for row in MINIMAL_VALUES],
            "quantpilot_states_zh": list(SMOKE_STATE_LABELS_ZH),
            "minimal_transport_response": minimal_response,
            "quantpilot_transport_response": quantpilot_response,
            "official_shape_transport_response": official_shape_response,
            "probe_transport_responses": probe_responses,
            "minimal_payload": _payload_summary(minimal_payload),
            "official_shape_payload": _payload_summary(official_shape_payload),
            "quantpilot_payload": _payload_summary(quantpilot_payload),
            "api_audit": audit,
            "hold_seconds": float(hold_seconds),
            "visual_confirmation_required": True,
        }
        if ready_callback is not None:
            ready_callback(ready_evidence)
        if hold_seconds > 0:
            try:
                sleeper(float(hold_seconds))
            except KeyboardInterrupt:
                interrupted = True
    finally:
        if initialized:
            close()

    return {
        "schema_version": "tdx_tq_display_smoke_v1",
        "status": "transport_accepted_pending_visual_confirmation",
        "symbol": selected_payload["stock_code"],
        "timestamps": selected_payload["time_list"],
        "selected_probes": list(selected_probes),
        "minimal_formula": MINIMAL_FORMULA,
        "minimal_payload": _payload_summary(minimal_payload),
        "official_shape_payload": _payload_summary(official_shape_payload),
        "quantpilot_payload": _payload_summary(quantpilot_payload),
        "minimal_transport_response": minimal_response,
        "quantpilot_transport_response": quantpilot_response,
        "official_shape_transport_response": official_shape_response,
        "probe_transport_responses": probe_responses,
        "api_audit": audit,
        "formula_set_data_info_called": False,
        "exec_to_tdx_called": False,
        "run_id_reused_as_input": False,
        "session_kept_open_seconds": float(hold_seconds),
        "hold_interrupted": interrupted,
        "ordinary_chart_overlay_proven": False,
        "visual_confirmation_required": True,
        "protocol_assertions": {
            "data_orientation": "row_major_by_timestamp",
            "count_equals_timestamp_count": True,
            "all_transmitted_scalars_are_numeric_strings": True,
        },
        "acceptance_note": (
            "ErrorId=0 proves transport acceptance only. Confirm the non-square values "
            "and QuantPilot transitions on the ordinary one-minute chart."
        ),
    }


def _payload_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    data_list = payload["data_list"]
    return {
        "stock_code": payload["stock_code"],
        "time_list": list(payload["time_list"]),
        "count": payload["count"],
        "data_orientation": "row_major_by_timestamp",
        "row_count": len(data_list),
        "columns_per_row": [len(row) for row in data_list],
        "data_list": data_list,
    }


def _validate_timestamps(timestamps: Sequence[str]) -> None:
    for value in timestamps:
        try:
            parsed = datetime.strptime(value, "%Y%m%d%H%M%S")
        except ValueError as exc:
            raise ValueError("TQ timestamps must use YYYYMMDDHHMMSS") from exc
        if parsed.second != 0:
            raise ValueError("TQ smoke timestamps must align to one-minute bars")


def report_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
