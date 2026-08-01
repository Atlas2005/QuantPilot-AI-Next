#!/usr/bin/env python3
"""Run the optional Windows TDX Level1 adapter and intraday collector."""

from __future__ import annotations

import argparse
import json
import os
from typing import Sequence

from quantpilot_core.continuous_paper import InMemoryReportingStore, PostgreSQLReportingStore
from quantpilot_core.real_data_provider import (
    LiveLevel1Collector,
    TDXInitializationError,
    TDXLevel1Provider,
    TDXOperationError,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect TDX TQCenter Level1 snapshots without signals or order execution.",
    )
    parser.add_argument("--symbols", required=True, help="Comma-separated explicit A-share symbols.")
    parser.add_argument("--tdx-user-dir", required=True, help="Directory containing the Windows tqcenter.py runtime.")
    parser.add_argument("--duration", type=float, default=60.0, help="Collection duration in seconds.")
    parser.add_argument(
        "--store-provider",
        choices=("auto", "memory", "postgresql"),
        default="auto",
        help="Persistence backend; auto uses PostgreSQL when QUANTPILOT_POSTGRES_DSN is configured.",
    )
    parser.add_argument(
        "--shadow",
        action="store_true",
        help="Disable downstream trading side effects without changing quote/bar persistence.",
    )
    return parser


def _symbols(value: str) -> tuple[str, ...]:
    symbols = tuple(dict.fromkeys(item.strip() for item in value.split(",") if item.strip()))
    if not symbols:
        raise ValueError("--symbols must contain at least one symbol")
    return symbols


def _store(store_provider: str):
    dsn = os.environ.get("QUANTPILOT_POSTGRES_DSN")
    resolved = _resolved_storage_backend(store_provider, dsn)
    if resolved == "postgresql" and not dsn:
        raise RuntimeError(
            "--store-provider postgresql requires QUANTPILOT_POSTGRES_DSN to be configured"
        )
    store = PostgreSQLReportingStore(dsn) if resolved == "postgresql" else InMemoryReportingStore()
    store.initialize()
    return store, resolved


def _resolved_storage_backend(store_provider: str, dsn: str | None) -> str:
    if store_provider == "auto":
        return "postgresql" if dsn else "memory"
    return store_provider


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.duration < 0:
        parser.error("--duration must be non-negative")
    storage_backend = _resolved_storage_backend(
        args.store_provider,
        os.environ.get("QUANTPILOT_POSTGRES_DSN"),
    )
    try:
        symbols = _symbols(args.symbols)
        store, storage_backend = _store(args.store_provider)
        collector = LiveLevel1Collector(
            TDXLevel1Provider(args.tdx_user_dir),
            symbols,
            sink=store,
            storage_backend=storage_backend,
            shadow=bool(args.shadow),
        )
        try:
            report = collector.run(float(args.duration))
        except KeyboardInterrupt:
            collector.shutdown()
            report = collector.report()
        print(json.dumps(report.as_dict(), sort_keys=True))
        return 0
    except Exception as exc:
        payload = {
            "connection_status": "unavailable",
            "symbols": tuple(item.strip() for item in args.symbols.split(",") if item.strip()),
            "event_count": 0,
            "snapshot_count": 0,
            "bar_count": 0,
            "callback_count": 0,
            "quote_change_count": 0,
            "persisted_event_count": 0,
            "persisted_bar_count": 0,
            "storage_backend": storage_backend,
            "realtime_market_change_detected": False,
            "subscription_attempted": False,
            "subscription_succeeded": False,
            "subscription_error_type": None,
            "sanitized_subscription_error": None,
            "polling_fallback_active": False,
            "shadow": bool(args.shadow),
            "error": str(exc),
        }
        if isinstance(exc, (TDXInitializationError, TDXOperationError)):
            payload.update(exc.as_dict())
        print(json.dumps(payload, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
