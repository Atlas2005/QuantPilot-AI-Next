"""Report serialization helpers for the durable daily paper loop."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Mapping

from quantpilot_core.daily_paper_loop.state import canonical_json


def write_report_atomic(report: Mapping[str, Any], path: str | Path | None) -> str | None:
    if path is None:
        return None
    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = report_path.with_name(f".{report_path.name}.tmp")
    payload = json.dumps(_json_ready(report), sort_keys=True, indent=2, ensure_ascii=True)
    with temp_path.open("w", encoding="utf-8") as handle:
        handle.write(payload)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, report_path)
    return str(report_path)


def report_digest(report: Mapping[str, Any]) -> str:
    from quantpilot_core.daily_paper_loop.state import payload_digest

    return payload_digest(report)


def _json_ready(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _json_ready(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_json_ready(item) for item in value]
    if hasattr(value, "value"):
        return value.value
    try:
        canonical_json(value)
        return value
    except TypeError:
        return str(value)
