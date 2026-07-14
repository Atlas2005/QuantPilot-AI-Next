from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import scripts.runtime_doctor_v1 as runtime_doctor_cli
import quantpilot_core.runtime_node.doctor as doctor_module
from quantpilot_core.qmt_builtin_bridge import (
    BRIDGE_VERSION,
    ENVIRONMENT_ID,
    LATEST_SNAPSHOT_RELATIVE_PATH,
    PROVIDER_ID,
    SCHEMA_VERSION,
    TEMP_SNAPSHOT_RELATIVE_PATH,
    AccountRecord,
    QmtBridgeSnapshot,
    QueryStatus,
    QueryStatusBundle,
    ReadOnlySafetyState,
    RuntimeMetadata,
    redact_account_identity,
    serialize_snapshot,
    snapshot_to_mapping,
)
from quantpilot_core.runtime_node.config import (
    BrokerProvider,
    QmtBuiltinBridgeConfig,
    RuntimeConfig,
)
from quantpilot_core.runtime_node.doctor import (
    _qmt_builtin_bridge_checks,
    collect_runtime_diagnostics,
)


_BINDING_KEY = bytes(range(32))
_KEY_BYTES = _BINDING_KEY.hex().encode("ascii")
_ACCOUNT_BINDING = redact_account_identity(
    "offline-provisioning-fixture",
    binding_key=_BINDING_KEY,
)


def _snapshot(*, generated_at: datetime | None = None) -> QmtBridgeSnapshot:
    observed_at = generated_at or datetime.now(timezone.utc) - timedelta(seconds=2)
    return QmtBridgeSnapshot(
        schema_version=SCHEMA_VERSION,
        bridge_version=BRIDGE_VERSION,
        generated_at=observed_at,
        sequence=1,
        snapshot_id="qmt-1",
        qmt_trading_date="20260714",
        provider=PROVIDER_ID,
        environment=ENVIRONMENT_ID,
        redacted_account_id=_ACCOUNT_BINDING,
        account_type="STOCK",
        account_status="connected",
        account=AccountRecord(
            redacted_account_id=_ACCOUNT_BINDING,
            account_type="STOCK",
            enabled=True,
            login_state="connected",
            trading_date="20260714",
            total_assets=100_000.0,
            available_cash=80_000.0,
            withdrawable_cash=80_000.0,
            frozen_cash=0.0,
            frozen_commission=0.0,
            stock_market_value=20_000.0,
            fund_market_value=0.0,
            bond_market_value=0.0,
            total_instrument_value=20_000.0,
            position_profit=0.0,
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
        source_field_provenance={
            "account": {},
            "positions": {},
            "orders": {},
            "trades": {},
        },
        safety=ReadOnlySafetyState(),
        failures=(),
    )


def _config(
    tmp_path: Path,
    bridge_root: Path,
    *,
    expected_account_type: str = "STOCK",
    expected_redacted_account_id: str = _ACCOUNT_BINDING,
) -> RuntimeConfig:
    return RuntimeConfig(
        platform="windows",
        broker_provider=BrokerProvider.QMT_BUILTIN_BRIDGE,
        qmt_builtin_bridge=QmtBuiltinBridgeConfig(
            bridge_root=bridge_root,
            max_snapshot_age_seconds=60,
            expected_account_type=expected_account_type,
            expected_redacted_account_id=expected_redacted_account_id,
        ),
        runtime_home=tmp_path / "runtime",
        reporting_enabled=False,
        grafana_enabled=False,
    )


def _checks(config: RuntimeConfig, *, provisioning: bool) -> dict[str, object]:
    return {
        check.name: check
        for check in _qmt_builtin_bridge_checks(
            config,
            allow_missing_qmt_snapshot_during_provisioning=provisioning,
        )
    }


def _write_key(bridge_root: Path, content: bytes = _KEY_BYTES) -> Path:
    key_path = bridge_root / "state" / "account_binding_key_v1.hex"
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_bytes(content)
    return key_path


def _write_payload(bridge_root: Path, payload: object) -> Path:
    snapshot_path = bridge_root / LATEST_SNAPSHOT_RELATIVE_PATH
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        snapshot_path.write_text(payload, encoding="utf-8")
    else:
        snapshot_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return snapshot_path


def test_normal_missing_snapshot_remains_strict(tmp_path: Path) -> None:
    bridge_root = tmp_path / "bridge"
    bridge_root.mkdir()
    _write_key(bridge_root)

    checks = _checks(_config(tmp_path, bridge_root), provisioning=False)

    assert checks["qmt_builtin_bridge.snapshot"].status == "NOT_READY"
    assert "MissingSnapshotError" in checks["qmt_builtin_bridge.snapshot"].detail
    assert checks["broker"].status == "NOT_READY"
    assert "qmt_builtin_bridge.account_binding_key" not in checks


def test_provisioning_allows_only_a_genuinely_absent_first_snapshot(tmp_path: Path) -> None:
    bridge_root = tmp_path / "bridge"
    bridge_root.mkdir()
    _write_key(bridge_root)

    checks = _checks(_config(tmp_path, bridge_root), provisioning=True)

    assert checks["qmt_builtin_bridge.directory"].status == "READY"
    assert checks["qmt_builtin_bridge.account_binding_key"].status == "READY"
    assert checks["qmt_builtin_bridge.snapshot"].status == "EXPECTED"
    assert checks["qmt_builtin_bridge.snapshot"].detail == "first exporter snapshot is pending"
    assert checks["qmt_builtin_bridge.read_only"].status == "EXPECTED"
    assert checks["broker"].status == "EXPECTED"
    assert "first read-only snapshot pending" in checks["broker"].detail


def test_provisioning_does_not_allow_a_missing_bridge_directory(tmp_path: Path) -> None:
    bridge_root = tmp_path / "missing-bridge"

    checks = _checks(_config(tmp_path, bridge_root), provisioning=True)

    assert checks["qmt_builtin_bridge.directory"].status == "NOT_READY"
    assert checks["qmt_builtin_bridge.snapshot"].status == "NOT_CHECKED"
    assert checks["broker"].status == "NOT_READY"
    assert "qmt_builtin_bridge.account_binding_key" not in checks


@pytest.mark.parametrize(
    ("case", "expected_error"),
    [
        ("malformed_json", "MalformedSnapshotError"),
        ("unsupported_schema", "UnsupportedSchemaError"),
        ("unsupported_bridge_version", "UnsupportedSchemaError"),
        ("stale", "StaleSnapshotError"),
        ("future", "InvalidSnapshotValueError"),
        ("unsafe", "InvalidSnapshotValueError"),
        ("account_binding_mismatch", "AccountIdentityMismatchError"),
        ("account_type_mismatch", "InvalidSnapshotValueError"),
    ],
)
def test_provisioning_keeps_completed_snapshot_validation_errors_fatal(
    tmp_path: Path,
    case: str,
    expected_error: str,
) -> None:
    bridge_root = tmp_path / "bridge"
    bridge_root.mkdir()
    _write_key(bridge_root)
    config = _config(tmp_path, bridge_root)

    if case == "malformed_json":
        _write_payload(bridge_root, "{")
    else:
        snapshot = _snapshot()
        payload = snapshot_to_mapping(snapshot)
        if case == "unsupported_schema":
            payload["schema_version"] = 2
        elif case == "unsupported_bridge_version":
            payload["bridge_version"] = "qmt_builtin_readonly_bridge_v2"
        elif case == "stale":
            payload["generated_at"] = (
                datetime.now(timezone.utc) - timedelta(minutes=10)
            ).isoformat().replace("+00:00", "Z")
        elif case == "future":
            payload["generated_at"] = (
                datetime.now(timezone.utc) + timedelta(minutes=10)
            ).isoformat().replace("+00:00", "Z")
        elif case == "unsafe":
            payload["safety"]["order_submission_enabled"] = True
        elif case == "account_binding_mismatch":
            other_binding = redact_account_identity(
                "different-offline-account",
                binding_key=_BINDING_KEY,
            )
            config = _config(
                tmp_path,
                bridge_root,
                expected_redacted_account_id=other_binding,
            )
        elif case == "account_type_mismatch":
            config = _config(tmp_path, bridge_root, expected_account_type="CREDIT")
        _write_payload(bridge_root, payload)

    checks = _checks(config, provisioning=True)

    assert "qmt_builtin_bridge.account_binding_key" not in checks
    assert checks["qmt_builtin_bridge.snapshot"].status == "NOT_READY"
    assert expected_error in checks["qmt_builtin_bridge.snapshot"].detail
    assert checks["broker"].status == "NOT_READY"


def test_provisioning_keeps_temp_only_snapshot_fatal(tmp_path: Path) -> None:
    bridge_root = tmp_path / "bridge"
    bridge_root.mkdir()
    _write_key(bridge_root)
    temporary_path = bridge_root / TEMP_SNAPSHOT_RELATIVE_PATH
    temporary_path.parent.mkdir(parents=True)
    temporary_path.write_text("{}", encoding="utf-8")

    checks = _checks(_config(tmp_path, bridge_root), provisioning=True)

    assert checks["qmt_builtin_bridge.snapshot"].status == "NOT_READY"
    assert "IncompleteAtomicWriteError" in checks["qmt_builtin_bridge.snapshot"].detail
    assert checks["broker"].status == "NOT_READY"


@pytest.mark.parametrize("occupied_path", ["completed", "temporary"])
def test_provisioning_requires_both_snapshot_paths_to_be_truly_absent(
    tmp_path: Path,
    occupied_path: str,
) -> None:
    bridge_root = tmp_path / "bridge"
    bridge_root.mkdir()
    _write_key(bridge_root)
    relative = (
        LATEST_SNAPSHOT_RELATIVE_PATH
        if occupied_path == "completed"
        else TEMP_SNAPSHOT_RELATIVE_PATH
    )
    path = bridge_root / relative
    path.mkdir(parents=True)

    checks = _checks(_config(tmp_path, bridge_root), provisioning=True)

    assert checks["qmt_builtin_bridge.snapshot"].status == "NOT_READY"
    assert checks["broker"].status == "NOT_READY"


def test_provisioning_keeps_failed_snapshot_queries_fatal(tmp_path: Path) -> None:
    bridge_root = tmp_path / "bridge"
    bridge_root.mkdir()
    _write_key(bridge_root)
    payload = snapshot_to_mapping(_snapshot())
    payload["query_status"]["positions"] = {
        "ok": False,
        "error": "qmt_query_failed",
    }
    payload["failures"] = [
        {
            "section": "positions",
            "code": "qmt_query_failed",
            "message": "QMT read-only positions query failed",
            "exception_type": "RuntimeError",
        }
    ]
    _write_payload(bridge_root, payload)

    checks = _checks(_config(tmp_path, bridge_root), provisioning=True)

    assert checks["qmt_builtin_bridge.snapshot"].status == "NOT_READY"
    assert checks["qmt_builtin_bridge.records"].status == "NOT_READY"
    assert checks["broker"].status == "NOT_READY"


@pytest.mark.parametrize(
    "key_content",
    [
        None,
        b"",
        b"a" * 63,
        b"A" * 64,
        b"g" * 64,
        b"a" * 64 + b"\n",
        b"a" * 65,
    ],
)
def test_provisioning_rejects_missing_empty_malformed_or_oversized_key(
    tmp_path: Path,
    key_content: bytes | None,
) -> None:
    bridge_root = tmp_path / "bridge"
    bridge_root.mkdir()
    if key_content is not None:
        _write_key(bridge_root, key_content)

    checks = _checks(_config(tmp_path, bridge_root), provisioning=True)

    key_check = checks["qmt_builtin_bridge.account_binding_key"]
    assert key_check.status == "NOT_READY"
    assert key_check.detail == "local account binding key is missing or invalid"
    assert checks["qmt_builtin_bridge.snapshot"].status == "NOT_READY"
    assert checks["broker"].status == "NOT_READY"
    assert "account_binding_key_v1.hex" not in key_check.detail
    if key_content:
        assert key_content.decode("ascii", "ignore") not in key_check.detail


def test_provisioning_rejects_an_unreadable_key_without_disclosing_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bridge_root = tmp_path / "bridge"
    bridge_root.mkdir()
    key_path = _write_key(bridge_root)
    original_open = Path.open

    def denied_open(path: Path, *args, **kwargs):
        if path == key_path:
            raise PermissionError("fixture denial")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", denied_open)

    checks = _checks(_config(tmp_path, bridge_root), provisioning=True)

    assert checks["qmt_builtin_bridge.account_binding_key"].status == "NOT_READY"
    assert checks["qmt_builtin_bridge.snapshot"].status == "NOT_READY"
    assert _KEY_BYTES.decode("ascii") not in checks["qmt_builtin_bridge.account_binding_key"].detail


def test_provisioning_key_gate_applies_to_valid_snapshot_but_normal_mode_is_unchanged(
    tmp_path: Path,
) -> None:
    bridge_root = tmp_path / "bridge"
    bridge_root.mkdir()
    snapshot_path = bridge_root / LATEST_SNAPSHOT_RELATIVE_PATH
    snapshot_path.parent.mkdir(parents=True)
    snapshot_path.write_text(serialize_snapshot(_snapshot()), encoding="utf-8")
    config = _config(tmp_path, bridge_root)

    normal = _checks(config, provisioning=False)
    provisioning = _checks(config, provisioning=True)

    assert normal["qmt_builtin_bridge.snapshot"].status == "READY"
    assert "qmt_builtin_bridge.account_binding_key" not in normal
    assert provisioning["qmt_builtin_bridge.account_binding_key"].status == "NOT_READY"
    assert provisioning["qmt_builtin_bridge.snapshot"].status == "READY"
    assert provisioning["broker"].status == "NOT_READY"


def test_provisioning_does_not_read_key_under_repository_local_bridge_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repository"
    bridge_root = repository_root / "bridge"
    bridge_root.mkdir(parents=True)
    _write_key(bridge_root)
    monkeypatch.setenv("QUANTPILOT_REPOSITORY_ROOT", str(repository_root))

    def forbidden_key_read(_bridge_root: Path) -> bool:
        raise AssertionError("repository-local key must not be read")

    monkeypatch.setattr(
        doctor_module,
        "_valid_qmt_provisioning_binding_key",
        forbidden_key_read,
    )

    checks = _checks(_config(tmp_path, bridge_root), provisioning=True)

    assert checks["qmt_builtin_bridge.snapshot"].status == "NOT_READY"
    assert "QmtBridgeInspectionError" in checks["qmt_builtin_bridge.snapshot"].detail
    assert "qmt_builtin_bridge.account_binding_key" not in checks
    assert checks["broker"].status == "NOT_READY"


def test_unreadable_existing_completed_snapshot_cannot_be_relaxed_as_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bridge_root = tmp_path / "bridge"
    bridge_root.mkdir()
    _write_key(bridge_root)
    completed = bridge_root / LATEST_SNAPSHOT_RELATIVE_PATH
    completed.parent.mkdir(parents=True)
    completed.write_text("{}", encoding="utf-8")
    original_read_text = Path.read_text

    def denied_read(path: Path, *args, **kwargs):
        if path == completed:
            raise PermissionError("fixture denial")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", denied_read)

    checks = _checks(_config(tmp_path, bridge_root), provisioning=True)

    assert checks["qmt_builtin_bridge.snapshot"].status == "NOT_READY"
    assert checks["qmt_builtin_bridge.snapshot"].detail == (
        "QMT provisioning state is incomplete or invalid"
    )
    assert "qmt_builtin_bridge.account_binding_key" not in checks
    assert checks["broker"].status == "NOT_READY"


def test_provider_none_is_unchanged_when_provisioning_flag_is_set(tmp_path: Path) -> None:
    config = RuntimeConfig(
        platform="windows",
        broker_provider=BrokerProvider.NONE,
        runtime_home=tmp_path / "runtime",
        reporting_enabled=False,
        grafana_enabled=False,
    )

    normal = {
        check.name: check
        for check in collect_runtime_diagnostics(config, probe_services=False)
    }
    provisioning = {
        check.name: check
        for check in collect_runtime_diagnostics(
            config,
            probe_services=False,
            allow_missing_qmt_snapshot_during_provisioning=True,
        )
    }

    assert normal["broker"] == provisioning["broker"]
    assert normal["broker"].status == "EXPECTED"
    assert not any(name.startswith("qmt_builtin_bridge.") for name in provisioning)


def test_cli_strict_exit_codes_and_output_are_narrowly_opt_in(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bridge_root = tmp_path / "bridge"
    bridge_root.mkdir()
    _write_key(bridge_root)
    config = _config(tmp_path, bridge_root)

    class FixtureRuntimeConfig:
        @classmethod
        def from_environment(cls) -> RuntimeConfig:
            return config

    def focused_collect(passed_config: RuntimeConfig, **kwargs):
        assert passed_config is config
        return tuple(
            _qmt_builtin_bridge_checks(
                passed_config,
                allow_missing_qmt_snapshot_during_provisioning=kwargs[
                    "allow_missing_qmt_snapshot_during_provisioning"
                ],
            )
        )

    monkeypatch.setattr(runtime_doctor_cli, "RuntimeConfig", FixtureRuntimeConfig)
    monkeypatch.setattr(runtime_doctor_cli, "collect_runtime_diagnostics", focused_collect)
    monkeypatch.setenv("TUSHARE_TOKEN", "offline-fixture-token")

    strict_arguments = ["--format", "json", "--strict", "--skip-services"]
    assert runtime_doctor_cli.main(strict_arguments) == 1
    strict_payload = json.loads(capsys.readouterr().out)
    assert strict_payload["ok"] is False
    strict_checks = {check["name"]: check for check in strict_payload["checks"]}
    assert strict_checks["qmt_builtin_bridge.snapshot"]["status"] == "NOT_READY"

    provisioning_arguments = strict_arguments + [
        "--allow-missing-qmt-snapshot-during-provisioning"
    ]
    assert runtime_doctor_cli.main(provisioning_arguments) == 0
    provisioning_payload = json.loads(capsys.readouterr().out)
    assert provisioning_payload["ok"] is True
    provisioning_checks = {
        check["name"]: check for check in provisioning_payload["checks"]
    }
    assert provisioning_checks["qmt_builtin_bridge.snapshot"] == {
        "name": "qmt_builtin_bridge.snapshot",
        "status": "EXPECTED",
        "detail": "first exporter snapshot is pending",
        "required": True,
    }

    temporary = bridge_root / TEMP_SNAPSHOT_RELATIVE_PATH
    temporary.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_text("{}", encoding="utf-8")
    assert runtime_doctor_cli.main(provisioning_arguments) == 1
    temp_payload = json.loads(capsys.readouterr().out)
    temp_checks = {check["name"]: check for check in temp_payload["checks"]}
    assert temp_checks["qmt_builtin_bridge.snapshot"]["status"] == "NOT_READY"
    assert "IncompleteAtomicWriteError" in temp_checks["qmt_builtin_bridge.snapshot"]["detail"]
