from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from quantpilot_core.qmt_builtin_bridge import (
    ACCOUNT_BINDING_KEY_BYTES,
    MAX_ACCOUNT_ID_UTF8_BYTES,
    AccountBindingKeyError,
    AccountIdentityMismatchError,
    AccountIdentityRedactionError,
    DuplicateSequenceError,
    IncompleteAtomicWriteError,
    InvalidSnapshotValueError,
    LATEST_SNAPSHOT_RELATIVE_PATH,
    MalformedSnapshotError,
    MissingSnapshotError,
    OrderSubmissionNotEnabledError,
    QmtBuiltinBridgeReader,
    QmtBuiltinReadOnlyBridge,
    ReadOnlyBridgeError,
    RegressingSequenceError,
    SequenceTracker,
    StaleSnapshotError,
    TEMP_SNAPSHOT_RELATIVE_PATH,
    UnsupportedSchemaError,
    bounded_provider_metadata,
    is_redacted_account_identity,
    redact_account_identity,
    serialize_snapshot,
    snapshot_from_mapping,
    validate_account_binding_key,
)


NOW = datetime(2026, 7, 14, 6, 30, tzinfo=timezone.utc)
RAW_ACCOUNT_ID = "offline-test-account-126"
ACCOUNT_BINDING_KEY = bytes(range(ACCOUNT_BINDING_KEY_BYTES))
ACCOUNT_BINDING = redact_account_identity(
    RAW_ACCOUNT_ID,
    binding_key=ACCOUNT_BINDING_KEY,
)


def _valid_payload(*, sequence: int = 17) -> dict[str, object]:
    return {
        "schema_version": 1,
        "bridge_version": "qmt_builtin_readonly_bridge_v1",
        "generated_at": "2026-07-14T06:29:45Z",
        "sequence": sequence,
        "snapshot_id": f"qmt-{sequence}",
        "qmt_trading_date": "20260714",
        "provider": "qmt_builtin_bridge",
        "environment": "simulation_signal",
        "redacted_account_id": ACCOUNT_BINDING,
        "account_type": "STOCK",
        "account_status": "ONLINE",
        "account": {
            "redacted_account_id": ACCOUNT_BINDING,
            "account_type": "STOCK",
            "enabled": True,
            "login_state": "ONLINE",
            "trading_date": "20260714",
            "total_assets": 1_250_000.5,
            "available_cash": 725_000.25,
            "withdrawable_cash": 700_000.0,
            "frozen_cash": 100.0,
            "frozen_commission": 5.0,
            "stock_market_value": 525_000.25,
            "fund_market_value": 0.0,
            "bond_market_value": 0.0,
            "total_instrument_value": 525_000.25,
            "position_profit": -1_250.75,
            "entrust_asset": 0.0,
            "assure_asset": 1_250_000.5,
            "provider_status": "ONLINE",
            "provider_metadata": {"m_nBrokerType": 42},
        },
        "positions": [
            {
                "symbol": "600000.SH",
                "instrument_name": "Pudong Bank",
                "total_quantity": 1000,
                "available_quantity": 800,
                "frozen_quantity": 200,
                "on_road_quantity": 0,
                "yesterday_quantity": 1000,
                "average_cost": 10.5,
                "open_cost": 10.4,
                "latest_price": 10.7,
                "market_value": 10_700.0,
                "floating_profit": 200.0,
                "profit_ratio": 0.019,
                "trading_day": "20260714",
                "provider_metadata": {"m_nHedgeFlag": 1},
            }
        ],
        "orders": [
            {
                "broker_order_reference": "17",
                "system_order_id": "SYS-17",
                "symbol": "600000.SH",
                "side": "BUY",
                "operation_label": "BUY",
                "order_price_type": 11,
                "limit_price": 10.7,
                "original_quantity": 100,
                "filled_quantity": 80,
                "remaining_quantity": 20,
                "cancelled_quantity": 0,
                "average_traded_price": 10.69,
                "order_status": 50,
                "submission_status": 49,
                "error_id": 0,
                "error_message": None,
                "cancel_information": None,
                "insert_date": "20260714",
                "insert_time": "142945",
                "trade_amount": 855.2,
                "investment_remark": "shadow-observation",
                "provider_metadata": {},
            }
        ],
        "trades": [
            {
                "trade_id": "TRADE-17",
                "order_reference": "17",
                "system_order_id": "SYS-17",
                "symbol": "600000.SH",
                "side": "BUY",
                "operation_label": "BUY",
                "fill_price": 10.69,
                "fill_quantity": 80,
                "fill_amount": 855.2,
                "commission": 5.0,
                "trade_date": "20260714",
                "trade_time": "142946",
                "investment_remark": "shadow-observation",
                "provider_metadata": {},
            }
        ],
        "query_status": {
            "account": {"ok": True, "error": None},
            "positions": {"ok": True, "error": None},
            "orders": {"ok": True, "error": None},
            "trades": {"ok": True, "error": None},
        },
        "runtime": {
            "python_version": "3.6.8",
            "python_implementation": "CPython",
            "qmt_runtime": "builtin_python",
            "qmt_version": None,
            "platform": "win32",
            "metadata": {"architecture": "64-bit"},
        },
        "source_field_provenance": {
            "account": {"total_assets": ["m_dBalance", "m_dAssetBalance"]},
            "positions": {"total_quantity": ["m_nVolume"]},
            "orders": {"broker_order_reference": ["m_strOrderRef", "m_nRef"]},
            "trades": {"commission": ["m_dCommission", "m_dComission"]},
        },
        "safety": {
            "order_submission_enabled": False,
            "cancel_enabled": False,
            "passorder_invoked": False,
            "cancel_invoked": False,
        },
        "failures": [],
    }


def _write_completed(root, payload: object) -> None:
    path = root / LATEST_SNAPSHOT_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _parse(payload: object, **kwargs):
    return snapshot_from_mapping(
        payload,
        max_snapshot_age_seconds=60,
        now=NOW,
        **kwargs,
    )


def test_reader_returns_deeply_stable_canonical_records_and_deterministic_json(tmp_path) -> None:
    _write_completed(tmp_path, _valid_payload())
    temporary = tmp_path / TEMP_SNAPSHOT_RELATIVE_PATH
    temporary.write_text("not completed JSON", encoding="utf-8")

    snapshot = QmtBuiltinBridgeReader(
        tmp_path,
        max_snapshot_age_seconds=60,
        expected_account_type="STOCK",
        expected_redacted_account_id=ACCOUNT_BINDING,
    ).read_latest(now=NOW)

    assert snapshot.snapshot_id == "qmt-17"
    assert snapshot.age_seconds(NOW) == 15.0
    assert snapshot.account is not None
    assert snapshot.account.total_assets == 1_250_000.5
    assert snapshot.positions[0].symbol == "600000.SH"
    assert snapshot.orders[0].remaining_quantity == 20
    assert snapshot.trades[0].commission == 5.0
    assert snapshot.source_path == tmp_path / LATEST_SNAPSHOT_RELATIVE_PATH
    assert serialize_snapshot(snapshot) == serialize_snapshot(snapshot)
    assert json.loads(serialize_snapshot(snapshot))["snapshot_id"] == "qmt-17"

    with pytest.raises(FrozenInstanceError):
        snapshot.sequence = 18  # type: ignore[misc]
    with pytest.raises(TypeError):
        snapshot.account.provider_metadata["new"] = 1  # type: ignore[index]
    with pytest.raises(TypeError):
        snapshot.source_field_provenance["account"]["new"] = ("field",)  # type: ignore[index]


def test_temp_only_is_incomplete_and_missing_completed_is_distinct(tmp_path) -> None:
    temporary = tmp_path / TEMP_SNAPSHOT_RELATIVE_PATH
    temporary.parent.mkdir(parents=True)
    temporary.write_text("{}", encoding="utf-8")
    reader = QmtBuiltinBridgeReader(tmp_path, max_snapshot_age_seconds=60)

    with pytest.raises(IncompleteAtomicWriteError) as incomplete:
        reader.read_latest(now=NOW)
    assert incomplete.value.code == "incomplete_atomic_write"

    temporary.unlink()
    with pytest.raises(MissingSnapshotError) as missing:
        reader.read_latest(now=NOW)
    assert missing.value.code == "missing_snapshot"


def test_malformed_and_unsupported_completed_snapshots_have_narrow_errors(tmp_path) -> None:
    completed = tmp_path / LATEST_SNAPSHOT_RELATIVE_PATH
    completed.parent.mkdir(parents=True)
    completed.write_text("{", encoding="utf-8")
    reader = QmtBuiltinBridgeReader(tmp_path, max_snapshot_age_seconds=60)
    with pytest.raises(MalformedSnapshotError) as malformed:
        reader.read_latest(now=NOW)
    assert malformed.value.code == "malformed_json"

    payload = _valid_payload()
    payload["schema_version"] = 2
    _write_completed(tmp_path, payload)
    with pytest.raises(UnsupportedSchemaError) as unsupported:
        reader.read_latest(now=NOW)
    assert unsupported.value.code == "unsupported_schema"


def test_stale_heartbeat_and_future_timestamp_are_rejected() -> None:
    stale = _valid_payload()
    stale["generated_at"] = "2026-07-14T06:00:00Z"
    with pytest.raises(StaleSnapshotError) as error:
        _parse(stale)
    assert error.value.code == "stale_heartbeat"

    future = _valid_payload()
    future["generated_at"] = (NOW + timedelta(minutes=6)).isoformat().replace("+00:00", "Z")
    with pytest.raises(InvalidSnapshotValueError):
        _parse(future)


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("account", "total_assets", float("nan")),
        ("account", "total_assets", 10**1000),
        ("positions", "total_quantity", -1),
        ("orders", "remaining_quantity", -1),
        ("trades", "fill_quantity", -1),
    ],
)
def test_non_finite_numbers_and_negative_quantities_are_rejected(
    section: str,
    field: str,
    value: object,
) -> None:
    payload = _valid_payload()
    target = payload[section]
    if isinstance(target, list):
        target[0][field] = value
    else:
        target[field] = value
    with pytest.raises(InvalidSnapshotValueError) as error:
        _parse(payload)
    assert error.value.code == "invalid_values"


def test_sequence_tracker_rejects_duplicate_and_regressing_completed_snapshots() -> None:
    tracker = SequenceTracker()
    _parse(_valid_payload(sequence=17), sequence_tracker=tracker)
    assert tracker.last_sequence == 17

    with pytest.raises(DuplicateSequenceError) as duplicate:
        _parse(_valid_payload(sequence=17), sequence_tracker=tracker)
    assert duplicate.value.code == "duplicate_sequence"

    with pytest.raises(RegressingSequenceError) as regressing:
        _parse(_valid_payload(sequence=16), sequence_tracker=tracker)
    assert regressing.value.code == "regressing_sequence"

    _parse(_valid_payload(sequence=18), sequence_tracker=tracker)
    assert tracker.last_snapshot_id == "qmt-18"


def test_account_binding_and_cross_field_mismatches_never_echo_identifiers() -> None:
    expected = redact_account_identity(
        "a-different-offline-account",
        binding_key=ACCOUNT_BINDING_KEY,
    )
    with pytest.raises(AccountIdentityMismatchError) as mismatch:
        _parse(_valid_payload(), expected_redacted_account_id=expected)
    message = str(mismatch.value)
    assert expected not in message
    assert ACCOUNT_BINDING not in message

    payload = _valid_payload()
    payload["account_status"] = "OFFLINE"
    with pytest.raises(InvalidSnapshotValueError):
        _parse(payload)


def test_failed_account_query_is_a_valid_heartbeat_only_with_null_account_state() -> None:
    payload = _valid_payload()
    payload["account"] = None
    payload["account_status"] = None
    payload["qmt_trading_date"] = None
    payload["query_status"]["account"] = {"ok": False, "error": "qmt_query_failed"}
    payload["failures"] = [
        {
            "section": "account",
            "code": "qmt_query_failed",
            "message": "QMT read-only account query failed",
            "exception_type": "RuntimeError",
        }
    ]

    snapshot = _parse(payload)
    assert snapshot.account is None
    assert snapshot.query_status.account.ok is False

    payload["account_status"] = "ONLINE"
    with pytest.raises(InvalidSnapshotValueError):
        _parse(payload)

    payload = _valid_payload()
    payload["query_status"]["account"] = {"ok": False, "error": "qmt_query_failed"}
    payload["failures"] = [
        {
            "section": "account",
            "code": "qmt_query_failed",
            "message": "QMT read-only account query failed",
            "exception_type": "RuntimeError",
        }
    ]
    with pytest.raises(InvalidSnapshotValueError):
        _parse(payload)


def test_failure_messages_are_fixed_and_cannot_carry_provider_data() -> None:
    payload = _valid_payload()
    payload["positions"] = []
    payload["query_status"]["positions"] = {"ok": False, "error": "qmt_query_failed"}
    payload["failures"] = [
        {
            "section": "positions",
            "code": "qmt_query_failed",
            "message": "query failed and exposed a raw account identifier",
            "exception_type": "RuntimeError",
        }
    ]
    with pytest.raises(InvalidSnapshotValueError):
        _parse(payload)


@pytest.mark.parametrize(
    "sensitive_key",
    [
        "m_strAccountID",
        "m_strAccountKey",
        "m_strStockHolder",
        "shareholder_id",
        "clientToken",
        "private_key",
        "customerEmail",
    ],
)
def test_sensitive_provider_metadata_is_never_returned(sensitive_key: str) -> None:
    payload = _valid_payload()
    payload["account"]["provider_metadata"][sensitive_key] = "forbidden"
    with pytest.raises(InvalidSnapshotValueError):
        _parse(payload)

    sanitized = bounded_provider_metadata(
        {sensitive_key: "forbidden", "m_nBrokerType": 42, "nested": {"ignored": True}}
    )
    assert sanitized == {"m_nBrokerType": 42}


def test_redaction_is_deterministic_bounded_and_never_contains_the_source() -> None:
    source = "synthetic-account-alpha"
    first = redact_account_identity(source, binding_key=ACCOUNT_BINDING_KEY)
    second = redact_account_identity(source, binding_key=ACCOUNT_BINDING_KEY)
    assert first == second
    assert first == "qmtacct-v1-58963c7445d88fa2237ed6cc"
    assert source not in first
    assert is_redacted_account_identity(first)
    assert not is_redacted_account_identity(source)


def test_account_binding_hmac_changes_with_account_or_key() -> None:
    account = "offline-account-a"
    other_account = "offline-account-b"
    other_key = bytes(reversed(range(ACCOUNT_BINDING_KEY_BYTES)))

    first = redact_account_identity(account, binding_key=ACCOUNT_BINDING_KEY)
    assert first == redact_account_identity(account, binding_key=ACCOUNT_BINDING_KEY)
    assert first != redact_account_identity(other_account, binding_key=ACCOUNT_BINDING_KEY)
    assert first != redact_account_identity(account, binding_key=other_key)


@pytest.mark.parametrize(
    "invalid_key",
    [
        None,
        b"",
        b"k" * 31,
        b"k" * 33,
        "00" * 32,
        object(),
    ],
)
def test_account_binding_key_validation_fails_closed(invalid_key: object) -> None:
    with pytest.raises(AccountBindingKeyError) as error:
        validate_account_binding_key(invalid_key)
    assert "k" * 31 not in str(error.value)

    with pytest.raises(AccountBindingKeyError):
        redact_account_identity("offline-account", binding_key=invalid_key)


def test_account_binding_key_validation_returns_an_immutable_exact_copy() -> None:
    source = bytearray(ACCOUNT_BINDING_KEY)
    normalized = validate_account_binding_key(source)
    source[0] = 255
    assert isinstance(normalized, bytes)
    assert len(normalized) == ACCOUNT_BINDING_KEY_BYTES
    assert normalized[0] == 0


@pytest.mark.parametrize(
    "invalid_account",
    [
        None,
        True,
        "",
        "   ",
        "\ud800",
        "a" * (MAX_ACCOUNT_ID_UTF8_BYTES + 1),
        "\u8d26" * (MAX_ACCOUNT_ID_UTF8_BYTES // 3 + 1),
    ],
)
def test_account_identity_input_validation_fails_closed(invalid_account: object) -> None:
    with pytest.raises(AccountIdentityRedactionError) as error:
        redact_account_identity(invalid_account, binding_key=ACCOUNT_BINDING_KEY)
    assert "offline-test-account" not in str(error.value)


def test_raw_account_and_binding_key_never_enter_serialized_snapshot() -> None:
    snapshot = _parse(_valid_payload())
    serialized = serialize_snapshot(snapshot)
    assert RAW_ACCOUNT_ID not in serialized
    assert ACCOUNT_BINDING_KEY.hex() not in serialized
    assert bytes(ACCOUNT_BINDING_KEY).decode("latin-1") not in serialized
    assert ACCOUNT_BINDING in serialized


def test_unknown_protocol_fields_and_external_runtime_labels_are_rejected() -> None:
    payload = _valid_payload()
    payload["raw_account"] = "must not pass"
    with pytest.raises(InvalidSnapshotValueError):
        _parse(payload)

    payload = _valid_payload()
    payload["runtime"]["qmt_runtime"] = "external_xtquant"
    with pytest.raises(InvalidSnapshotValueError):
        _parse(payload)


def test_all_mutation_attempts_fail_with_stable_read_only_codes(tmp_path) -> None:
    facade = QmtBuiltinReadOnlyBridge(
        QmtBuiltinBridgeReader(tmp_path, max_snapshot_age_seconds=60)
    )
    with pytest.raises(OrderSubmissionNotEnabledError) as submit:
        facade.submit_order(symbol="600000.SH", quantity=100)
    assert submit.value.code == "order_submission_not_enabled"

    with pytest.raises(OrderSubmissionNotEnabledError):
        facade.place_order(symbol="600000.SH", quantity=100)

    with pytest.raises(ReadOnlyBridgeError) as cancel:
        facade.cancel_order("broker-ref")
    assert cancel.value.code == "read_only_bridge"


def test_safety_flags_must_be_literal_false() -> None:
    payload = deepcopy(_valid_payload())
    payload["safety"]["order_submission_enabled"] = 0
    with pytest.raises(InvalidSnapshotValueError):
        _parse(payload)
