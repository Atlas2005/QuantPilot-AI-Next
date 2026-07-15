from __future__ import annotations

import ast
import datetime as dt
import hashlib
import hmac
import importlib.util
import json
import re
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest


EXECUTOR_PATH = Path("scripts/qmt_builtin_simulation_executor_v1.py")
READONLY_EXPORTER_PATH = Path("scripts/qmt_builtin_readonly_exporter_v1.py")
READONLY_EXPORTER_SHA256 = "134210fceb7b58f18a2a76c7bd6e6a07ef5127d2ce0e64c77bcd35688ce4dc77"
BINDING_KEY = bytes(range(32))
RAW_ACCOUNT = "offline-qmt-simulation-account"


class LastBarContext:
    def __init__(self, last_bar: bool = True):
        self.last_bar = last_bar

    def is_last_bar(self) -> bool:
        return self.last_bar


def load_executor():
    name = "qmt_builtin_simulation_executor_v1_{0}".format(uuid4().hex)
    spec = importlib.util.spec_from_file_location(name, EXECUTOR_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def configure_executor(executor, root: Path, *, account_type: str = "STOCK") -> None:
    key_dir = root / "state"
    key_dir.mkdir(parents=True)
    (key_dir / "account_binding_key_v1.hex").write_bytes(BINDING_KEY.hex().encode("ascii"))
    executor.BRIDGE_ROOT = str(root)
    executor.account = RAW_ACCOUNT
    executor.accountType = account_type
    executor.init(LastBarContext())


def write_intent(
    executor,
    root: Path,
    *,
    intent_id: str = "intent_127",
    side: str = "buy",
    quantity: int = 100,
    limit_price: float = 10.25,
    created_at: dt.datetime | None = None,
    expires_at: dt.datetime | None = None,
    binding: str | None = None,
    hmac_key: bytes = BINDING_KEY,
) -> dict[str, object]:
    created = created_at or dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    expires = expires_at or created + dt.timedelta(minutes=10)
    unsigned: dict[str, object] = {
        "schema_version": executor.SCHEMA_VERSION,
        "protocol_version": executor.PROTOCOL_VERSION,
        "intent_id": intent_id,
        "created_at": executor._utc_text(created),
        "expires_at": executor._utc_text(expires),
        "environment": executor.ENVIRONMENT,
        "expected_redacted_account_id": binding or executor.G.redacted_account_id,
        "account_type": executor.ACCOUNT_TYPE,
        "symbol": "600000.SH",
        "side": side,
        "quantity": quantity,
        "order_kind": executor.ORDER_KIND,
        "limit_price": limit_price,
        "source_order_digest": "a" * 64,
        "run_label": "focused-static-test",
        "explicit_submit": True,
    }
    payload = dict(unsigned)
    payload["intent_hmac"] = hmac.new(
        hmac_key,
        executor.INTENT_HMAC_DOMAIN + executor._canonical_bytes(unsigned),
        hashlib.sha256,
    ).hexdigest()
    path = root / "execution" / "intents" / (intent_id + ".json")
    path.write_bytes(executor._file_bytes(payload))
    return payload


def rewrite_signed_intent(executor, root: Path, payload: dict[str, object]) -> None:
    unsigned = dict(payload)
    unsigned.pop("intent_hmac", None)
    payload["intent_hmac"] = hmac.new(
        BINDING_KEY,
        executor.INTENT_HMAC_DOMAIN + executor._canonical_bytes(unsigned),
        hashlib.sha256,
    ).hexdigest()
    intent_id = str(payload["intent_id"])
    path = root / "execution" / "intents" / (intent_id + ".json")
    path.write_bytes(executor._file_bytes(payload))


def read_document(root: Path, section: str, intent_id: str = "intent_127") -> dict[str, object]:
    path = root / "execution" / section / (intent_id + ".json")
    return json.loads(path.read_text(encoding="utf-8"))


def query_from(orders, deals, calls):
    def query(account_id, account_type, data_type):
        calls.append((account_id, account_type, data_type))
        if data_type == "order":
            return orders() if callable(orders) else orders
        if data_type == "deal":
            return deals() if callable(deals) else deals
        raise AssertionError("unexpected QMT data type")

    return query


def test_source_is_ascii_gbk_python36_standard_library_and_loop_free() -> None:
    source_bytes = EXECUTOR_PATH.read_bytes()
    source = source_bytes.decode("gbk")
    tree = ast.parse(source, filename=str(EXECUTOR_PATH), feature_version=(3, 6))

    assert source_bytes.splitlines()[0] == b"#coding:gbk"
    assert all(value < 128 for value in source_bytes)
    assert not any(isinstance(node, (ast.AnnAssign, ast.JoinedStr, ast.While)) for node in ast.walk(tree))

    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert imports <= {
        "datetime",
        "errno",
        "fcntl",
        "hashlib",
        "hmac",
        "json",
        "math",
        "msvcrt",
        "os",
        "re",
        "stat",
    }
    lowered = source.lower()
    for forbidden in (
        "xtquant",
        "socket",
        "urllib",
        "requests",
        "subprocess",
        "threading",
        "deepseek",
        "algo_passorder",
        "quicktrade=2",
    ):
        assert forbidden not in lowered


def test_exact_passorder_shape_and_handlebar_only_reachability() -> None:
    source = EXECUTOR_PATH.read_text(encoding="gbk")
    tree = ast.parse(source, filename=str(EXECUTOR_PATH), feature_version=(3, 6))
    functions = {
        node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)
    }
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "passorder"
    ]
    assert len(calls) == 1
    call = calls[0]
    assert len(call.args) == 11
    assert call.keywords == []
    assert isinstance(call.args[0], ast.Name) and call.args[0].id == "operation_code"
    assert isinstance(call.args[1], ast.Constant) and call.args[1].value == 1101
    assert isinstance(call.args[4], ast.Constant) and call.args[4].value == 11
    assert isinstance(call.args[8], ast.Constant) and call.args[8].value == 1
    assert isinstance(call.args[10], ast.Name) and call.args[10].id == "ContextInfo"
    assert isinstance(call.args[9], ast.Subscript)
    assert isinstance(call.args[9].value, ast.Name) and call.args[9].value.id == "intent"
    assert isinstance(call.args[9].slice, ast.Constant) and call.args[9].slice.value == "intent_id"

    passorder_owners = {
        name
        for name, function in functions.items()
        if any(child is call for child in ast.walk(function))
    }
    assert passorder_owners == {"handlebar"}
    operation_values = {
        node.value
        for node in ast.walk(functions["handlebar"])
        if isinstance(node, ast.Constant)
        and node.value in (23, 24)
    }
    assert operation_values == {23, 24}

    prohibited_calls = {
        "cancel",
        "cancelorder",
        "cancel_order",
        "algo_passorder",
        "smart_algo_passorder",
        "order_stock",
        "submit_order",
    }
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert called_names.isdisjoint(prohibited_calls)


def test_broker_queries_and_last_bar_guard_are_only_in_handlebar() -> None:
    tree = ast.parse(
        EXECUTOR_PATH.read_text(encoding="gbk"),
        filename=str(EXECUTOR_PATH),
        feature_version=(3, 6),
    )
    functions = {
        node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)
    }
    query_owners = set()
    query_lines = []
    passorder_line = None
    for name, function in functions.items():
        for node in ast.walk(function):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id == "get_trade_detail_data":
                query_owners.add(name)
                query_lines.append(node.lineno)
            elif node.func.id == "passorder":
                passorder_line = node.lineno
    assert query_owners == {"handlebar"}
    assert len(query_lines) == 2
    assert passorder_line is not None and max(query_lines) < passorder_line

    first = functions["handlebar"].body[0]
    assert isinstance(first, ast.If)
    assert isinstance(first.test, ast.UnaryOp) and isinstance(first.test.op, ast.Not)
    assert isinstance(first.test.operand, ast.Call)
    assert isinstance(first.test.operand.func, ast.Attribute)
    assert first.test.operand.func.attr == "is_last_bar"
    assert any(isinstance(item, ast.Return) for item in first.body)


def test_readonly_exporter_remains_byte_identical_and_mutation_free() -> None:
    source_bytes = READONLY_EXPORTER_PATH.read_bytes()
    assert hashlib.sha256(source_bytes).hexdigest() == READONLY_EXPORTER_SHA256
    tree = ast.parse(source_bytes.decode("gbk"), filename=str(READONLY_EXPORTER_PATH))
    mutation_names = {
        "passorder",
        "cancel",
        "cancelorder",
        "cancel_order",
        "algo_passorder",
        "smart_algo_passorder",
    }
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert calls.isdisjoint(mutation_names)
    assert re.search(rb"\bpassorder\s*\(", source_bytes) is None


def test_submission_persists_claim_and_attempt_before_exact_call(tmp_path: Path) -> None:
    executor = load_executor()
    root = tmp_path / "bridge"
    configure_executor(executor, root)
    write_intent(executor, root)
    query_calls = []
    executor.get_trade_detail_data = query_from([], [], query_calls)
    passorder_calls = []

    def fake_passorder(*args):
        state = read_document(root, "state")
        assert state["status"] == "submission_attempted"
        assert state["passorder_attempted"] is True
        passorder_calls.append(args)

    executor.passorder = fake_passorder
    executor.handlebar(LastBarContext())

    assert len(passorder_calls) == 1
    assert passorder_calls[0][:-1] == (
        23,
        1101,
        RAW_ACCOUNT,
        "600000.SH",
        11,
        10.25,
        100,
        "quantpilot_sim_v1",
        1,
        "intent_127",
    )
    assert isinstance(passorder_calls[0][-1], LastBarContext)
    assert query_calls == [
        (RAW_ACCOUNT, "STOCK", "order"),
        (RAW_ACCOUNT, "STOCK", "deal"),
    ]
    state = read_document(root, "state")
    result = read_document(root, "acknowledgements")
    assert state["status"] == result["status"] == "uncertain"
    assert state["passorder_attempted"] is result["passorder_attempted"] is True
    assert result["failure_code"] == "broker_readback_pending"
    assert not (root / "execution" / "state" / "intent_127.json.tmp").exists()
    assert not (root / "execution" / "acknowledgements" / "intent_127.json.tmp").exists()


def test_historical_bar_returns_before_query_or_submission(tmp_path: Path) -> None:
    executor = load_executor()
    root = tmp_path / "bridge"
    configure_executor(executor, root)
    write_intent(executor, root)
    calls = []
    executor.get_trade_detail_data = lambda *args: calls.append(("query", args))
    executor.passorder = lambda *args: calls.append(("passorder", args))

    executor.handlebar(LastBarContext(last_bar=False))

    assert calls == []
    assert not (root / "execution" / "state" / "intent_127.json").exists()


def test_query_failure_before_submission_stays_claimed_and_can_retry(tmp_path: Path) -> None:
    executor = load_executor()
    root = tmp_path / "bridge"
    configure_executor(executor, root)
    write_intent(executor, root)
    fail = {"value": True}

    def query(*args):
        if fail["value"]:
            raise RuntimeError("provider text is not serialized")
        return []

    submitted = []
    executor.get_trade_detail_data = query
    executor.passorder = lambda *args: submitted.append(args)
    executor.handlebar(LastBarContext())

    state = read_document(root, "state")
    result = read_document(root, "acknowledgements")
    assert state["status"] == result["status"] == "claimed"
    assert state["passorder_attempted"] is result["passorder_attempted"] is False
    assert result["failure_code"] == "broker_query_failed"
    assert "provider text" not in json.dumps(result)

    fail["value"] = False
    executor.handlebar(LastBarContext())
    assert len(submitted) == 1


@pytest.mark.parametrize(
    ("orders", "deals", "expected_status"),
    [
        (
            [
                SimpleNamespace(
                    m_strRemark="intent_127",
                    m_strOrderRef="broker-ref-1",
                    m_strOrderSysID="system-1",
                    m_nOrderStatus=50,
                    m_nOrderSubmitStatus=49,
                    m_nVolumeTotalOriginal=100,
                    m_nVolumeTraded=0,
                    m_strInstrumentID="600000",
                    m_strExchangeID="SH",
                    m_strOptName="buy",
                )
            ],
            [],
            "broker_acknowledged",
        ),
        (
            [],
            [
                SimpleNamespace(
                    m_strRemark="intent_127",
                    m_strOrderRef="broker-ref-2",
                    m_strOrderSysID="system-2",
                    m_nVolume=100,
                    m_dPrice=10.2,
                    m_strInstrumentID="600000",
                    m_strExchangeID="SH",
                )
            ],
            "filled",
        ),
    ],
)
def test_existing_matching_order_or_deal_prevents_submission(
    tmp_path: Path, orders, deals, expected_status: str
) -> None:
    executor = load_executor()
    root = tmp_path / "bridge"
    configure_executor(executor, root)
    write_intent(executor, root)
    query_calls = []
    executor.get_trade_detail_data = query_from(orders, deals, query_calls)
    passorder_calls = []
    executor.passorder = lambda *args: passorder_calls.append(args)

    executor.handlebar(LastBarContext())

    assert passorder_calls == []
    result = read_document(root, "acknowledgements")
    assert result["status"] == expected_status
    assert result["passorder_attempted"] is False
    if deals:
        assert result["broker_order_reference"] == "broker-ref-2"
        assert result["system_order_id"] == "system-2"
        assert result["deal_count"] == 1
    from quantpilot_core.qmt_simulation_execution.validation import result_from_mapping

    result_from_mapping(result, expected_intent_id="intent_127")


def test_restart_and_acknowledgement_failure_never_resubmit(tmp_path: Path) -> None:
    root = tmp_path / "bridge"
    first = load_executor()
    configure_executor(first, root)
    write_intent(first, root)
    first.get_trade_detail_data = query_from([], [], [])
    passorder_calls = []
    first.passorder = lambda *args: passorder_calls.append(args)
    first._safe_write_result = lambda *args: False

    first.handlebar(LastBarContext())
    assert len(passorder_calls) == 1
    assert read_document(root, "state")["passorder_attempted"] is True
    assert not (root / "execution" / "acknowledgements" / "intent_127.json").exists()
    first.stop(LastBarContext())

    second = load_executor()
    second.BRIDGE_ROOT = str(root)
    second.account = RAW_ACCOUNT
    second.accountType = "STOCK"
    second.init(LastBarContext())
    second.get_trade_detail_data = query_from([], [], [])
    second.passorder = lambda *args: passorder_calls.append(args)
    second.handlebar(LastBarContext())

    assert len(passorder_calls) == 1
    assert read_document(root, "state")["status"] == "uncertain"
    assert read_document(root, "acknowledgements")["status"] == "uncertain"


def test_passorder_exception_is_uncertain_and_never_retried(tmp_path: Path) -> None:
    executor = load_executor()
    root = tmp_path / "bridge"
    configure_executor(executor, root)
    write_intent(executor, root)
    executor.get_trade_detail_data = query_from([], [], [])
    attempts = []

    def failing_passorder(*args):
        attempts.append(args)
        raise RuntimeError("unbounded provider message " + RAW_ACCOUNT)

    executor.passorder = failing_passorder
    executor.handlebar(LastBarContext())
    first_state = read_document(root, "state")
    first_result = read_document(root, "acknowledgements")
    assert first_state["status"] == first_result["status"] == "uncertain"
    assert first_state["passorder_attempted"] is True
    assert first_result["failure_code"] == "submission_uncertain"
    executor.handlebar(LastBarContext())

    assert len(attempts) == 1
    result_path = root / "execution" / "acknowledgements" / "intent_127.json"
    result = json.loads(result_path.read_text())
    assert result["status"] == "uncertain"
    assert result["passorder_attempted"] is True
    assert result["failure_code"] in {"submission_uncertain", "broker_readback_pending"}
    assert result["failure_type"] in {"RuntimeError", None}
    assert RAW_ACCOUNT not in result_path.read_text()


def test_corrupt_received_state_cannot_clear_attempt_barrier(tmp_path: Path) -> None:
    executor = load_executor()
    root = tmp_path / "bridge"
    configure_executor(executor, root)
    intent = write_intent(executor, root)
    corrupt = {
        "schema_version": executor.SCHEMA_VERSION,
        "protocol_version": executor.PROTOCOL_VERSION,
        "intent_id": "intent_127",
        "updated_at": executor._utc_text(),
        "status": "received",
        "expected_redacted_account_id": executor.G.redacted_account_id,
        "passorder_attempted": True,
        "failure_code": None,
    }
    state_path = root / "execution" / "state" / "intent_127.json"
    state_path.write_bytes(executor._file_bytes(corrupt))
    calls = []
    executor.get_trade_detail_data = lambda *args: calls.append(("query", args))
    executor.passorder = lambda *args: calls.append(("passorder", args))

    executor.handlebar(LastBarContext())

    assert intent["intent_id"] == "intent_127"
    assert calls == []
    state = read_document(root, "state")
    assert state["status"] == "uncertain"
    assert state["passorder_attempted"] is True
    assert state["failure_code"] == "invalid_local_state"


def test_readback_upgrades_uncertain_to_acknowledged_partial_and_filled(tmp_path: Path) -> None:
    executor = load_executor()
    root = tmp_path / "bridge"
    configure_executor(executor, root)
    write_intent(executor, root, quantity=200)
    stage = {"value": 0}

    def orders():
        if stage["value"] == 0:
            return []
        return [
            SimpleNamespace(
                m_strRemark="intent_127",
                m_strOrderRef="ref-127",
                m_nOrderStatus=50,
                m_nVolumeTotalOriginal=200,
                m_nVolumeTraded=100 if stage["value"] == 2 else 0,
                m_strInstrumentID="600000.SH",
                m_strOptName="buy",
            )
        ]

    def deals():
        if stage["value"] < 2:
            return []
        records = [
            SimpleNamespace(
                m_strRemark="intent_127",
                m_strOrderRef="ref-127",
                m_nVolume=100,
                m_dPrice=10.0,
                m_strInstrumentID="600000.SH",
            )
        ]
        if stage["value"] == 3:
            records.append(
                SimpleNamespace(
                    m_strRemark="intent_127",
                    m_strOrderRef="ref-127",
                    m_nVolume=100,
                    m_dPrice=10.2,
                    m_strInstrumentID="600000.SH",
                )
            )
        return records

    executor.get_trade_detail_data = query_from(orders, deals, [])
    submitted = []
    executor.passorder = lambda *args: submitted.append(args)

    executor.handlebar(LastBarContext())
    assert read_document(root, "acknowledgements")["status"] == "uncertain"
    stage["value"] = 1
    executor.handlebar(LastBarContext())
    assert read_document(root, "acknowledgements")["status"] == "broker_acknowledged"
    stage["value"] = 2
    executor.handlebar(LastBarContext())
    partial = read_document(root, "acknowledgements")
    assert partial["status"] == "partially_filled"
    assert partial["filled_quantity"] == 100
    stage["value"] = 3
    executor.handlebar(LastBarContext())
    filled = read_document(root, "acknowledgements")
    assert filled["status"] == "filled"
    assert filled["filled_quantity"] == 200
    assert filled["average_fill_price"] == pytest.approx(10.1)
    assert len(submitted) == 1


def test_readback_evidence_is_monotonic_across_incomplete_queries(tmp_path: Path) -> None:
    executor = load_executor()
    root = tmp_path / "bridge"
    configure_executor(executor, root)
    write_intent(executor, root, quantity=200)
    mode = {"value": "empty"}

    def query(account_id, account_type, data_type):
        del account_id, account_type
        if mode["value"] == "error":
            raise RuntimeError("temporary readback failure")
        if data_type == "order":
            if mode["value"] == "order":
                return [SimpleNamespace(m_strRemark="intent_127", m_nOrderStatus=50)]
            return []
        quantities = {
            "partial": (100,),
            "lower_partial": (50,),
            "filled": (100, 100),
            "post_fill_partial": (100,),
        }.get(mode["value"], ())
        return [
            SimpleNamespace(
                m_strRemark="intent_127",
                m_strTradeID="D{0}".format(index),
                m_nVolume=quantity,
                m_dPrice=10.0,
            )
            for index, quantity in enumerate(quantities, start=1)
        ]

    executor.get_trade_detail_data = query
    submitted = []
    executor.passorder = lambda *args: submitted.append(args)
    executor.handlebar(LastBarContext())
    assert len(submitted) == 1

    mode["value"] = "partial"
    executor.handlebar(LastBarContext())
    assert read_document(root, "acknowledgements")["filled_quantity"] == 100
    for transient in ("error", "empty", "order", "lower_partial"):
        mode["value"] = transient
        executor.handlebar(LastBarContext())
        preserved = read_document(root, "acknowledgements")
        assert preserved["status"] == "partially_filled"
        assert preserved["filled_quantity"] == 100

    mode["value"] = "filled"
    executor.handlebar(LastBarContext())
    assert read_document(root, "acknowledgements")["status"] == "filled"
    mode["value"] = "post_fill_partial"
    executor.handlebar(LastBarContext())
    terminal = read_document(root, "acknowledgements")
    assert terminal["status"] == "filled"
    assert terminal["filled_quantity"] == 200


@pytest.mark.parametrize("new_reference", ["REF-B", None])
def test_readback_cannot_change_or_clear_established_broker_identity(
    tmp_path: Path, new_reference: str | None
) -> None:
    executor = load_executor()
    root = tmp_path / "bridge"
    configure_executor(executor, root)
    write_intent(executor, root, quantity=200)
    stage = {"value": "partial"}

    def deals():
        reference = "REF-A" if stage["value"] == "partial" else new_reference
        quantities = (100,) if stage["value"] == "partial" else (100, 100)
        result = []
        for index, quantity in enumerate(quantities, start=1):
            values = {
                "m_strRemark": "intent_127",
                "m_strTradeID": "D{0}".format(index),
                "m_nVolume": quantity,
                "m_dPrice": 10.0,
            }
            if reference is not None:
                values["m_strOrderRef"] = reference
            result.append(SimpleNamespace(**values))
        return result

    executor.get_trade_detail_data = query_from([], deals, [])
    executor.passorder = lambda *args: pytest.fail("preexisting deal must not submit")
    executor.handlebar(LastBarContext())
    first = read_document(root, "acknowledgements")
    assert first["status"] == "partially_filled"
    assert first["broker_order_reference"] == "REF-A"

    stage["value"] = "full"
    executor.handlebar(LastBarContext())
    preserved = read_document(root, "acknowledgements")
    assert preserved["status"] == "partially_filled"
    assert preserved["filled_quantity"] == 100
    assert preserved["broker_order_reference"] == "REF-A"


def test_readback_deal_count_cannot_decrease(tmp_path: Path) -> None:
    executor = load_executor()
    root = tmp_path / "bridge"
    configure_executor(executor, root)
    write_intent(executor, root, quantity=300)
    stage = {"value": "two"}

    def deals():
        if stage["value"] == "two":
            return [
                SimpleNamespace(
                    m_strRemark="intent_127",
                    m_strTradeID="D1",
                    m_nVolume=50,
                    m_dPrice=10.0,
                ),
                SimpleNamespace(
                    m_strRemark="intent_127",
                    m_strTradeID="D2",
                    m_nVolume=50,
                    m_dPrice=10.0,
                ),
            ]
        return [
            SimpleNamespace(
                m_strRemark="intent_127",
                m_strTradeID="D3",
                m_nVolume=150,
                m_dPrice=10.0,
            )
        ]

    executor.get_trade_detail_data = query_from([], deals, [])
    executor.passorder = lambda *args: pytest.fail("preexisting deal must not submit")
    executor.handlebar(LastBarContext())
    assert read_document(root, "acknowledgements")["deal_count"] == 2
    stage["value"] = "one"
    executor.handlebar(LastBarContext())
    preserved = read_document(root, "acknowledgements")
    assert preserved["filled_quantity"] == 100
    assert preserved["deal_count"] == 2


def test_unexpected_reconciliation_error_cannot_overwrite_filled_evidence(
    tmp_path: Path,
) -> None:
    executor = load_executor()
    root = tmp_path / "bridge"
    configure_executor(executor, root)
    write_intent(executor, root)
    deal = SimpleNamespace(
        m_strRemark="intent_127",
        m_strTradeID="D-filled",
        m_nVolume=100,
        m_dPrice=10.0,
    )
    executor.get_trade_detail_data = query_from([], [deal], [])
    executor.passorder = lambda *args: pytest.fail("preexisting fill must not submit")
    executor.handlebar(LastBarContext())
    result_path = root / "execution" / "acknowledgements" / "intent_127.json"
    before = result_path.read_bytes()

    def unexpected(*args):
        del args
        raise RuntimeError("unexpected reconciliation failure")

    executor._reconcile = unexpected
    executor.handlebar(LastBarContext())

    assert result_path.read_bytes() == before
    assert read_document(root, "state")["status"] == "filled"


def test_expired_attempted_intent_still_reconciles_but_never_resubmits(tmp_path: Path) -> None:
    executor = load_executor()
    root = tmp_path / "bridge"
    configure_executor(executor, root)
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    write_intent(
        executor,
        root,
        created_at=now - dt.timedelta(minutes=10),
        expires_at=now - dt.timedelta(minutes=5),
    )
    intent = read_document(root, "intents")
    executor._write_local_state(
        executor._bridge_paths(str(root)), intent, "submission_attempted", True
    )
    order = SimpleNamespace(
        m_strRemark="intent_127",
        m_strOrderRef="late-order",
        m_nOrderStatus=50,
        m_nVolumeTotalOriginal=100,
        m_nVolumeTraded=0,
        m_strInstrumentID="600000.SH",
    )
    executor.get_trade_detail_data = query_from([order], [], [])
    submitted = []
    executor.passorder = lambda *args: submitted.append(args)

    executor.handlebar(LastBarContext())

    assert submitted == []
    assert read_document(root, "acknowledgements")["status"] == "broker_acknowledged"


def test_fresh_expired_intent_queries_then_expires_without_submission(tmp_path: Path) -> None:
    executor = load_executor()
    root = tmp_path / "bridge"
    configure_executor(executor, root)
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    write_intent(
        executor,
        root,
        created_at=now - dt.timedelta(minutes=10),
        expires_at=now - dt.timedelta(minutes=5),
    )
    queries = []
    executor.get_trade_detail_data = query_from([], [], queries)
    submitted = []
    executor.passorder = lambda *args: submitted.append(args)

    executor.handlebar(LastBarContext())

    assert len(queries) == 2
    assert submitted == []
    assert read_document(root, "state")["status"] == "expired"
    assert read_document(root, "acknowledgements")["status"] == "expired"


def test_query_crossing_expiry_cannot_submit(tmp_path: Path) -> None:
    executor = load_executor()
    root = tmp_path / "bridge"
    configure_executor(executor, root)
    created = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    expires = created + dt.timedelta(seconds=10)
    write_intent(executor, root, created_at=created, expires_at=expires)
    clock = {"now": created}
    executor._utc_now_datetime = lambda: clock["now"]

    def crossing_query(*args):
        del args
        clock["now"] = expires + dt.timedelta(seconds=1)
        return []

    executor.get_trade_detail_data = crossing_query
    submitted = []
    executor.passorder = lambda *args: submitted.append(args)
    executor.handlebar(LastBarContext())

    assert submitted == []
    assert read_document(root, "state")["status"] == "expired"
    assert read_document(root, "state")["passorder_attempted"] is False


def test_expiry_after_attempt_marker_is_rechecked_before_passorder(tmp_path: Path) -> None:
    executor = load_executor()
    root = tmp_path / "bridge"
    configure_executor(executor, root)
    created = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    expires = created + dt.timedelta(seconds=10)
    write_intent(executor, root, created_at=created, expires_at=expires)
    clock = {"now": created}
    executor._utc_now_datetime = lambda: clock["now"]
    executor.get_trade_detail_data = query_from([], [], [])
    original_write = executor._write_local_state

    def crossing_write(paths, intent, status, attempted, failure_code=None):
        state = original_write(paths, intent, status, attempted, failure_code)
        if status == "submission_attempted":
            clock["now"] = expires + dt.timedelta(seconds=1)
        return state

    executor._write_local_state = crossing_write
    submitted = []
    executor.passorder = lambda *args: submitted.append(args)
    executor.handlebar(LastBarContext())

    assert submitted == []
    result = read_document(root, "acknowledgements")
    assert result["status"] == "uncertain"
    assert result["passorder_attempted"] is True
    assert result["failure_code"] == "intent_expired_before_call"


@pytest.mark.parametrize("order_status", [57, "57", "rejected", "waste"])
def test_explicit_broker_rejection_is_bounded_and_never_submits(
    tmp_path: Path, order_status
) -> None:
    executor = load_executor()
    root = tmp_path / "bridge"
    configure_executor(executor, root)
    write_intent(executor, root)
    order = SimpleNamespace(
        m_strRemark="intent_127",
        m_strOrderRef="rejected-order",
        m_nOrderStatus=order_status,
        m_nVolumeTotalOriginal=100,
        m_nVolumeTraded=0,
        m_strInstrumentID="600000.SH",
        m_strErrorMsg="must never be serialized " + RAW_ACCOUNT,
    )
    executor.get_trade_detail_data = query_from([order], [], [])
    submitted = []
    executor.passorder = lambda *args: submitted.append(args)

    executor.handlebar(LastBarContext())

    result_path = root / "execution" / "acknowledgements" / "intent_127.json"
    rejected = json.loads(result_path.read_text())
    assert rejected["status"] == "rejected"
    assert rejected["failure_code"] == "broker_order_rejected"
    assert RAW_ACCOUNT not in result_path.read_text()
    assert "must never be serialized" not in result_path.read_text()
    assert submitted == []


def test_arbitrary_broker_status_text_is_never_serialized(tmp_path: Path) -> None:
    executor = load_executor()
    root = tmp_path / "bridge"
    configure_executor(executor, root)
    write_intent(executor, root)
    secret_status = "rejected password=provider-secret"
    order = SimpleNamespace(
        m_strRemark="intent_127",
        m_strOrderRef="safe-ref",
        m_strOrderStatus=secret_status,
    )
    executor.get_trade_detail_data = query_from([order], [], [])
    executor.passorder = lambda *args: pytest.fail("rejected evidence must not submit")
    executor.handlebar(LastBarContext())

    path = root / "execution" / "acknowledgements" / "intent_127.json"
    serialized = path.read_text()
    result = json.loads(serialized)
    assert result["status"] == "rejected"
    assert result["order_status"] == "observed"
    assert result["failure_code"] == "broker_order_rejected"
    assert secret_status not in serialized
    assert "provider-secret" not in serialized


@pytest.mark.parametrize("case", ["duplicate", "conflict", "references"])
def test_deal_identity_deduplication_and_conflicts_are_safe(
    tmp_path: Path, case: str
) -> None:
    executor = load_executor()
    root = tmp_path / "bridge"
    configure_executor(executor, root)
    write_intent(executor, root, quantity=200)
    first = SimpleNamespace(
        m_strRemark="intent_127",
        m_strTradeID="D1",
        m_nVolume=100,
        m_dPrice=10.0,
        m_strOrderRef="R1",
    )
    if case == "duplicate":
        second = SimpleNamespace(**first.__dict__)
    elif case == "conflict":
        second = SimpleNamespace(
            m_strRemark="intent_127",
            m_strTradeID="D1",
            m_nVolume=50,
            m_dPrice=10.0,
            m_strOrderRef="R1",
        )
    else:
        second = SimpleNamespace(
            m_strRemark="intent_127",
            m_strTradeID="D2",
            m_nVolume=50,
            m_dPrice=10.0,
            m_strOrderRef="R2",
        )
    executor.get_trade_detail_data = query_from([], [first, second], [])
    executor.passorder = lambda *args: pytest.fail("matching deals must not submit")
    executor.handlebar(LastBarContext())

    result = read_document(root, "acknowledgements")
    if case == "duplicate":
        assert result["status"] == "partially_filled"
        assert result["filled_quantity"] == 100
        assert result["deal_count"] == 1
    else:
        assert result["status"] == "uncertain"
        assert result["passorder_attempted"] is False
        assert result["failure_code"] == "conflicting_deal_identity"
        assert result["filled_quantity"] == 0


def test_order_and_deal_references_must_identify_one_broker_order(tmp_path: Path) -> None:
    executor = load_executor()
    root = tmp_path / "bridge"
    configure_executor(executor, root)
    write_intent(executor, root)
    order = SimpleNamespace(
        m_strRemark="intent_127",
        m_strOrderRef="ORDER-A",
        m_strOrderSysID="SYSTEM-A",
    )
    deal = SimpleNamespace(
        m_strRemark="intent_127",
        m_strTradeID="D1",
        m_strOrderRef="ORDER-B",
        m_strOrderSysID="SYSTEM-B",
        m_nVolume=100,
        m_dPrice=10.0,
    )
    executor.get_trade_detail_data = query_from([order], [deal], [])
    executor.passorder = lambda *args: pytest.fail("conflicting evidence must not submit")
    executor.handlebar(LastBarContext())

    result = read_document(root, "acknowledgements")
    assert result["status"] == "uncertain"
    assert result["passorder_attempted"] is False
    assert result["failure_code"] == "multiple_broker_orders"
    assert result["filled_quantity"] == 0


def test_explicit_unknown_broker_side_cannot_prove_fill(tmp_path: Path) -> None:
    executor = load_executor()
    root = tmp_path / "bridge"
    configure_executor(executor, root)
    write_intent(executor, root)
    deal = SimpleNamespace(
        m_strRemark="intent_127",
        m_strTradeID="D-side",
        m_nDirection=99,
        m_nVolume=100,
        m_dPrice=10.0,
    )
    executor.get_trade_detail_data = query_from([], [deal], [])
    executor.passorder = lambda *args: pytest.fail("invalid side must not submit")
    executor.handlebar(LastBarContext())

    result = read_document(root, "acknowledgements")
    assert result["status"] == "uncertain"
    assert result["passorder_attempted"] is False
    assert result["failure_code"] == "broker_side_mismatch"


@pytest.mark.parametrize(
    ("direction", "offset", "expected_status"),
    [(99, 48, "filled"), (24, 48, "uncertain")],
)
def test_broker_side_aliases_require_one_consistent_recognized_side(
    tmp_path: Path, direction: int, offset: int, expected_status: str
) -> None:
    executor = load_executor()
    root = tmp_path / "bridge"
    configure_executor(executor, root)
    write_intent(executor, root)
    deal = SimpleNamespace(
        m_strRemark="intent_127",
        m_strTradeID="D-side-alias",
        m_nDirection=direction,
        m_nOffsetFlag=offset,
        m_nVolume=100,
        m_dPrice=10.0,
    )
    executor.get_trade_detail_data = query_from([], [deal], [])
    executor.passorder = lambda *args: pytest.fail("matching remark must not resubmit")
    executor.handlebar(LastBarContext())

    result = read_document(root, "acknowledgements")
    assert result["status"] == expected_status
    if expected_status == "uncertain":
        assert result["failure_code"] == "broker_side_mismatch"


@pytest.mark.parametrize(
    ("instrument", "expected_status", "failure_code"),
    [
        ("600000", "filled", None),
        ("999999", "uncertain", "broker_symbol_mismatch"),
        ("malformed", "uncertain", "broker_symbol_mismatch"),
    ],
)
def test_bare_broker_symbol_must_match_intent_code(
    tmp_path: Path,
    instrument: str,
    expected_status: str,
    failure_code: str | None,
) -> None:
    executor = load_executor()
    root = tmp_path / "bridge"
    configure_executor(executor, root)
    write_intent(executor, root)
    deal = SimpleNamespace(
        m_strRemark="intent_127",
        m_strTradeID="D-symbol",
        m_strInstrumentID=instrument,
        m_nVolume=100,
        m_dPrice=10.0,
    )
    executor.get_trade_detail_data = query_from([], [deal], [])
    executor.passorder = lambda *args: pytest.fail("matching remark must not resubmit")
    executor.handlebar(LastBarContext())

    result = read_document(root, "acknowledgements")
    assert result["status"] == expected_status
    assert result["passorder_attempted"] is False
    assert result["failure_code"] == failure_code


def test_uncertain_false_is_a_barrier_and_can_upgrade_from_readback(tmp_path: Path) -> None:
    executor = load_executor()
    root = tmp_path / "bridge"
    configure_executor(executor, root)
    write_intent(executor, root)
    mode = {"value": "overflow"}

    def deals():
        if mode["value"] == "empty":
            return []
        quantity = 101 if mode["value"] == "overflow" else 100
        return [
            SimpleNamespace(
                m_strRemark="intent_127",
                m_strTradeID="D1",
                m_nVolume=quantity,
                m_dPrice=10.0,
            )
        ]

    executor.get_trade_detail_data = query_from([], deals, [])
    executor.passorder = lambda *args: pytest.fail("readback barrier must not submit")
    executor.handlebar(LastBarContext())
    assert read_document(root, "state")["status"] == "uncertain"
    assert read_document(root, "state")["passorder_attempted"] is False

    mode["value"] = "empty"
    executor.handlebar(LastBarContext())
    preserved = read_document(root, "acknowledgements")
    assert preserved["status"] == "uncertain"
    assert preserved["passorder_attempted"] is False

    mode["value"] = "filled"
    executor.handlebar(LastBarContext())
    upgraded = read_document(root, "acknowledgements")
    assert upgraded["status"] == "filled"
    assert upgraded["passorder_attempted"] is False


def test_deal_quantity_overflow_is_fixed_safe_failure(tmp_path: Path) -> None:
    executor = load_executor()
    root = tmp_path / "bridge"
    configure_executor(executor, root)
    write_intent(executor, root)
    deal = SimpleNamespace(
        m_strRemark="intent_127",
        m_nVolume=101,
        m_dPrice=10.0,
        m_strInstrumentID="600000.SH",
    )
    executor.get_trade_detail_data = query_from([], [deal], [])
    executor.passorder = lambda *args: pytest.fail("overflow evidence must not submit")

    executor.handlebar(LastBarContext())

    result = read_document(root, "acknowledgements")
    assert result["status"] == "uncertain"
    assert result["passorder_attempted"] is False
    assert result["failure_code"] == "broker_quantity_exceeds_request"
    assert result["filled_quantity"] == 0


@pytest.mark.parametrize("fill_price", [1_000_000_001.0, 1e308])
def test_deal_price_is_bounded_before_weighting(
    tmp_path: Path, fill_price: float
) -> None:
    executor = load_executor()
    root = tmp_path / "bridge"
    configure_executor(executor, root)
    write_intent(executor, root)
    deal = SimpleNamespace(
        m_strRemark="intent_127",
        m_strTradeID="D-price",
        m_nVolume=100,
        m_dPrice=fill_price,
    )
    executor.get_trade_detail_data = query_from([], [deal], [])
    executor.passorder = lambda *args: pytest.fail("invalid fill price must not submit")
    executor.handlebar(LastBarContext())

    result = read_document(root, "acknowledgements")
    assert result["status"] == "uncertain"
    assert result["passorder_attempted"] is False
    assert result["failure_code"] == "invalid_broker_fill_price"
    assert result["filled_quantity"] == 0


def test_snapshot_sequence_is_bounded_for_result_compatibility(tmp_path: Path) -> None:
    executor = load_executor()
    root = tmp_path / "bridge"
    configure_executor(executor, root)
    write_intent(executor, root)
    snapshot_dir = root / "snapshots"
    snapshot_dir.mkdir()
    (snapshot_dir / "latest_snapshot_v1.json").write_text(
        json.dumps({"sequence": 2**63}) + "\n",
        encoding="utf-8",
    )
    executor.get_trade_detail_data = query_from([], [], [])
    executor.passorder = lambda *args: None
    executor.handlebar(LastBarContext())

    assert read_document(root, "acknowledgements")["latest_snapshot_sequence"] is None


@pytest.mark.parametrize("mutation", ["hmac", "binding", "noncanonical", "future"])
def test_invalid_authenticated_transport_never_queries_or_submits(
    tmp_path: Path, mutation: str
) -> None:
    executor = load_executor()
    root = tmp_path / "bridge"
    configure_executor(executor, root)
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    kwargs = {}
    if mutation == "binding":
        kwargs["binding"] = "qmtacct-v1-" + "f" * 24
    if mutation == "future":
        kwargs["created_at"] = now + dt.timedelta(minutes=20)
        kwargs["expires_at"] = now + dt.timedelta(minutes=25)
    payload = write_intent(executor, root, **kwargs)
    path = root / "execution" / "intents" / "intent_127.json"
    if mutation == "hmac":
        payload["limit_price"] = 11.0
        path.write_bytes(executor._file_bytes(payload))
    elif mutation == "noncanonical":
        path.write_bytes(json.dumps(payload, indent=2, sort_keys=True).encode("utf-8"))
    calls = []
    executor.get_trade_detail_data = lambda *args: calls.append(("query", args))
    executor.passorder = lambda *args: calls.append(("passorder", args))

    executor.handlebar(LastBarContext())

    assert calls == []
    assert not (root / "execution" / "state" / "intent_127.json").exists()


def test_only_one_intent_is_accepted_per_model_run(tmp_path: Path) -> None:
    executor = load_executor()
    root = tmp_path / "bridge"
    configure_executor(executor, root)
    write_intent(executor, root, intent_id="intent_a")
    write_intent(executor, root, intent_id="intent_b")
    calls = []
    executor.get_trade_detail_data = lambda *args: calls.append(("query", args))
    executor.passorder = lambda *args: calls.append(("passorder", args))

    executor.handlebar(LastBarContext())

    assert calls == []
    assert list((root / "execution" / "state").glob("*.json")) == []


def test_unrelated_and_nontext_remarks_do_not_match(tmp_path: Path) -> None:
    executor = load_executor()
    root = tmp_path / "bridge"
    configure_executor(executor, root)
    write_intent(executor, root, intent_id="127")
    unrelated_orders = [
        SimpleNamespace(m_strRemark="other-intent"),
        SimpleNamespace(m_strRemark=127),
    ]
    unrelated_deals = [SimpleNamespace(m_strRemark="intent_127")]
    executor.get_trade_detail_data = query_from(unrelated_orders, unrelated_deals, [])
    submitted = []
    executor.passorder = lambda *args: submitted.append(args)

    executor.handlebar(LastBarContext())

    assert len(submitted) == 1
    assert submitted[0][9] == "127"


def test_intent_directory_symlink_cannot_escape_bridge_root(tmp_path: Path) -> None:
    executor = load_executor()
    root = tmp_path / "bridge"
    configure_executor(executor, root)
    intent_dir = root / "execution" / "intents"
    intent_dir.rmdir()
    repository_data = Path("data/open_source_candidates").resolve()
    try:
        intent_dir.symlink_to(repository_data, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable")
    calls = []
    executor.get_trade_detail_data = lambda *args: calls.append(("query", args))
    executor.passorder = lambda *args: calls.append(("passorder", args))

    executor.handlebar(LastBarContext())

    assert calls == []
    assert list((root / "execution" / "state").glob("*.json")) == []


def test_stock_account_injection_is_required_and_raw_account_is_never_written(
    tmp_path: Path,
) -> None:
    rejected = load_executor()
    with pytest.raises(RuntimeError, match="initialization failed"):
        configure_executor(rejected, tmp_path / "credit", account_type="CREDIT")

    executor = load_executor()
    root = tmp_path / "stock"
    configure_executor(executor, root)
    write_intent(executor, root)
    executor.get_trade_detail_data = query_from([], [], [])
    executor.passorder = lambda *args: None
    executor.handlebar(LastBarContext())

    for path in (root / "execution").rglob("*.json"):
        assert RAW_ACCOUNT not in path.read_text(encoding="utf-8")
    assert BINDING_KEY.hex() not in (root / "execution" / "state" / "intent_127.json").read_text()


def test_unreadable_broker_remark_is_a_durable_no_submit_barrier(
    tmp_path: Path,
) -> None:
    class UnreadableRemark:
        @property
        def m_strRemark(self):
            raise RuntimeError("provider field access failed " + RAW_ACCOUNT)

    executor = load_executor()
    root = tmp_path / "bridge"
    configure_executor(executor, root)
    write_intent(executor, root)
    submitted = []
    executor.get_trade_detail_data = query_from([UnreadableRemark()], [], [])
    executor.passorder = lambda *args: submitted.append(args)

    executor.handlebar(LastBarContext())

    assert submitted == []
    state = read_document(root, "state")
    result = read_document(root, "acknowledgements")
    assert state["status"] == result["status"] == "uncertain"
    assert state["passorder_attempted"] is False
    assert result["passorder_attempted"] is False
    assert result["failure_code"] == "broker_record_inspection_failed"

    executor.get_trade_detail_data = query_from([], [], [])
    executor.handlebar(LastBarContext())
    assert submitted == []
    assert read_document(root, "state")["status"] == "uncertain"

    matching_order = SimpleNamespace(
        m_strRemark="intent_127",
        m_nOrderStatus=50,
    )
    executor.get_trade_detail_data = query_from([matching_order], [], [])
    executor.handlebar(LastBarContext())
    upgraded = read_document(root, "acknowledgements")
    assert submitted == []
    assert upgraded["status"] == "broker_acknowledged"
    assert upgraded["passorder_attempted"] is False


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("schema_version", 1.0),
        ("created_at", "2026-07- 5T01:02:03Z"),
    ],
)
def test_nonexact_schema_and_timestamp_never_query_or_submit(
    tmp_path: Path, field: str, invalid_value: object
) -> None:
    executor = load_executor()
    root = tmp_path / "bridge"
    configure_executor(executor, root)
    payload = write_intent(executor, root)
    payload[field] = invalid_value
    rewrite_signed_intent(executor, root, payload)
    calls = []
    executor.get_trade_detail_data = lambda *args: calls.append(("query", args))
    executor.passorder = lambda *args: calls.append(("passorder", args))

    executor.handlebar(LastBarContext())

    assert calls == []
    assert not (root / "execution" / "state" / "intent_127.json").exists()


def test_allowed_future_clock_skew_writes_readable_monotonic_artifacts(
    tmp_path: Path,
) -> None:
    from quantpilot_core.qmt_simulation_execution import read_result, read_state

    root = tmp_path / "bridge"
    first = load_executor()
    configure_executor(first, root)
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    created = now + dt.timedelta(seconds=120)
    write_intent(
        first,
        root,
        created_at=created,
        expires_at=created + dt.timedelta(minutes=10),
    )
    submitted = []
    first.get_trade_detail_data = query_from([], [], [])
    first.passorder = lambda *args: submitted.append(args)

    first.handlebar(LastBarContext())

    assert len(submitted) == 1
    state = read_state(root, "intent_127")
    result = read_result(root, "intent_127")
    assert state.updated_at >= created
    assert result.generated_at >= created
    assert state.status == result.status == "uncertain"
    assert state.passorder_attempted is result.passorder_attempted is True
    first.stop(LastBarContext())

    second = load_executor()
    second.BRIDGE_ROOT = str(root)
    second.account = RAW_ACCOUNT
    second.accountType = "STOCK"
    second.init(LastBarContext())
    second.get_trade_detail_data = query_from([], [], [])
    second.passorder = lambda *args: pytest.fail("future-skew restart must not resubmit")
    second.handlebar(LastBarContext())

    restarted_state = read_state(root, "intent_127")
    restarted_result = read_result(root, "intent_127")
    assert restarted_state.updated_at >= state.updated_at
    assert restarted_result.generated_at >= result.generated_at
    assert restarted_state.status == restarted_result.status == "uncertain"
