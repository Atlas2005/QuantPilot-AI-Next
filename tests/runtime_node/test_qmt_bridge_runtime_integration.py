from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from quantpilot_core.qmt_builtin_bridge import (
    BRIDGE_VERSION,
    ENVIRONMENT_ID,
    LATEST_SNAPSHOT_RELATIVE_PATH,
    PROVIDER_ID,
    SCHEMA_VERSION,
    AccountRecord,
    QmtBridgeSnapshot,
    QueryStatus,
    QueryStatusBundle,
    ReadOnlySafetyState,
    RuntimeMetadata,
    redact_account_identity,
    serialize_snapshot,
)
from quantpilot_core.runtime_node import BrokerProvider, QmtBuiltinBridgeConfig, RuntimeConfig, collect_runtime_diagnostics
from quantpilot_core.runtime_node.qmt_bridge_status import qmt_builtin_bridge_status_payload
from scripts.inspect_qmt_builtin_bridge_v1 import REPORT_FILE_NAME, inspection_payload, main


def _runtime_layout(home: Path) -> None:
    for name in ("config", "secrets", "logs", "state", "reports", "cache"):
        (home / name).mkdir(parents=True, exist_ok=True)


def _snapshot(now: datetime, *, sequence: int = 7) -> QmtBridgeSnapshot:
    redacted_id = redact_account_identity(
        "offline-integration-fixture",
        binding_key=bytes(range(32)),
    )
    return QmtBridgeSnapshot(
        schema_version=SCHEMA_VERSION,
        bridge_version=BRIDGE_VERSION,
        generated_at=now - timedelta(seconds=4),
        sequence=sequence,
        snapshot_id=f"qmt-{sequence}",
        qmt_trading_date="20260714",
        provider=PROVIDER_ID,
        environment=ENVIRONMENT_ID,
        redacted_account_id=redacted_id,
        account_type="STOCK",
        account_status="connected",
        account=AccountRecord(
            redacted_account_id=redacted_id,
            account_type="STOCK",
            enabled=True,
            login_state="connected",
            trading_date="20260714",
            total_assets=250000.0,
            available_cash=175000.5,
            withdrawable_cash=170000.0,
            frozen_cash=0.0,
            frozen_commission=0.0,
            stock_market_value=75000.0,
            fund_market_value=None,
            bond_market_value=None,
            total_instrument_value=75000.0,
            position_profit=1500.0,
            entrust_asset=0.0,
            assure_asset=None,
            provider_status="connected",
        ),
        positions=(),
        orders=(),
        trades=(),
        query_status=QueryStatusBundle(
            account=QueryStatus(ok=True),
            positions=QueryStatus(ok=True),
            orders=QueryStatus(ok=True),
            trades=QueryStatus(ok=True),
        ),
        runtime=RuntimeMetadata(
            python_version="3.6.8",
            python_implementation="CPython",
            qmt_runtime="builtin_python",
            qmt_version=None,
            platform="win32",
        ),
        source_field_provenance={"account": {}, "positions": {}, "orders": {}, "trades": {}},
        safety=ReadOnlySafetyState(),
        failures=(),
    )


def _write_snapshot(bridge_root: Path, snapshot: QmtBridgeSnapshot) -> Path:
    path = bridge_root / LATEST_SNAPSHOT_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_snapshot(snapshot), encoding="utf-8")
    return path


def _config(tmp_path: Path, bridge_root: Path, snapshot: QmtBridgeSnapshot) -> RuntimeConfig:
    runtime_home = tmp_path / "runtime"
    _runtime_layout(runtime_home)
    return RuntimeConfig(
        platform="windows",
        broker_provider=BrokerProvider.QMT_BUILTIN_BRIDGE,
        qmt_builtin_bridge=QmtBuiltinBridgeConfig(
            bridge_root=bridge_root,
            max_snapshot_age_seconds=60,
            expected_account_type="STOCK",
            expected_redacted_account_id=snapshot.redacted_account_id,
            polling_interval_seconds=5,
            heartbeat_interval_seconds=15,
        ),
        runtime_home=runtime_home,
        reporting_enabled=False,
        grafana_enabled=False,
    )


def test_qmt_status_projects_validated_snapshot_without_mutating_bridge(tmp_path: Path) -> None:
    now = datetime(2026, 7, 14, 6, 30, tzinfo=timezone.utc)
    snapshot = _snapshot(now)
    bridge_root = tmp_path / "bridge"
    snapshot_path = _write_snapshot(bridge_root, snapshot)
    config = _config(tmp_path, bridge_root, snapshot)
    before_files = sorted(path.relative_to(bridge_root) for path in bridge_root.rglob("*") if path.is_file())
    before_bytes = snapshot_path.read_bytes()

    payload = qmt_builtin_bridge_status_payload(config, now=now)

    assert payload == {
        "ok": True,
        "validation_result": "valid",
        "snapshot_timestamp": "2026-07-14T06:29:56+00:00",
        "snapshot_age_seconds": 4.0,
        "sequence": 7,
        "snapshot_id": "qmt-7",
        "provider": "qmt_builtin_bridge",
        "provider_mode": "simulation_signal",
        "account_status": "connected",
        "trading_date": "20260714",
        "total_assets": 250000.0,
        "available_cash": 175000.5,
        "position_count": 0,
        "order_count": 0,
        "trade_count": 0,
        "query_status": {
            "account": {"ok": True, "error": None},
            "positions": {"ok": True, "error": None},
            "orders": {"ok": True, "error": None},
            "trades": {"ok": True, "error": None},
        },
        "read_only": True,
        "order_submission_enabled": False,
        "cancel_enabled": False,
        "passorder_invoked": False,
        "cancel_invoked": False,
        "failure_count": 0,
    }
    assert snapshot_path.read_bytes() == before_bytes
    assert sorted(path.relative_to(bridge_root) for path in bridge_root.rglob("*") if path.is_file()) == before_files


def test_runtime_doctor_reports_qmt_snapshot_account_counts_and_safety(monkeypatch, tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    snapshot = _snapshot(now)
    bridge_root = tmp_path / "bridge"
    snapshot_path = _write_snapshot(bridge_root, snapshot)
    config = _config(tmp_path, bridge_root, snapshot)
    before_bytes = snapshot_path.read_bytes()

    checks = {check.name: check for check in collect_runtime_diagnostics(config, probe_services=False)}

    assert checks["qmt_builtin_bridge.directory"].status == "READY"
    assert checks["qmt_builtin_bridge.snapshot"].status == "READY"
    assert "age_seconds=" in checks["qmt_builtin_bridge.snapshot"].detail
    assert checks["qmt_builtin_bridge.account"].detail == "status=connected; trading_date=20260714"
    assert checks["qmt_builtin_bridge.records"].detail == "positions=0; orders=0; trades=0"
    assert checks["qmt_builtin_bridge.read_only"].status == "EXPECTED"
    assert "order_submission_enabled=false" in checks["qmt_builtin_bridge.read_only"].detail
    assert checks["broker"].status == "READY"
    assert snapshot_path.read_bytes() == before_bytes


def test_runtime_doctor_reports_temp_only_bridge_as_narrow_not_ready(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    snapshot = _snapshot(now)
    bridge_root = tmp_path / "bridge"
    temporary_path = bridge_root / "snapshots" / "latest_snapshot_v1.json.tmp"
    temporary_path.parent.mkdir(parents=True)
    temporary_path.write_text("{}", encoding="utf-8")
    config = _config(tmp_path, bridge_root, snapshot)

    checks = {check.name: check for check in collect_runtime_diagnostics(config, probe_services=False)}

    assert checks["qmt_builtin_bridge.snapshot"].status == "NOT_READY"
    assert "IncompleteAtomicWriteError" in checks["qmt_builtin_bridge.snapshot"].detail
    assert checks["qmt_builtin_bridge.read_only"].status == "EXPECTED"
    assert checks["broker"].status == "NOT_READY"
    assert temporary_path.read_text(encoding="utf-8") == "{}"


def test_inspection_cli_writes_bounded_report_and_never_prints_account_identity(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    now = datetime.now(timezone.utc)
    snapshot = _snapshot(now)
    bridge_root = tmp_path / "bridge"
    _write_snapshot(bridge_root, snapshot)
    runtime_home = tmp_path / "runtime"
    monkeypatch.setenv("QUANTPILOT_RUNTIME_HOME", str(runtime_home))
    monkeypatch.setenv("QUANTPILOT_BROKER_PROVIDER", "qmt_builtin_bridge")
    monkeypatch.setenv("QUANTPILOT_QMT_BRIDGE_ROOT", str(bridge_root))
    monkeypatch.setenv("QUANTPILOT_QMT_MAX_SNAPSHOT_AGE_SECONDS", "60")
    monkeypatch.setenv("QUANTPILOT_QMT_EXPECTED_ACCOUNT_TYPE", "STOCK")
    monkeypatch.setenv("QUANTPILOT_QMT_EXPECTED_REDACTED_ACCOUNT_ID", snapshot.redacted_account_id)

    assert main(["--format", "json"]) == 0
    output = capsys.readouterr().out
    payload = json.loads(output)
    report_path = runtime_home / "reports" / REPORT_FILE_NAME

    assert payload["ok"] is True
    assert payload["report_path"] == str(report_path.resolve())
    assert json.loads(report_path.read_text(encoding="utf-8")) == payload
    assert snapshot.redacted_account_id not in output
    assert "offline-integration-fixture" not in output
    assert "order_submission_enabled" in output
    assert "cancel_enabled" in output


def test_inspection_failure_remains_read_only_and_produces_concise_report(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    bridge_root = tmp_path / "bridge"
    bridge_root.mkdir()
    runtime_home = tmp_path / "runtime"
    monkeypatch.setenv("QUANTPILOT_RUNTIME_HOME", str(runtime_home))
    monkeypatch.setenv("QUANTPILOT_BROKER_PROVIDER", "qmt_builtin_bridge")
    monkeypatch.setenv("QUANTPILOT_QMT_BRIDGE_ROOT", str(bridge_root))

    assert main(["--format", "json"]) == 1
    payload = json.loads(capsys.readouterr().out)

    assert payload["validation_result"] == "invalid:MissingSnapshotError"
    assert payload["read_only"] is True
    assert payload["order_submission_enabled"] is False
    assert payload["cancel_enabled"] is False
    assert "account" not in payload
    assert Path(payload["report_path"]).is_file()


def test_inspection_payload_refuses_provider_none_without_touching_bridge(tmp_path: Path) -> None:
    bridge_root = tmp_path / "bridge"
    bridge_root.mkdir()
    config = RuntimeConfig(
        broker_provider=BrokerProvider.NONE,
        qmt_builtin_bridge=QmtBuiltinBridgeConfig(bridge_root=bridge_root),
        runtime_home=tmp_path / "runtime",
    )

    payload = inspection_payload(config)

    assert payload["ok"] is False
    assert payload["validation_result"] == "invalid:QmtBridgeInspectionError"
    assert payload["provider"] == "none"
    assert list(bridge_root.iterdir()) == []


def test_inspection_refuses_repository_local_bridge_root(monkeypatch, tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    bridge_root = repository / "runtime-bridge"
    bridge_root.mkdir(parents=True)
    monkeypatch.setenv("QUANTPILOT_REPOSITORY_ROOT", str(repository))
    config = RuntimeConfig(
        broker_provider=BrokerProvider.QMT_BUILTIN_BRIDGE,
        qmt_builtin_bridge=QmtBuiltinBridgeConfig(bridge_root=bridge_root),
        runtime_home=tmp_path / "runtime",
    )

    payload = inspection_payload(config)

    assert payload["ok"] is False
    assert payload["validation_result"] == "invalid:QmtBridgeInspectionError"
    assert "outside the Git repository" in payload["error"]
    assert list(bridge_root.iterdir()) == []
