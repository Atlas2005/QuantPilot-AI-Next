#!/usr/bin/env python3
"""Inspect bounded local QMT simulation state/result without contacting QMT."""
from __future__ import annotations

import argparse
import json
from typing import Any

from quantpilot_core.qmt_simulation_execution import (
    MissingResultError,
    MissingStateError,
    QmtSimulationExecutionError,
    read_intent,
    read_result,
    read_state,
)


def inspection_payload(bridge_root: str, intent_id: str) -> dict[str, Any]:
    """Return a credential-safe projection of one local protocol identity."""

    try:
        result = read_result(bridge_root, intent_id)
    except MissingResultError:
        try:
            state = read_state(bridge_root, intent_id)
        except MissingStateError:
            intent = read_intent(bridge_root, intent_id)
            return {
                "artifact": "intent",
                "expires_at": intent.expires_at.isoformat(),
                "intent_id": intent.intent_id,
                "ok": True,
                "passorder_attempted": False,
                "protocol_version": intent.protocol_version,
                "requested_quantity": intent.quantity,
                "side": intent.side,
                "status": "received",
                "symbol": intent.symbol,
            }
        return {
            "artifact": "state",
            "failure_code": state.failure_code,
            "intent_id": state.intent_id,
            "ok": True,
            "passorder_attempted": state.passorder_attempted,
            "protocol_version": state.protocol_version,
            "status": state.status,
        }
    return {
        "artifact": "acknowledgement",
        "average_fill_price": result.average_fill_price,
        "broker_order_reference": result.broker_order_reference,
        "deal_count": result.deal_count,
        "failure_code": result.failure_code,
        "failure_type": result.failure_type,
        "filled_quantity": result.filled_quantity,
        "generated_at": result.generated_at.isoformat(),
        "intent_id": result.intent_id,
        "latest_snapshot_sequence": result.latest_snapshot_sequence,
        "ok": True,
        "order_status": result.order_status,
        "passorder_attempted": result.passorder_attempted,
        "protocol_version": result.protocol_version,
        "requested_quantity": result.requested_quantity,
        "side": result.side,
        "status": result.status,
        "submission_status": result.submission_status,
        "symbol": result.symbol,
        "system_order_id": result.system_order_id,
        "user_order_id": result.user_order_id,
    }


def _print_text(payload: dict[str, Any]) -> None:
    for name in (
        "ok",
        "artifact",
        "protocol_version",
        "intent_id",
        "status",
        "symbol",
        "side",
        "requested_quantity",
        "passorder_attempted",
        "broker_order_reference",
        "system_order_id",
        "order_status",
        "submission_status",
        "filled_quantity",
        "average_fill_price",
        "deal_count",
        "failure_code",
        "failure_type",
        "latest_snapshot_sequence",
        "generated_at",
        "expires_at",
        "error_code",
    ):
        if name in payload:
            value = payload[name]
            if isinstance(value, bool):
                value = str(value).lower()
            print(f"{name}={value}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--bridge-root", required=True)
    parser.add_argument("--intent-id", required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = inspection_payload(args.bridge_root, args.intent_id)
    except QmtSimulationExecutionError as exc:
        payload = {"error_code": exc.code, "intent_id": args.intent_id, "ok": False}
    except (OSError, TypeError, ValueError, OverflowError):
        payload = {
            "error_code": "inspection_failed",
            "intent_id": args.intent_id,
            "ok": False,
        }

    if args.format == "json":
        print(
            json.dumps(
                payload,
                ensure_ascii=True,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    else:
        _print_text(payload)
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
