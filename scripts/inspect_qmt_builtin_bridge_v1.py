#!/usr/bin/env python3
"""Inspect one completed QMT built-in bridge snapshot without contacting QMT."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quantpilot_core.qmt_builtin_bridge import QmtBuiltinBridgeError
from quantpilot_core.runtime_node.config import RuntimeConfig
from quantpilot_core.runtime_node.qmt_bridge_status import QmtBridgeInspectionError, qmt_builtin_bridge_status_payload

REPORT_FILE_NAME = "qmt_builtin_bridge_inspection_v1.json"


def _write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(path.name + ".tmp")
    serialized = json.dumps(payload, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n"
    try:
        with temporary_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except Exception:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass
        raise


def inspection_payload(config: RuntimeConfig | None = None, *, now: datetime | None = None) -> dict[str, Any]:
    config = config or RuntimeConfig.from_environment()
    observed_at = now or datetime.now(timezone.utc)
    try:
        return qmt_builtin_bridge_status_payload(config, now=observed_at)
    except (QmtBuiltinBridgeError, QmtBridgeInspectionError, OSError) as exc:
        return {
            "ok": False,
            "validation_result": f"invalid:{type(exc).__name__}",
            "error": str(exc),
            "provider": config.broker_provider.value,
            "read_only": True,
            "order_submission_enabled": False,
            "cancel_enabled": False,
            "passorder_invoked": False,
            "cancel_invoked": False,
        }


def _print_text(payload: dict[str, Any]) -> None:
    ordered_fields = (
        "validation_result",
        "snapshot_timestamp",
        "snapshot_age_seconds",
        "provider",
        "provider_mode",
        "account_status",
        "trading_date",
        "total_assets",
        "available_cash",
        "position_count",
        "order_count",
        "trade_count",
        "read_only",
        "order_submission_enabled",
        "cancel_enabled",
        "passorder_invoked",
        "cancel_invoked",
        "report_path",
        "error",
    )
    for name in ordered_fields:
        if name in payload:
            value = payload[name]
            if isinstance(value, bool):
                value = str(value).lower()
            print(f"{name}={value}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    config = RuntimeConfig.from_environment()
    report_path = (config.paths.reports / REPORT_FILE_NAME).expanduser().resolve()
    payload = inspection_payload(config)
    payload["report_path"] = str(report_path)
    try:
        _write_report(report_path, payload)
    except OSError as exc:
        payload = {
            "ok": False,
            "validation_result": f"invalid:{type(exc).__name__}",
            "error": "inspection report could not be written",
            "provider": config.broker_provider.value,
            "read_only": True,
            "order_submission_enabled": False,
            "cancel_enabled": False,
            "passorder_invoked": False,
            "cancel_invoked": False,
            "report_path": str(report_path),
        }

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=True, allow_nan=False, sort_keys=True))
    else:
        _print_text(payload)
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
