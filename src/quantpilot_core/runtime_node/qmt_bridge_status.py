"""Narrow status projection for the read-only QMT built-in filesystem bridge."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import BrokerProvider, RuntimeConfig


class QmtBridgeInspectionError(ValueError):
    """The runtime configuration cannot safely inspect the QMT bridge."""


def _repository_root() -> Path | None:
    configured = os.environ.get("QUANTPILOT_REPOSITORY_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    source_checkout = Path(__file__).resolve().parents[3]
    if (source_checkout / "pyproject.toml").is_file() and (source_checkout / "src").is_dir():
        return source_checkout
    return None


def _assert_bridge_root_outside_repository(bridge_root: Path) -> None:
    repository = _repository_root()
    if repository is None:
        return
    try:
        bridge_root.expanduser().resolve().relative_to(repository)
    except ValueError:
        return
    raise QmtBridgeInspectionError("QMT built-in bridge root must be outside the Git repository")


def read_qmt_builtin_bridge_snapshot(config: RuntimeConfig, *, now: datetime | None = None) -> Any:
    """Read one completed bridge snapshot without calling or importing QMT."""
    if config.broker_provider is not BrokerProvider.QMT_BUILTIN_BRIDGE:
        raise QmtBridgeInspectionError("provider must be qmt_builtin_bridge")
    bridge = config.qmt_builtin_bridge
    if bridge.bridge_root is None:
        raise QmtBridgeInspectionError("QMT built-in bridge root is not configured")
    _assert_bridge_root_outside_repository(bridge.bridge_root)
    if not bridge.bridge_root.is_dir():
        raise QmtBridgeInspectionError("QMT built-in bridge directory does not exist")

    from quantpilot_core.qmt_builtin_bridge import QmtBuiltinBridgeReader

    snapshot = QmtBuiltinBridgeReader(
        bridge.bridge_root,
        max_snapshot_age_seconds=bridge.max_snapshot_age_seconds,
        expected_account_type=bridge.expected_account_type,
        expected_redacted_account_id=bridge.expected_redacted_account_id,
    ).read_latest(now=now)
    if snapshot.environment != bridge.provider_mode.value:
        raise QmtBridgeInspectionError("snapshot environment does not match configured QMT provider mode")
    return snapshot


def qmt_builtin_bridge_status_payload(config: RuntimeConfig, *, now: datetime | None = None) -> dict[str, Any]:
    """Return a credential-safe status payload backed by a validated snapshot."""
    observed_at = now or datetime.now(timezone.utc)
    snapshot = read_qmt_builtin_bridge_snapshot(config, now=observed_at)
    account = snapshot.account
    safety = snapshot.safety
    query_status = {
        section: {
            "ok": snapshot.query_status.for_section(section).ok,
            "error": snapshot.query_status.for_section(section).error,
        }
        for section in ("account", "positions", "orders", "trades")
    }
    queries_ok = all(section["ok"] for section in query_status.values())
    safety_ok = (
        safety.order_submission_enabled is False
        and safety.cancel_enabled is False
        and safety.passorder_invoked is False
        and safety.cancel_invoked is False
    )
    return {
        "ok": queries_ok and safety_ok,
        "validation_result": "valid" if queries_ok and safety_ok else "valid_snapshot_with_failed_query_or_safety_flag",
        "snapshot_timestamp": snapshot.generated_at.isoformat(),
        "snapshot_age_seconds": round(snapshot.age_seconds(observed_at), 3),
        "sequence": snapshot.sequence,
        "snapshot_id": snapshot.snapshot_id,
        "provider": snapshot.provider,
        "provider_mode": config.qmt_builtin_bridge.provider_mode.value,
        "account_status": snapshot.account_status,
        "trading_date": snapshot.qmt_trading_date,
        "total_assets": account.total_assets if account is not None else None,
        "available_cash": account.available_cash if account is not None else None,
        "position_count": len(snapshot.positions),
        "order_count": len(snapshot.orders),
        "trade_count": len(snapshot.trades),
        "query_status": query_status,
        "read_only": safety_ok,
        "order_submission_enabled": safety.order_submission_enabled,
        "cancel_enabled": safety.cancel_enabled,
        "passorder_invoked": safety.passorder_invoked,
        "cancel_invoked": safety.cancel_invoked,
        "failure_count": len(snapshot.failures),
    }


__all__ = [
    "QmtBridgeInspectionError",
    "qmt_builtin_bridge_status_payload",
    "read_qmt_builtin_bridge_snapshot",
]
