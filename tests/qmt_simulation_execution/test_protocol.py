from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from quantpilot_core.order_intent import OrderIntent
from quantpilot_core.qmt_simulation_execution import (
    AccountBindingMismatchError,
    ExpiredIntentError,
    FutureIntentError,
    IntentAuthenticationError,
    IntentConflictError,
    InvalidBridgeRootError,
    InvalidIntentError,
    InvalidResultError,
    InvalidStateError,
    InvalidStateTransitionError,
    MAX_INTENT_BYTES,
    MalformedArtifactError,
    QmtSimulationOrderIntent,
    RepositoryLocalPathError,
    build_signed_intent,
    build_signed_intent_from_order_intent,
    build_state,
    canonical_json_bytes,
    inspect_status,
    intent_from_mapping,
    intent_path,
    intent_to_mapping,
    read_intent,
    read_result,
    read_state,
    reconcile_broker_records,
    redact_account_id,
    result_to_reporting_facts,
    result_path,
    serialize_result,
    serialize_intent,
    state_from_result,
    state_from_mapping,
    verify_account_binding,
    write_intent_atomic,
    write_result_atomic,
    write_state_atomic,
)


NOW = datetime(2026, 7, 15, 1, 0, tzinfo=timezone.utc)
KEY = bytes(range(32))
RAW_ACCOUNT = "offline-simulation-account"
BINDING = redact_account_id(RAW_ACCOUNT, binding_key=KEY)


def _bridge(tmp_path: Path) -> Path:
    root = tmp_path / "qmt-bridge"
    (root / "state").mkdir(parents=True)
    (root / "state" / "account_binding_key_v1.hex").write_bytes(KEY.hex().encode("ascii"))
    return root


def _intent(**overrides: object) -> QmtSimulationOrderIntent:
    values: dict[str, object] = {
        "intent_id": "intent_127",
        "expected_redacted_account_id": BINDING,
        "symbol": "600000.SH",
        "side": "buy",
        "quantity": 100,
        "limit_price": 10,
        "source_order_digest": "a" * 64,
        "binding_key": KEY,
        "created_at": NOW,
        "ttl_seconds": 300,
        "run_label": "pr127-test",
        "validation_now": NOW,
    }
    values.update(overrides)
    return build_signed_intent(**values)  # type: ignore[arg-type]


def test_canonical_intent_is_stable_strict_and_authenticated() -> None:
    intent = _intent()
    encoded = serialize_intent(intent)
    assert encoded.endswith(b"\n")
    assert encoded == serialize_intent(intent)
    assert canonical_json_bytes(intent_to_mapping(intent), trailing_newline=True) == encoded
    assert json.loads(encoded)["limit_price"] == 10.0
    assert KEY.hex().encode("ascii") not in encoded
    assert RAW_ACCOUNT.encode("ascii") not in encoded

    parsed = intent_from_mapping(intent_to_mapping(intent), binding_key=KEY, now=NOW)
    assert parsed == intent
    with pytest.raises(FrozenInstanceError):
        parsed.quantity = 200  # type: ignore[misc]

    tampered = intent_to_mapping(intent)
    tampered["quantity"] = 200
    with pytest.raises(IntentAuthenticationError):
        intent_from_mapping(tampered, binding_key=KEY, now=NOW)
    unknown = intent_to_mapping(intent)
    unknown["extra"] = True
    with pytest.raises(InvalidIntentError):
        intent_from_mapping(unknown, binding_key=KEY, now=NOW)
    missing = intent_to_mapping(intent)
    del missing["quantity"]
    with pytest.raises(InvalidIntentError):
        intent_from_mapping(missing, binding_key=KEY, now=NOW)


def test_account_expiry_future_price_and_buy_lot_validation() -> None:
    intent = _intent()
    verify_account_binding(BINDING, raw_account_id=RAW_ACCOUNT, binding_key=KEY)
    with pytest.raises(AccountBindingMismatchError):
        verify_account_binding(BINDING, raw_account_id="other", binding_key=KEY)
    with pytest.raises(AccountBindingMismatchError):
        intent_from_mapping(
            intent_to_mapping(intent),
            binding_key=KEY,
            now=NOW,
            raw_account_id="other",
        )
    with pytest.raises(ExpiredIntentError):
        intent_from_mapping(
            intent_to_mapping(intent),
            binding_key=KEY,
            now=NOW + timedelta(minutes=6),
        )
    for price in (0, float("nan"), float("inf")):
        with pytest.raises(InvalidIntentError):
            _intent(limit_price=price)
    with pytest.raises(InvalidIntentError):
        _intent(quantity=99)
    with pytest.raises(InvalidIntentError):
        _intent(run_label="x" * 129)
    with pytest.raises(FutureIntentError):
        _intent(created_at=NOW + timedelta(seconds=301), validation_now=NOW)


def test_atomic_immutable_write_read_and_repository_rejection(tmp_path: Path) -> None:
    root = _bridge(tmp_path)
    intent = _intent()
    path = write_intent_atomic(root, intent, now=NOW)
    original = path.read_bytes()
    assert path == intent_path(root, intent.intent_id)
    assert write_intent_atomic(root, intent, now=NOW) == path
    assert path.read_bytes() == original
    assert read_intent(root, intent.intent_id, now=NOW) == intent

    conflict = _intent(source_order_digest="b" * 64)
    with pytest.raises(IntentConflictError):
        write_intent_atomic(root, conflict, now=NOW)

    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    with pytest.raises(RepositoryLocalPathError):
        write_intent_atomic(repo / "runtime", intent, binding_key=KEY, now=NOW)


def test_execution_child_symlink_is_rejected(tmp_path: Path) -> None:
    root = _bridge(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "execution").symlink_to(outside, target_is_directory=True)
    with pytest.raises(InvalidBridgeRootError):
        write_intent_atomic(root, _intent(), now=NOW)


def test_intent_reader_rejects_oversize_duplicate_and_noncanonical_files(
    tmp_path: Path,
) -> None:
    root = _bridge(tmp_path)
    intent = _intent()
    path = intent_path(root, intent.intent_id)
    path.parent.mkdir(parents=True)

    path.write_bytes(b"x" * (MAX_INTENT_BYTES + 1))
    with pytest.raises(InvalidIntentError):
        read_intent(root, intent.intent_id, now=NOW)

    noncanonical = json.dumps(intent_to_mapping(intent), sort_keys=True).encode("ascii")
    path.write_bytes(noncanonical)
    with pytest.raises(InvalidIntentError):
        read_intent(root, intent.intent_id, now=NOW)

    canonical = serialize_intent(intent)
    duplicate = canonical.replace(b"{", b'{"schema_version":1,', 1)
    path.write_bytes(duplicate)
    with pytest.raises(MalformedArtifactError):
        read_intent(root, intent.intent_id, now=NOW)


def test_order_intent_adapter_uses_shares_identity_digest_and_label() -> None:
    upstream = OrderIntent(
        symbol="600000",
        side="buy",
        target_weight=0.1,
        target_shares=100,
        run_label="source-run",
        metadata={"order_id": "source_order_1", "source_order_digest": "c" * 64},
    )
    broker = build_signed_intent_from_order_intent(
        upstream,
        limit_price=10.5,
        expected_redacted_account_id=BINDING,
        binding_key=KEY,
        created_at=NOW,
        validation_now=NOW,
    )
    assert broker.intent_id == "source_order_1"
    assert broker.symbol == "600000.SH"
    assert broker.quantity == 100
    assert broker.run_label == "source-run"
    assert broker.source_order_digest == "c" * 64
    assert upstream.target_weight == 0.1
    with pytest.raises(InvalidIntentError):
        build_signed_intent_from_order_intent(
            OrderIntent(symbol="600000.SH", side="hold", target_weight=0.1),
            limit_price=10,
            expected_redacted_account_id=BINDING,
            binding_key=KEY,
            created_at=NOW,
            validation_now=NOW,
        )


@pytest.mark.parametrize(
    ("source_symbol", "broker_symbol"),
    [("510300", "510300.SH"), ("159915", "159915.SZ")],
)
def test_order_intent_adapter_infers_common_exchange_traded_fund_symbols(
    source_symbol: str, broker_symbol: str
) -> None:
    broker = build_signed_intent_from_order_intent(
        OrderIntent(symbol=source_symbol, side="buy", target_shares=100),
        limit_price=1.5,
        expected_redacted_account_id=BINDING,
        binding_key=KEY,
        created_at=NOW,
        validation_now=NOW,
    )
    assert broker.symbol == broker_symbol


def test_reconciliation_requires_readback_and_never_matches_unrelated_records() -> None:
    intent = _intent()
    pending = reconcile_broker_records(
        intent, [], [], passorder_attempted=True, generated_at=NOW
    )
    assert (pending.status, pending.failure_code) == (
        "uncertain",
        "broker_readback_pending",
    )
    unrelated = reconcile_broker_records(
        intent,
        [{"m_strRemark": "other", "m_nOrderStatus": 50}],
        [{"m_strRemark": "other", "m_nVolume": 100, "m_dPrice": 10}],
        passorder_attempted=False,
        generated_at=NOW,
    )
    assert unrelated.status == "received"

    acknowledged = reconcile_broker_records(
        intent,
        [
            {
                "m_strRemark": intent.intent_id,
                "m_strInstrumentID": "600000",
                "m_strExchangeID": "SSE",
                "m_nOffsetFlag": 48,
                "m_nVolumeTotalOriginal": 100,
                "m_nVolumeTraded": 0,
                "m_nOrderStatus": 50,
            }
        ],
        [],
        passorder_attempted=False,
        generated_at=NOW,
    )
    assert acknowledged.status == "broker_acknowledged"
    assert acknowledged.passorder_attempted is False
    bare_same_code = reconcile_broker_records(
        intent,
        [{"m_strRemark": intent.intent_id, "m_strInstrumentID": "600000"}],
        [],
        passorder_attempted=False,
        generated_at=NOW,
    )
    assert bare_same_code.status == "broker_acknowledged"
    bare_wrong_code = reconcile_broker_records(
        intent,
        [{"m_strRemark": intent.intent_id, "m_strInstrumentID": "000001"}],
        [],
        passorder_attempted=False,
        generated_at=NOW,
    )
    assert bare_wrong_code.failure_code == "broker_shape_mismatch"

    class ThrowingRemark:
        @property
        def m_strRemark(self):
            raise TypeError("provider detail must not cross the protocol")

    throwing = reconcile_broker_records(
        intent,
        [ThrowingRemark()],
        [],
        passorder_attempted=False,
        generated_at=NOW,
    )
    assert (throwing.status, throwing.failure_code) == (
        "uncertain",
        "broker_shape_mismatch",
    )


def test_reconciliation_fill_rejection_duplicate_and_shape_failures() -> None:
    intent = _intent()
    partial = reconcile_broker_records(
        intent,
        [],
        [{"m_strRemark": intent.intent_id, "m_strTradeID": "D1", "m_nVolume": 40, "m_dPrice": 10}],
        passorder_attempted=True,
        generated_at=NOW,
    )
    assert (partial.status, partial.filled_quantity, partial.deal_count) == (
        "partially_filled",
        40,
        1,
    )
    filled = reconcile_broker_records(
        intent,
        [],
        [
            {"m_strRemark": intent.intent_id, "m_strTradeID": "D1", "m_nVolume": 40, "m_dPrice": 10},
            {"m_strRemark": intent.intent_id, "m_strTradeID": "D2", "m_nVolume": 60, "m_dPrice": 11},
        ],
        passorder_attempted=True,
        generated_at=NOW,
    )
    assert filled.status == "filled"
    assert filled.average_fill_price == pytest.approx(10.6)

    rejected = reconcile_broker_records(
        intent,
        [{"m_strRemark": intent.intent_id, "m_nOrderSubmitStatus": 57}],
        [],
        passorder_attempted=True,
        generated_at=NOW,
    )
    assert (rejected.status, rejected.failure_code) == (
        "rejected",
        "broker_order_rejected",
    )
    duplicate = reconcile_broker_records(
        intent,
        [{"m_strRemark": intent.intent_id}, {"m_strRemark": intent.intent_id}],
        [],
        passorder_attempted=False,
        generated_at=NOW,
    )
    assert (duplicate.status, duplicate.failure_code) == (
        "uncertain",
        "multiple_broker_orders",
    )
    overflow = reconcile_broker_records(
        intent,
        [],
        [{"m_strRemark": intent.intent_id, "m_nVolume": 101, "m_dPrice": 10}],
        passorder_attempted=True,
        generated_at=NOW,
    )
    assert (overflow.status, overflow.failure_code, overflow.filled_quantity) == (
        "uncertain",
        "broker_quantity_exceeds_request",
        0,
    )
    mismatch = reconcile_broker_records(
        intent,
        [{"m_strRemark": intent.intent_id, "symbol": "000001.SZ"}],
        [],
        passorder_attempted=False,
        generated_at=NOW,
    )
    assert mismatch.failure_code == "broker_shape_mismatch"
    ambiguous_side = reconcile_broker_records(
        intent,
        [{"m_strRemark": intent.intent_id, "m_strOptName": "not buy"}],
        [],
        passorder_attempted=False,
        generated_at=NOW,
    )
    assert ambiguous_side.failure_code == "broker_shape_mismatch"
    masked_valid_side = reconcile_broker_records(
        intent,
        [
            {
                "m_strRemark": intent.intent_id,
                "m_nOperation": 999,
                "m_nOffsetFlag": 48,
            }
        ],
        [],
        passorder_attempted=False,
        generated_at=NOW,
    )
    assert masked_valid_side.status == "broker_acknowledged"
    conflicting_side = reconcile_broker_records(
        intent,
        [{"m_strRemark": intent.intent_id, "m_nOffsetFlag": 48, "m_nDirection": 49}],
        [],
        passorder_attempted=False,
        generated_at=NOW,
    )
    assert conflicting_side.failure_code == "broker_shape_mismatch"

    distinct_order_refs = reconcile_broker_records(
        intent,
        [],
        [
            {
                "m_strRemark": intent.intent_id,
                "m_strTradeID": "D3",
                "m_strOrderRef": "REF-1",
                "m_nVolume": 40,
                "m_dPrice": 10,
            },
            {
                "m_strRemark": intent.intent_id,
                "m_strTradeID": "D4",
                "m_strOrderRef": "REF-2",
                "m_nVolume": 60,
                "m_dPrice": 10,
            },
        ],
        passorder_attempted=True,
        generated_at=NOW,
    )
    assert distinct_order_refs.failure_code == "multiple_broker_orders"


def test_broker_status_text_is_fixed_and_never_serializes_provider_message() -> None:
    intent = _intent()
    secret = "rejected password broker-secret-value"
    result = reconcile_broker_records(
        intent,
        [{"m_strRemark": intent.intent_id, "m_strOrderStatus": secret}],
        [],
        passorder_attempted=True,
        generated_at=NOW,
    )
    assert result.order_status == "rejected"
    assert secret not in serialize_result(result).decode("ascii")
    payload = result.__dict__.copy()
    payload.pop("source_path", None)
    payload["generated_at"] = "2026-07-15T01:00:00Z"
    payload["order_status"] = secret
    from quantpilot_core.qmt_simulation_execution import result_from_mapping

    with pytest.raises(InvalidResultError):
        result_from_mapping(payload)


def test_state_semantics_preserve_truthful_pre_submission_attempt_flag() -> None:
    base = {
        "schema_version": 1,
        "protocol_version": "qmt_simulation_order_loop_v1",
        "intent_id": "intent_127",
        "updated_at": "2026-07-15T01:00:00Z",
        "status": "received",
        "expected_redacted_account_id": BINDING,
        "passorder_attempted": True,
        "failure_code": None,
    }
    with pytest.raises(InvalidStateError):
        state_from_mapping(base)
    base["status"] = "uncertain"
    base["passorder_attempted"] = False
    assert state_from_mapping(base).passorder_attempted is False
    base["status"] = "expired"
    base["passorder_attempted"] = True
    with pytest.raises(InvalidStateError):
        state_from_mapping(base)

    received = reconcile_broker_records(
        _intent(), [], [], passorder_attempted=False, generated_at=NOW
    )
    result_payload = received.__dict__.copy()
    result_payload.pop("source_path", None)
    result_payload["generated_at"] = "2026-07-15T01:00:00Z"
    result_payload["passorder_attempted"] = True
    from quantpilot_core.qmt_simulation_execution import result_from_mapping

    with pytest.raises(InvalidResultError):
        result_from_mapping(result_payload)


def test_state_result_roundtrip_inspection_and_non_paper_reporting(tmp_path: Path) -> None:
    root = _bridge(tmp_path)
    intent = _intent()
    write_intent_atomic(root, intent, now=NOW)
    state = build_state(
        intent_id=intent.intent_id,
        expected_redacted_account_id=BINDING,
        status="submission_attempted",
        passorder_attempted=True,
        updated_at=NOW,
    )
    write_state_atomic(root, state)
    assert read_state(root, intent.intent_id) == state
    assert inspect_status(root, intent.intent_id)["status"] == "submission_attempted"

    result = reconcile_broker_records(
        intent,
        [],
        [{"m_strRemark": intent.intent_id, "m_nVolume": 100, "m_dPrice": 10}],
        passorder_attempted=True,
        generated_at=NOW,
    )
    write_result_atomic(root, result)
    assert read_result(root, intent.intent_id) == result
    assert state_from_result(result).status == "filled"
    assert inspect_status(root, intent.intent_id)["source"] == "acknowledgement"
    facts = result_to_reporting_facts(result)
    assert set(facts) == {"qmt_orders", "qmt_fills", "qmt_reconciliation"}
    assert facts["qmt_reconciliation"][0]["checks"]["classified_as_paper_fill"] is False
    assert all(not key.startswith("paper_") for key in facts)
    json.dumps(facts)


def test_result_reader_cross_binds_authenticated_intent_fields(tmp_path: Path) -> None:
    root = _bridge(tmp_path)
    intent = _intent()
    write_intent_atomic(root, intent, now=NOW)
    valid = reconcile_broker_records(
        intent,
        [{"m_strRemark": intent.intent_id, "m_nOrderStatus": 50}],
        [],
        passorder_attempted=False,
        generated_at=NOW,
    )
    forged = replace(valid, symbol="000001.SZ")
    path = result_path(root, intent.intent_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(serialize_result(forged))
    with pytest.raises(InvalidResultError):
        read_result(root, intent.intent_id)


def test_state_and_result_updates_cannot_clear_fill_or_order_evidence(tmp_path: Path) -> None:
    root = _bridge(tmp_path)
    intent = _intent()
    write_intent_atomic(root, intent, now=NOW)
    partial = reconcile_broker_records(
        intent,
        [],
        [
            {
                "m_strRemark": intent.intent_id,
                "m_strOrderRef": "REF-1",
                "m_nVolume": 40,
                "m_dPrice": 10,
            }
        ],
        passorder_attempted=True,
        generated_at=NOW,
    )
    write_result_atomic(root, partial)
    smaller = reconcile_broker_records(
        intent,
        [],
        [
            {
                "m_strRemark": intent.intent_id,
                "m_strOrderRef": "REF-1",
                "m_nVolume": 20,
                "m_dPrice": 10,
            }
        ],
        passorder_attempted=True,
        generated_at=NOW + timedelta(seconds=1),
    )
    with pytest.raises(InvalidStateTransitionError):
        write_result_atomic(root, smaller)

    changed_reference = reconcile_broker_records(
        intent,
        [],
        [
            {
                "m_strRemark": intent.intent_id,
                "m_strOrderRef": "REF-2",
                "m_nVolume": 60,
                "m_dPrice": 10,
            }
        ],
        passorder_attempted=True,
        generated_at=NOW + timedelta(seconds=1),
    )
    with pytest.raises(InvalidStateTransitionError):
        write_result_atomic(root, changed_reference)

    partial_state = build_state(
        intent_id=intent.intent_id,
        expected_redacted_account_id=BINDING,
        status="partially_filled",
        passorder_attempted=True,
        updated_at=NOW,
    )
    write_state_atomic(root, partial_state)
    rejected_state = build_state(
        intent_id=intent.intent_id,
        expected_redacted_account_id=BINDING,
        status="rejected",
        passorder_attempted=True,
        failure_code="broker_order_rejected",
        updated_at=NOW + timedelta(seconds=1),
    )
    with pytest.raises(InvalidStateTransitionError):
        write_state_atomic(root, rejected_state)


def test_filled_result_cannot_be_fabricated_without_deal_evidence() -> None:
    result = reconcile_broker_records(
        _intent(),
        [{"m_strRemark": "intent_127", "filled_quantity": 100, "m_nOrderStatus": 56}],
        [],
        passorder_attempted=True,
        generated_at=NOW,
    )
    assert result.status == "broker_acknowledged"
    payload = {
        **result.__dict__,
        "generated_at": "2026-07-15T01:00:00Z",
        "status": "filled",
        "filled_quantity": 100,
        "average_fill_price": 10.0,
    }
    payload.pop("source_path", None)
    from quantpilot_core.qmt_simulation_execution import result_from_mapping

    with pytest.raises(InvalidResultError):
        result_from_mapping(payload)
