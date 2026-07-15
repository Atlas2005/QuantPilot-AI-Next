#!/usr/bin/env python3
"""Create one authenticated QMT broker-simulation intent; never contact QMT."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from typing import Any

from quantpilot_core.qmt_simulation_execution import (
    QmtSimulationExecutionError,
    canonical_json_bytes,
    create_and_write_intent,
)


def _source_digest(args: argparse.Namespace, intent_id: str) -> str:
    if args.source_order_digest is not None:
        return args.source_order_digest
    source: dict[str, Any] = {
        "intent_id": intent_id,
        "limit_price": args.limit_price,
        "quantity": args.quantity,
        "run_label": args.run_label,
        "side": args.side,
        "symbol": args.symbol,
    }
    return hashlib.sha256(canonical_json_bytes(source)).hexdigest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--side", choices=("buy", "sell"), required=True)
    parser.add_argument("--quantity", type=int, required=True)
    parser.add_argument("--limit-price", type=float, required=True)
    parser.add_argument(
        "--expected-redacted-account-id",
        "--expected-redacted-account-binding",
        dest="expected_redacted_account_id",
        required=True,
    )
    parser.add_argument("--bridge-root", required=True)
    parser.add_argument("--intent-id")
    parser.add_argument("--run-label")
    parser.add_argument("--source-order-digest")
    parser.add_argument("--expires-in-seconds", type=int, default=900)
    parser.add_argument("--confirm-broker-simulation-order", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.confirm_broker_simulation_order:
        print(
            "intent_creation_refused=confirm_broker_simulation_order_required",
            file=sys.stderr,
        )
        return 2

    intent_id = args.intent_id or "qpsim-" + uuid.uuid4().hex
    try:
        intent, path = create_and_write_intent(
            args.bridge_root,
            intent_id=intent_id,
            expected_redacted_account_id=args.expected_redacted_account_id,
            symbol=args.symbol,
            side=args.side,
            quantity=args.quantity,
            limit_price=args.limit_price,
            source_order_digest=_source_digest(args, intent_id),
            ttl_seconds=args.expires_in_seconds,
            run_label=args.run_label,
        )
    except QmtSimulationExecutionError as exc:
        print("intent_creation_failed=" + exc.code, file=sys.stderr)
        return 2
    except (OSError, TypeError, ValueError, OverflowError):
        print("intent_creation_failed=invalid_command_input", file=sys.stderr)
        return 2

    payload = {
        "created": True,
        "environment": intent.environment,
        "expires_at": intent.expires_at.isoformat(),
        "intent_file": path.name,
        "intent_id": intent.intent_id,
        "order_kind": intent.order_kind,
        "protocol_version": intent.protocol_version,
        "status": "received",
    }
    print(
        json.dumps(
            payload,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
