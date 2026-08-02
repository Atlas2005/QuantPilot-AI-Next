"""Atomic JSON and CSV writers for TDX signal export."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from quantpilot_core.tdx_manual_signal_bridge.contracts import (
    TDX_SIGNAL_CSV_HEADER,
    TdxSignal,
)


TDX_PREDICTION_SIGNAL_CSV_HEADER: tuple[str, ...] = (
    "schema_version",
    "symbol",
    "timestamp",
    "data_cutoff_timestamp",
    "state",
    "entry_probability",
    "continuation_probability",
    "exit_probability",
    "expected_move",
    "expected_return",
    "entry_zone_low",
    "entry_zone_high",
    "invalidation_price",
    "first_target_price",
    "reason_code",
    "evidence_refs",
    "context_data_asofs",
    "source_components",
    "material_change",
)


def write_signals_json_atomic(signals: Sequence[TdxSignal], path: str | Path) -> str:
    """Write signals as newline-delimited JSON (one object per line), atomically.

    Returns the resolved output path on success.
    """
    return _write_signals_atomic(
        signals=signals,
        path=Path(path),
        suffix=".json",
        formatter=_format_json,
    )


def write_signals_csv_atomic(signals: Sequence[TdxSignal], path: str | Path) -> str:
    """Write signals as CSV with header, atomically.

    CSV is an audit product — no claim that TDX formulas can read CSV directly.
    Returns the resolved output path on success.
    """
    return _write_signals_atomic(
        signals=signals,
        path=Path(path),
        suffix=".csv",
        formatter=_format_csv,
    )


def write_signals_atomic(
    signals: Sequence[TdxSignal],
    output_dir: str | Path,
    *,
    json_filename: str = "latest.json",
    csv_filename: str = "latest.csv",
) -> tuple[str, str]:
    """Write both JSON and CSV atomically to output_dir.

    Returns (json_path, csv_path).
    """
    out = Path(output_dir)
    json_path = write_signals_json_atomic(signals, out / json_filename)
    csv_path = write_signals_csv_atomic(signals, out / csv_filename)
    return json_path, csv_path


def write_prediction_signals_atomic(
    signals: Sequence[Mapping[str, Any]],
    output_dir: str | Path,
    *,
    json_filename: str = "latest_prediction.json",
    csv_filename: str = "latest_prediction.csv",
) -> tuple[str, str]:
    """Extend the existing atomic formula-data path for intraday predictions."""

    records = tuple(_prediction_record(signal) for signal in signals)
    out = Path(output_dir)
    json_path = _write_signals_atomic(
        signals=records,
        path=out / json_filename,
        suffix=".json",
        formatter=_format_prediction_json,
    )
    csv_path = _write_signals_atomic(
        signals=records,
        path=out / csv_filename,
        suffix=".csv",
        formatter=_format_prediction_csv,
    )
    return json_path, csv_path


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

from quantpilot_core.tdx_manual_signal_bridge.exporter import signal_to_dict, signal_to_row


def _write_signals_atomic(
    *,
    signals: Sequence[Any],
    path: Path,
    suffix: str,
    formatter: Any,
) -> str:
    out_path = path if path.suffix == suffix else path.with_suffix(suffix)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = out_path.with_name(f".{out_path.name}.tmp")

    with temp_path.open("w", encoding="utf-8", newline="") as handle:
        formatter(signals, handle)
        handle.flush()
        os.fsync(handle.fileno())

    os.replace(temp_path, out_path)
    return str(out_path)


def _format_json(signals: Sequence[TdxSignal], handle: Any) -> None:
    """Write as JSON array for consumer compatibility."""
    records = [signal_to_dict(s) for s in signals]
    json.dump(records, handle, sort_keys=True, indent=2, ensure_ascii=True)
    handle.write("\n")


def _format_csv(signals: Sequence[TdxSignal], handle: Any) -> None:
    writer = csv.writer(handle, lineterminator="\n")
    writer.writerow(list(TDX_SIGNAL_CSV_HEADER))
    for signal in signals:
        writer.writerow(list(signal_to_row(signal)))


def _format_prediction_json(
    signals: Sequence[Mapping[str, Any]],
    handle: Any,
) -> None:
    json.dump(list(signals), handle, sort_keys=True, indent=2, ensure_ascii=True)
    handle.write("\n")


def _format_prediction_csv(
    signals: Sequence[Mapping[str, Any]],
    handle: Any,
) -> None:
    writer = csv.writer(handle, lineterminator="\n")
    writer.writerow(TDX_PREDICTION_SIGNAL_CSV_HEADER)
    for signal in signals:
        writer.writerow(
            [
                signal["schema_version"],
                signal["symbol"],
                signal["timestamp"],
                signal["data_cutoff_timestamp"],
                signal["state"],
                signal["entry_probability"],
                signal["continuation_probability"],
                signal["exit_probability"],
                signal["expected_move"],
                signal["expected_return"],
                signal["entry_zone_low"],
                signal["entry_zone_high"],
                signal["invalidation_price"],
                signal["first_target_price"],
                signal["reason_code"],
                "|".join(signal["evidence_refs"]),
                "|".join(signal["context_data_asofs"]),
                "|".join(signal["source_components"]),
                str(bool(signal["material_change"])).lower(),
            ]
        )


def _prediction_record(signal: Mapping[str, Any]) -> Mapping[str, Any]:
    sequence_fields = {"context_data_asofs", "evidence_refs", "source_components"}
    required = set(TDX_PREDICTION_SIGNAL_CSV_HEADER) - sequence_fields
    missing = required - set(signal)
    if missing:
        raise ValueError(f"prediction signal missing required fields: {sorted(missing)}")
    sequences: dict[str, list[Any]] = {}
    for field_name in sorted(sequence_fields):
        values = signal.get(field_name, ())
        if not isinstance(values, Sequence) or isinstance(
            values, (str, bytes, bytearray)
        ):
            raise ValueError(f"prediction {field_name} must be a sequence")
        sequences[field_name] = list(values)
    return {
        key: (sequences[key] if key in sequence_fields else signal[key])
        for key in TDX_PREDICTION_SIGNAL_CSV_HEADER
    }
