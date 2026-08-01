"""Atomic JSON and CSV writers for TDX signal export."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any, Sequence

from quantpilot_core.tdx_manual_signal_bridge.contracts import (
    TDX_SIGNAL_CSV_HEADER,
    TdxSignal,
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


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

from quantpilot_core.tdx_manual_signal_bridge.exporter import signal_to_dict, signal_to_row


def _write_signals_atomic(
    *,
    signals: Sequence[TdxSignal],
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
