"""Persistent, non-repainting marker ledger and installable TDX formula bundle."""

from __future__ import annotations

import csv
import json
import os
import threading
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence


MARKER_SCHEMA_VERSION = "quantpilot_manual_marker_ledger_v1"
FORMULA_NAME = "QP_MANUAL_MARKERS"
VISIBLE_STATES = frozenset({"ENTRY", "HOLD", "WEAKENING", "EXIT", "INVALIDATED"})
LIFECYCLE_STATES = VISIBLE_STATES | {"WAIT"}

FORMULA_SOURCE = """{ QuantPilot manual lifecycle markers - ordinary K-line main chart }
{ Data is supplied by the persistent Python bridge through SIGNALS_TQ. }
{ Transport acceptance is not visual proof; complete the Windows chart check. }

SIGNAL_VALID := SIGNALS_TQ(1,0);
PRED_STATE   := SIGNALS_TQ(2,0);
ENTRY_PROB   := SIGNALS_TQ(3,0);
CONT_PROB    := SIGNALS_TQ(4,0);
EXIT_PROB    := SIGNALS_TQ(5,0);
ENTRY_LOW    := SIGNALS_TQ(7,0);
ENTRY_HIGH   := SIGNALS_TQ(8,0);
INVALIDATION := SIGNALS_TQ(9,0);
TARGET1      := SIGNALS_TQ(10,0);
MATERIAL     := SIGNALS_TQ(12,0);
ENTRY_SIG    := SIGNALS_TQ(13,0);
HOLD_SIG     := SIGNALS_TQ(14,0);
WEAKENING    := SIGNALS_TQ(15,0);
EXIT_SIG     := SIGNALS_TQ(16,0);

VALID := SIGNAL_VALID = 1 AND MATERIAL = 1;
ENTRY_LOW_LINE: IF(VALID, ENTRY_LOW, DRAWNULL), COLORCYAN, DOTLINE;
ENTRY_HIGH_LINE: IF(VALID, ENTRY_HIGH, DRAWNULL), COLORCYAN, DOTLINE;
INVALIDATION_LINE: IF(VALID, INVALIDATION, DRAWNULL), COLORGREEN, DOTLINE;
TARGET1_LINE: IF(VALID, TARGET1, DRAWNULL), COLORRED, DOTLINE;
DRAWICON(VALID AND ENTRY_SIG = 1, LOW * 0.99, 1);
DRAWICON(VALID AND EXIT_SIG = 1, HIGH * 1.01, 2);
DRAWTEXT(VALID AND PRED_STATE = 1, LOW * 0.98, '买 ' + NUMTOSTR(ENTRY_PROB, 0) + '%'), COLORRED;
DRAWTEXT(VALID AND PRED_STATE = 2, LOW * 0.98, '持 ' + NUMTOSTR(CONT_PROB, 0) + '%'), COLORYELLOW;
DRAWTEXT(VALID AND PRED_STATE = 3, HIGH * 1.02, '弱'), COLORGRAY;
DRAWTEXT(VALID AND PRED_STATE = 4, HIGH * 1.02, '卖 ' + NUMTOSTR(EXIT_PROB, 0) + '%'), COLORGREEN;
DRAWTEXT(VALID AND PRED_STATE = 5, HIGH * 1.02, '失效'), COLORGREEN;
"""

INSTALL_README = """QuantPilot TDX marker bundle
================================

1. Keep TongDaXin open and logged in with TQCenter available.
2. In TongDaXin Formula Manager create a main-chart formula named
   QP_MANUAL_MARKERS and paste QP_MANUAL_MARKERS.formula.txt.
3. Run the QuantPilot intraday command and keep its Python process open.
4. Open a QPTY symbol on the ordinary one-minute chart and apply the formula.
5. Confirm 买/持/弱/卖/失效 occur at the timestamps in marker_events.csv.
6. Confirm entry, invalidation, and target levels match the same ledger row.

The JSON status remains pending_windows_visual_confirmation until a human
observes the ordinary chart. ErrorId=0 is transport acceptance only.
"""


def write_json_atomic(payload: Any, path: str | Path) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(_jsonable(payload), handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, target)
    return str(target)


def write_text_atomic(text: str, path: str | Path) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        handle.write(text)
        if text and not text.endswith("\n"):
            handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, target)
    return str(target)


def install_marker_bundle(output_dir: str | Path) -> Mapping[str, Any]:
    """Write formula source and an exact Windows acceptance note."""

    root = Path(output_dir)
    formula_path = write_text_atomic(FORMULA_SOURCE, root / f"{FORMULA_NAME}.formula.txt")
    readme_path = write_text_atomic(INSTALL_README, root / "INSTALL_AND_VERIFY.txt")
    return {
        "marker_adapter_initialized": True,
        "adapter": "signals_tq_persistent_formula_bundle_v1",
        "formula_name": FORMULA_NAME,
        "formula_path": formula_path,
        "acceptance_procedure_path": readme_path,
        "ordinary_chart_overlay_status": "pending_windows_visual_confirmation",
        "transport_success_is_visual_proof": False,
        "broker_calls": 0,
        "order_submission_calls": 0,
    }


class PersistentMarkerPublisher:
    """Merge lifecycle transitions durably before optional TQ publication.

    Existing signal IDs are immutable. A new ID cannot be inserted before the
    latest persisted timestamp for that symbol, preventing restart-time
    backfilling or later-data repainting.
    """

    def __init__(
        self,
        output_dir: str | Path,
        *,
        delegate: Any | None = None,
        holdings: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> None:
        self.root = Path(output_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        self.delegate = delegate
        self.holdings = {str(key): dict(value) for key, value in (holdings or {}).items()}
        self.events_path = self.root / "marker_events.json"
        self.csv_path = self.root / "marker_events.csv"
        self.current_path = self.root / "current_states.json"
        self._lock = threading.RLock()
        self._records = self._load_records()
        self.duplicate_count = 0
        self.repaint_rejection_count = 0
        self.last_transport: Mapping[str, Any] | None = None
        self.bundle = dict(install_marker_bundle(self.root / "formula_bundle"))

    @property
    def records(self) -> tuple[Mapping[str, Any], ...]:
        with self._lock:
            return tuple(dict(item) for item in self._records)

    def initialize_wait_states(
        self,
        symbols: Sequence[str],
        *,
        timestamp: str,
        reference_prices: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        """Persist the non-visible initial state once without publishing a label."""

        prices = dict(reference_prices or {})
        records = [
            {
                "schema_version": "tdx_prediction_signal_v1",
                "signal_id": f"manual-wait:{symbol}:{timestamp}",
                "symbol": symbol,
                "timestamp": timestamp,
                "decision_timestamp": timestamp,
                "state": "WAIT",
                "state_label_zh": "等",
                "decision_price": prices.get(symbol),
                "material_change": False,
                "reason_code": "manual_monitoring_initialized",
            }
            for symbol in symbols
        ]
        self._merge(records, origin="initial_wait", include_wait=True)
        return self.report(historical_baseline=True)

    def restore_transport_baseline(self) -> Mapping[str, Any]:
        """Republish the immutable ledger after restart without stale warnings."""

        if self.delegate is None or not self._records:
            return self.report(historical_baseline=True)
        publisher = getattr(self.delegate, "publish_baseline", None)
        try:
            self.last_transport = (
                publisher(self.records) if callable(publisher) else self.delegate(self.records)
            )
        except Exception as exc:
            self.last_transport = _transport_failure(exc)
        return self.report(historical_baseline=True)

    def publish_baseline(self, records: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
        merged = self._merge(records, origin="historical_baseline")
        if self.delegate is not None:
            publisher = getattr(self.delegate, "publish_baseline", None)
            try:
                self.last_transport = (
                    publisher(merged) if callable(publisher) else self.delegate(merged)
                )
            except Exception as exc:
                self.last_transport = _transport_failure(exc)
        return self.report(historical_baseline=True)

    def __call__(self, records: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
        merged = self._merge(records, origin="live_transition")
        if self.delegate is not None:
            try:
                self.last_transport = self.delegate(merged)
            except Exception as exc:
                self.last_transport = _transport_failure(exc)
        return self.report(historical_baseline=False)

    def report(self, *, historical_baseline: bool | None = None) -> Mapping[str, Any]:
        current = _current_states(self._records)
        return {
            **self.bundle,
            "schema_version": MARKER_SCHEMA_VERSION,
            "event_log_path": str(self.events_path),
            "event_csv_path": str(self.csv_path),
            "current_state_path": str(self.current_path),
            "persisted_transition_count": len(self._records),
            "current_states": current,
            "duplicate_transition_count": self.duplicate_count,
            "repaint_rejection_count": self.repaint_rejection_count,
            "historical_baseline": historical_baseline,
            "transport": self.last_transport,
            "ordinary_chart_overlay_proven": False,
            "broker_calls": 0,
            "order_submission_calls": 0,
        }

    def _merge(
        self,
        records: Sequence[Mapping[str, Any]],
        *,
        origin: str,
        include_wait: bool = False,
    ) -> tuple[Mapping[str, Any], ...]:
        with self._lock:
            by_id = {str(item["signal_id"]): item for item in self._records}
            latest = _latest_timestamps(self._records)
            accepted_states = LIFECYCLE_STATES if include_wait else VISIBLE_STATES
            incoming = sorted(
                (dict(item) for item in records if str(item.get("state", "")).upper() in accepted_states),
                key=lambda item: (_timestamp(item), str(item.get("symbol", "")), str(item.get("signal_id", ""))),
            )
            for raw in incoming:
                symbol = str(raw.get("symbol", "")).strip()
                state = str(raw.get("state", "")).upper()
                timestamp = _timestamp(raw)
                signal_id = str(raw.get("signal_id") or f"{symbol}:{timestamp}:{state}")
                raw["signal_id"] = signal_id
                raw["state"] = state
                prior = by_id.get(signal_id)
                if prior is not None:
                    if _immutable_marker_payload(prior) != _immutable_marker_payload(raw):
                        raise ValueError(f"persisted marker mutation rejected: {signal_id}")
                    self.duplicate_count += 1
                    continue
                if symbol in latest and timestamp < latest[symbol]:
                    self.repaint_rejection_count += 1
                    raise ValueError(f"non-causal marker insertion rejected: {symbol}:{timestamp}")
                raw["marker_origin"] = origin
                raw["historical_event"] = origin in {"historical_baseline", "initial_wait"}
                raw["manual_holding"] = _holding_context(self.holdings.get(symbol), state)
                self._records.append(raw)
                by_id[signal_id] = raw
                latest[symbol] = timestamp
            self._records.sort(key=lambda item: (_timestamp(item), str(item.get("symbol", ""))))
            self._persist()
            return tuple(dict(item) for item in self._records)

    def _persist(self) -> None:
        write_json_atomic(self._records, self.events_path)
        write_json_atomic(_current_states(self._records), self.current_path)
        temporary = self.csv_path.with_name(f".{self.csv_path.name}.tmp")
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        fields = (
            "signal_id", "symbol", "timestamp", "state", "state_label_zh",
            "decision_price", "entry_zone_low", "entry_zone_high",
            "invalidation_price", "first_target_price", "reason_code",
            "marker_origin", "historical_event",
        )
        with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for item in self._records:
                writer.writerow(item)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.csv_path)

    def _load_records(self) -> list[dict[str, Any]]:
        try:
            value = json.loads(self.events_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
            raise ValueError("persisted marker ledger must be a JSON array of objects")
        records = [dict(item) for item in value]
        seen: set[str] = set()
        latest: dict[str, str] = {}
        for item in sorted(records, key=lambda row: (_timestamp(row), str(row.get("symbol", "")))):
            signal_id = str(item.get("signal_id", ""))
            symbol = str(item.get("symbol", ""))
            timestamp = _timestamp(item)
            if not signal_id or signal_id in seen:
                raise ValueError("persisted marker ledger contains duplicate or empty signal_id")
            if symbol in latest and timestamp < latest[symbol]:
                raise ValueError("persisted marker ledger is non-chronological")
            seen.add(signal_id)
            latest[symbol] = timestamp
        return records


def _timestamp(record: Mapping[str, Any]) -> str:
    value = str(record.get("timestamp") or record.get("decision_timestamp") or "")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("marker timestamp must be timezone-aware")
    return parsed.isoformat()


def _latest_timestamps(records: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    output: dict[str, str] = {}
    for item in records:
        symbol = str(item.get("symbol", ""))
        timestamp = _timestamp(item)
        output[symbol] = max(output.get(symbol, timestamp), timestamp)
    return output


def _immutable_marker_payload(record: Mapping[str, Any]) -> Mapping[str, Any]:
    ignored = {"marker_origin", "historical_event", "manual_holding"}
    return {key: _jsonable(value) for key, value in record.items() if key not in ignored}


def _current_states(records: Sequence[Mapping[str, Any]]) -> Mapping[str, Mapping[str, Any]]:
    output: dict[str, Mapping[str, Any]] = {}
    for item in sorted(records, key=lambda row: (_timestamp(row), str(row.get("symbol", "")))):
        output[str(item.get("symbol", ""))] = {
            "signal_id": item.get("signal_id"),
            "state": item.get("state"),
            "state_label_zh": item.get("state_label_zh"),
            "timestamp": _timestamp(item),
            "decision_price": item.get("decision_price"),
            "manual_holding": item.get("manual_holding"),
        }
    return dict(sorted(output.items()))


def _holding_context(holding: Mapping[str, Any] | None, state: str) -> Mapping[str, Any]:
    value = dict(holding or {})
    quantity = int(value.get("quantity", value.get("current_quantity", 0)) or 0)
    sellable = int(value.get("sellable_quantity", 0) or 0)
    exit_state = state in {"WEAKENING", "EXIT", "INVALIDATED"}
    return {
        "supplied": holding is not None,
        "quantity": quantity,
        "sellable_quantity": sellable,
        "average_cost": value.get("average_cost"),
        "t1_sellable": sellable > 0,
        "manual_actionability": (
            "manual_sell_available" if exit_state and sellable > 0
            else "t1_locked_or_no_position" if exit_state
            else "manual_review"
        ),
    }


def _transport_failure(exc: Exception) -> Mapping[str, Any]:
    return {
        "status": "failed_nonblocking",
        "error_type": type(exc).__name__,
        "sanitized_error": " ".join(str(exc).split())[:500],
        "ordinary_chart_overlay_status": "pending_windows_visual_confirmation",
    }


def _jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value
