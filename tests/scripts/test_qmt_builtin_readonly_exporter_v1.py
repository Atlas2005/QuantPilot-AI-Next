from __future__ import annotations

import ast
import hashlib
import hmac
import importlib.util
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest


EXPORTER_PATH = Path("scripts/qmt_builtin_readonly_exporter_v1.py")
BINDING_KEY = bytes(range(32))
BINDING_KEY_HEX = BINDING_KEY.hex().encode("ascii")


def load_exporter(name: str = "qmt_builtin_readonly_exporter_v1"):
    spec = importlib.util.spec_from_file_location(name, EXPORTER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_binding_key(root: Path, encoded: bytes = BINDING_KEY_HEX) -> Path:
    state_dir = root / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    key_path = state_dir / "account_binding_key_v1.hex"
    key_path.write_bytes(encoded)
    return key_path


def completed_sequence_payload(exporter, sequence: int) -> bytes:
    return json.dumps(
        {
            "schema_version": exporter.SCHEMA_VERSION,
            "bridge_version": exporter.BRIDGE_VERSION,
            "sequence": sequence,
            "snapshot_id": "qmt-{0}".format(sequence),
        },
        sort_keys=True,
    ).encode("utf-8")


class NoTimerContext:
    def run_time(self, *args):
        del args

    def is_last_bar(self):
        return True


class RecordingContext:
    def __init__(self, timer_error=None, last_bar=True):
        self.timer_error = timer_error
        self.last_bar = last_bar
        self.timer_calls = []

    def run_time(self, *args):
        self.timer_calls.append(args)
        if self.timer_error is not None:
            raise self.timer_error

    def is_last_bar(self):
        return self.last_bar


def configure_exporter(
    exporter,
    root: Path,
    account_id="injected-account",
    account_type="stock",
):
    exporter.BRIDGE_ROOT = str(root)
    exporter.account = account_id
    exporter.accountType = account_type
    write_binding_key(root)


def successful_query(calls):
    def fake_query(account_id, account_type, data_type):
        calls.append((account_id, account_type, data_type))
        if data_type == "account":
            return [
                SimpleNamespace(
                    m_dBalance=1000.0,
                    m_strStatus="connected",
                    m_strTradingDate="20260714",
                )
            ]
        return []

    return fake_query


def test_qmt_source_is_ascii_gbk_declared_and_python36_compatible() -> None:
    source_bytes = EXPORTER_PATH.read_bytes()

    assert source_bytes.splitlines()[0] == b"#coding:gbk"
    assert all(value < 128 for value in source_bytes)
    tree = ast.parse(source_bytes.decode("gbk"), filename=str(EXPORTER_PATH), feature_version=(3, 6))
    assert not any(isinstance(node, (ast.AnnAssign, ast.JoinedStr)) for node in ast.walk(tree))

    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert imports <= {
        "datetime",
        "errno",
        "hashlib",
        "hmac",
        "json",
        "math",
        "msvcrt",
        "os",
        "platform",
        "struct",
        "sys",
        "time",
    }


def test_qmt_query_uses_injected_system_function_directly_without_alias() -> None:
    source = EXPORTER_PATH.read_text(encoding="gbk")
    tree = ast.parse(source, filename=str(EXPORTER_PATH), feature_version=(3, 6))
    query_section = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_query_section"
    )
    direct_calls = [
        node
        for node in ast.walk(query_section)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "get_trade_detail_data"
    ]

    assert len(direct_calls) == 1
    direct_call = direct_calls[0]
    references = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id == "get_trade_detail_data"
    ]
    assert len(references) == 1
    assert references[0] is direct_call.func
    assert not any(
        isinstance(node, ast.Constant) and node.value == "get_trade_detail_data"
        for node in ast.walk(tree)
    )
    raw_assignments = [
        node
        for node in ast.walk(query_section)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "raw" for target in node.targets)
    ]
    assert len(raw_assignments) == 1
    assert raw_assignments[0].value is direct_call
    assert len(direct_call.args) == 3
    assert isinstance(direct_call.args[0], ast.Attribute)
    assert isinstance(direct_call.args[0].value, ast.Name)
    assert direct_call.args[0].value.id == "G"
    assert direct_call.args[0].attr == "account_id"
    assert isinstance(direct_call.args[1], ast.Attribute)
    assert isinstance(direct_call.args[1].value, ast.Name)
    assert direct_call.args[1].value.id == "G"
    assert direct_call.args[1].attr == "account_type"
    assert isinstance(direct_call.args[2], ast.Name)
    assert direct_call.args[2].id == "qmt_data_type"
    assert direct_call.keywords == []


def test_qmt_direct_query_call_is_statically_reachable_only_from_handlebar() -> None:
    source = EXPORTER_PATH.read_text(encoding="gbk")
    tree = ast.parse(source, filename=str(EXPORTER_PATH), feature_version=(3, 6))
    functions = {
        node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)
    }
    call_graph = {
        name: {
            child.func.id
            for child in ast.walk(function)
            if isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id in functions
        }
        for name, function in functions.items()
    }
    direct_query_owners = {
        name
        for name, function in functions.items()
        if any(
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id == "get_trade_detail_data"
            for child in ast.walk(function)
        )
    }

    def reaches_direct_query(name):
        pending = [name]
        visited = set()
        while pending:
            current = pending.pop()
            if current in visited:
                continue
            visited.add(current)
            if current in direct_query_owners:
                return True
            pending.extend(call_graph[current])
        return False

    query_reachable = {
        name for name in functions if reaches_direct_query(name)
    }
    query_roots = {
        name
        for name in query_reachable
        if not any(
            name in call_graph[caller]
            for caller in query_reachable
        )
    }

    assert direct_query_owners == {"_query_section"}
    assert query_roots == {"handlebar"}
    assert {
        name for name in ("init", "after_init", "export_qmt_snapshot", "stop")
        if name in query_reachable
    } == set()
    assert "handlebar" in query_reachable


def test_qmt_source_has_no_broker_mutation_call() -> None:
    source = EXPORTER_PATH.read_text(encoding="gbk")
    tree = ast.parse(source, filename=str(EXPORTER_PATH), feature_version=(3, 6))
    prohibited = {
        "passorder",
        "cancel",
        "cancelorder",
        "cancel_order",
        "cancel_task",
        "algo_passorder",
        "order_stock",
        "order_volume",
        "order_value",
        "order_percent",
        "order_target",
        "order_target_value",
        "order_target_percent",
        "submit_order",
        "place_order",
        "insert_order",
        "send_order",
        "buy",
        "sell",
    }
    called_names = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            called_names.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            called_names.add(node.func.attr)
    assert called_names.isdisjoint(prohibited)
    assert re.search(r"\bpassorder\s*\(", source) is None
    assert re.search(r"\bcancel(?:_order|_task)?\s*\(", source) is None
    assert "xtquant" not in source.lower()


def test_account_normalization_observed_fields_redacts_and_bounds_metadata() -> None:
    exporter = load_exporter()
    raw_account = "broker-account-should-never-appear"
    redacted = exporter._redact_account_id(raw_account, BINDING_KEY)
    account = SimpleNamespace(
        m_Enable=1,
        m_dBalance=1_000_000.5,
        m_dAvailable=500_000.25,
        m_dFetchBalance=490_000.0,
        m_dFrozenCash=100.0,
        m_dFrozenCommission=2.5,
        m_dStockValue=300_000.0,
        m_dFundValue=50_000.0,
        m_dLoanValue=25_000.0,
        m_dInstrumentValue=375_000.0,
        m_dPositionProfit=12_345.0,
        m_dEntrustAsset=999_990.0,
        m_dAssureAsset=999_800.0,
        m_nBrokerType=7,
        m_strStatus="connected",
        m_strTradingDate="20260714",
        m_strAccountID=raw_account,
        m_strAccountKey="super-secret-key",
        m_strStockHolder="shareholder-secret",
        m_strUnexpected="x" * 400,
    )
    provenance = {}

    normalized = exporter._normalize_account(account, redacted, "STOCK", provenance)

    assert normalized == {
        "redacted_account_id": redacted,
        "account_type": "STOCK",
        "enabled": True,
        "login_state": "connected",
        "trading_date": "20260714",
        "total_assets": 1_000_000.5,
        "available_cash": 500_000.25,
        "withdrawable_cash": 490_000.0,
        "frozen_cash": 100.0,
        "frozen_commission": 2.5,
        "stock_market_value": 300_000.0,
        "fund_market_value": 50_000.0,
        "bond_market_value": 25_000.0,
        "total_instrument_value": 375_000.0,
        "position_profit": 12_345.0,
        "entrust_asset": 999_990.0,
        "assure_asset": 999_800.0,
        "provider_status": "connected",
        "provider_metadata": {
            "m_nBrokerType": 7,
            "m_strUnexpected": "x" * exporter.MAX_STRING_LENGTH,
        },
    }
    serialized = exporter._serialize_snapshot(normalized).decode("utf-8")
    assert raw_account not in serialized
    assert "super-secret-key" not in serialized
    assert "shareholder-secret" not in serialized
    assert provenance["total_assets"] == {"m_dBalance"}


def test_missing_and_nonfinite_provider_fields_become_null() -> None:
    exporter = load_exporter()

    account = exporter._normalize_account(
        SimpleNamespace(m_dBalance=float("nan"), m_dAvailable=float("inf")),
        "qmtacct-v1-deadbeef",
        "STOCK",
    )
    position = exporter._normalize_position(SimpleNamespace(m_nVolume=None, m_dLastPrice=float("-inf")))

    assert account["total_assets"] is None
    assert account["available_cash"] is None
    assert account["provider_status"] is None
    assert position["total_quantity"] is None
    assert position["latest_price"] is None
    exporter._serialize_snapshot({"account": account, "position": position})


def test_position_normalization_uses_official_qmt_fields() -> None:
    exporter = load_exporter()
    position = SimpleNamespace(
        m_strInstrumentID="600000",
        m_strExchangeID="SSE",
        m_strInstrumentName="Pudong Bank",
        m_nVolume=1200,
        m_nCanUseVolume=1000,
        m_nFrozenVolume=100,
        m_nOnRoadVolume=100,
        m_nYesterdayVolume=900,
        m_dAvgOpenPrice=9.85,
        m_dOpenPrice=9.8,
        m_dLastPrice=10.1,
        m_dMarketValue=12120.0,
        m_dFloatProfit=300.0,
        m_dProfitRate=0.025,
        m_strTradingDay="20260714",
        m_strStockHolder="not-serializable",
        m_strAccountKey="not-serializable-either",
        m_nLegId=1,
    )

    normalized = exporter._normalize_position(position)

    assert normalized == {
        "symbol": "600000.SH",
        "instrument_name": "Pudong Bank",
        "total_quantity": 1200,
        "available_quantity": 1000,
        "frozen_quantity": 100,
        "on_road_quantity": 100,
        "yesterday_quantity": 900,
        "average_cost": 9.85,
        "open_cost": 9.8,
        "latest_price": 10.1,
        "market_value": 12120.0,
        "floating_profit": 300.0,
        "profit_ratio": 0.025,
        "trading_day": "20260714",
        "provider_metadata": {"m_nLegId": 1},
    }


def test_order_normalization_uses_official_qmt_fields() -> None:
    exporter = load_exporter()
    order = SimpleNamespace(
        m_strOrderRef="local-ref-1",
        m_strOrderSysID="system-id-2",
        m_strInstrumentID="000001",
        m_strExchangeID="SZ",
        m_nOffsetFlag=48,
        m_strOptName="BUY DISPLAY",
        m_nOrderPriceType=50,
        m_dLimitPrice=10.2,
        m_nVolumeTotalOriginal=500,
        m_nVolumeTraded=200,
        m_nVolumeTotal=250,
        m_dCancelAmount=50.0,
        m_dTradedPrice=10.1,
        m_nOrderStatus=55,
        m_nOrderSubmitStatus=51,
        m_nErrorID=0,
        m_strErrorMsg="",
        m_strCancelInfo="none",
        m_strInsertDate="20260714",
        m_strInsertTime="10:01:02",
        m_dTradeAmount=2020.0,
        m_strRemark="readonly-observed-order",
        m_strAccountID="sensitive-account",
    )

    normalized = exporter._normalize_order(order)

    assert normalized["broker_order_reference"] == "local-ref-1"
    assert normalized["system_order_id"] == "system-id-2"
    assert normalized["symbol"] == "000001.SZ"
    assert normalized["side"] == "BUY"
    assert normalized["operation_label"] == "BUY DISPLAY"
    assert normalized["original_quantity"] == 500
    assert normalized["filled_quantity"] == 200
    assert normalized["remaining_quantity"] == 250
    assert normalized["cancelled_quantity"] == 50
    assert normalized["investment_remark"] == "readonly-observed-order"
    assert normalized["provider_metadata"] == {}


def test_trade_normalization_supports_legacy_commission_name() -> None:
    exporter = load_exporter()
    trade = SimpleNamespace(
        m_strTradeID="trade-1",
        m_strOrderRef="order-ref-1",
        m_strOrderSysID="order-system-1",
        m_strInstrumentID="830001",
        m_strExchangeID="BSE",
        m_nOffsetFlag=49,
        m_strOptName="SELL DISPLAY",
        m_dPrice=12.0,
        m_nVolume=100,
        m_dTradeAmount=1200.0,
        m_dComission=1.25,
        m_strTradeDate="20260714",
        m_strTradeTime="10:02:03",
        m_strRemark="readonly-observed-trade",
        m_strAccountKey="secret-key",
    )

    normalized = exporter._normalize_trade(trade)

    assert normalized == {
        "trade_id": "trade-1",
        "order_reference": "order-ref-1",
        "system_order_id": "order-system-1",
        "symbol": "830001.BJ",
        "side": "SELL",
        "operation_label": "SELL DISPLAY",
        "fill_price": 12.0,
        "fill_quantity": 100,
        "fill_amount": 1200.0,
        "commission": 1.25,
        "trade_date": "20260714",
        "trade_time": "10:02:03",
        "investment_remark": "readonly-observed-trade",
        "provider_metadata": {},
    }


def test_unknown_metadata_and_collections_are_bounded() -> None:
    exporter = load_exporter()
    exporter.G.account_id = "raw-account-id"
    raw = {"field_{0:03d}".format(index): index for index in range(100)}
    raw["m_strPassword"] = "never-written"
    raw["m_strNote"] = "safe-looking field with raw-account-id embedded"

    metadata = exporter._provider_metadata(raw, set())

    assert len(metadata) == exporter.MAX_PROVIDER_METADATA_FIELDS
    assert "m_strPassword" not in metadata
    assert "m_strNote" not in metadata
    assert exporter._provider_metadata(
        {"m_strNote": "safe-looking field with raw-account-id embedded"}, set()
    ) == {}
    assert len(exporter._bounded_records(range(6000))) == exporter.MAX_RECORDS_PER_SECTION


def test_redaction_is_stable_domain_separated_and_never_returns_raw_value() -> None:
    exporter = load_exporter()
    from quantpilot_core.qmt_builtin_bridge import redact_account_identity

    first = exporter._redact_account_id("  account-A  ", BINDING_KEY)
    second = exporter._redact_account_id("account-A", BINDING_KEY)
    different = exporter._redact_account_id("account-B", BINDING_KEY)
    different_key = exporter._redact_account_id("account-A", bytes(reversed(range(32))))
    expected_digest = hmac.new(
        BINDING_KEY,
        b"quantpilot:qmt-account-binding:v1\x00account-A",
        hashlib.sha256,
    ).hexdigest()[:24]

    assert first == second
    assert first == "qmtacct-v1-" + expected_digest
    assert first == "qmtacct-v1-e5c5ce4ab6d01a24953af16f"
    assert first == redact_account_identity("account-A", binding_key=BINDING_KEY)
    assert first != different
    assert first != different_key
    assert first.startswith("qmtacct-v1-")
    assert "account-A" not in first
    assert len(first) == len("qmtacct-v1-") + 24


def test_account_identity_normalization_matches_keyed_protocol() -> None:
    exporter = load_exporter()

    assert exporter._normalized_account_identity_bytes(42) == b"42"
    assert exporter._normalized_account_identity_bytes(" 42 ") == b"42"
    assert len(exporter._normalized_account_identity_bytes("\u00e9" * 256)) == 512
    assert exporter._redact_account_id(42, BINDING_KEY) == exporter._redact_account_id(
        "42", BINDING_KEY
    )


@pytest.mark.parametrize(
    "account_id",
    [None, True, False, b"not-accepted", "", "   ", "x" * 513, "\u4e2d" * 171, "\ud800"],
)
def test_account_identity_normalization_rejects_ambiguous_or_overbound_values(account_id) -> None:
    exporter = load_exporter()

    with pytest.raises(ValueError, match=re.escape(exporter.SAFE_INITIALIZATION_ERROR)):
        exporter._normalized_account_identity_bytes(account_id)


def test_binding_key_file_is_exact_lowercase_hex_and_bounded(tmp_path: Path) -> None:
    exporter = load_exporter()
    key_path = write_binding_key(tmp_path)

    assert exporter._load_account_binding_key(str(key_path)) == BINDING_KEY


@pytest.mark.parametrize(
    "encoded",
    [
        None,
        b"",
        b"1" * 63,
        b"1" * 65,
        b"11" * 32 + b"\n",
        b"AA" * 32,
        b"gg" * 32,
    ],
    ids=["missing", "empty", "short", "long", "newline", "uppercase", "non_hex"],
)
def test_binding_key_file_fails_closed_without_echoing_secret(
    tmp_path: Path, encoded: bytes | None
) -> None:
    exporter = load_exporter()
    key_path = tmp_path / "state" / "account_binding_key_v1.hex"
    if encoded is not None:
        write_binding_key(tmp_path, encoded)

    with pytest.raises(ValueError) as raised:
        exporter._load_account_binding_key(str(key_path))

    assert str(raised.value) == exporter.SAFE_INITIALIZATION_ERROR
    if encoded:
        assert encoded.decode("ascii", "ignore") not in str(raised.value)


def test_last_sequence_returns_zero_only_when_completed_snapshot_is_absent(tmp_path: Path) -> None:
    exporter = load_exporter()
    snapshot_path = tmp_path / "snapshots" / "latest_snapshot_v1.json"

    assert exporter._load_last_sequence(str(snapshot_path)) == 0

    snapshot_path.parent.mkdir(parents=True)
    snapshot_path.write_bytes(completed_sequence_payload(exporter, 41))
    (snapshot_path.parent / "latest_snapshot_v1.json.tmp").write_bytes(b"stale-partial-data")
    assert exporter._load_last_sequence(str(snapshot_path)) == 41


def test_last_sequence_filesystem_probe_error_fails_closed(monkeypatch, tmp_path: Path) -> None:
    exporter = load_exporter()
    snapshot_path = tmp_path / "snapshots" / "latest_snapshot_v1.json"

    def deny_probe(_path):
        raise OSError(13, "synthetic access denial")

    monkeypatch.setattr(exporter.os, "lstat", deny_probe)
    with pytest.raises(ValueError) as raised:
        exporter._load_last_sequence(str(snapshot_path))

    assert str(raised.value) == exporter.SAFE_INITIALIZATION_ERROR
    assert "synthetic" not in str(raised.value)


def _invalid_completed_snapshot_payloads():
    base = {
        "schema_version": 1,
        "bridge_version": "qmt_builtin_readonly_bridge_v1",
        "sequence": 5,
        "snapshot_id": "qmt-5",
    }

    def changed(**values):
        payload = dict(base)
        payload.update(values)
        return json.dumps(payload).encode("utf-8")

    def missing(name):
        payload = dict(base)
        del payload[name]
        return json.dumps(payload).encode("utf-8")

    return [
        pytest.param(b"", id="empty"),
        pytest.param(b"\xff", id="invalid_utf8"),
        pytest.param(b"{", id="malformed_json"),
        pytest.param(b"[]", id="non_object"),
        pytest.param(missing("schema_version"), id="missing_schema"),
        pytest.param(changed(schema_version=True), id="boolean_schema"),
        pytest.param(changed(schema_version=1.0), id="float_schema"),
        pytest.param(changed(schema_version=2), id="unsupported_schema"),
        pytest.param(missing("bridge_version"), id="missing_bridge"),
        pytest.param(changed(bridge_version=1), id="non_string_bridge"),
        pytest.param(changed(bridge_version="other"), id="unsupported_bridge"),
        pytest.param(missing("sequence"), id="missing_sequence"),
        pytest.param(changed(sequence=True, snapshot_id="qmt-True"), id="boolean_sequence"),
        pytest.param(changed(sequence=0, snapshot_id="qmt-0"), id="zero_sequence"),
        pytest.param(changed(sequence=-1, snapshot_id="qmt--1"), id="negative_sequence"),
        pytest.param(changed(sequence=5.0, snapshot_id="qmt-5.0"), id="float_sequence"),
        pytest.param(changed(sequence="5", snapshot_id="qmt-5"), id="string_sequence"),
        pytest.param(missing("snapshot_id"), id="missing_snapshot_id"),
        pytest.param(changed(snapshot_id="qmt-4"), id="mismatched_snapshot_id"),
        pytest.param(changed(snapshot_id=5), id="non_string_snapshot_id"),
        pytest.param(
            b'{"schema_version":1,"schema_version":1,'
            b'"bridge_version":"qmt_builtin_readonly_bridge_v1",'
            b'"sequence":5,"snapshot_id":"qmt-5"}',
            id="duplicate_key",
        ),
        pytest.param(
            b'{"schema_version":1,"bridge_version":"qmt_builtin_readonly_bridge_v1",'
            b'"sequence":5,"snapshot_id":"qmt-5","unknown":NaN}',
            id="non_standard_json_constant",
        ),
    ]


@pytest.mark.parametrize("encoded", _invalid_completed_snapshot_payloads())
def test_present_invalid_completed_snapshot_always_raises_fixed_safe_error(
    tmp_path: Path, encoded: bytes
) -> None:
    exporter = load_exporter()
    snapshot_path = tmp_path / "snapshots" / "latest_snapshot_v1.json"
    snapshot_path.parent.mkdir(parents=True)
    snapshot_path.write_bytes(encoded)

    with pytest.raises(ValueError) as raised:
        exporter._load_last_sequence(str(snapshot_path))

    assert str(raised.value) == exporter.SAFE_INITIALIZATION_ERROR
    assert snapshot_path.read_bytes() == encoded


def test_present_oversized_or_non_file_completed_snapshot_is_invalid(tmp_path: Path) -> None:
    exporter = load_exporter()
    snapshot_path = tmp_path / "snapshots" / "latest_snapshot_v1.json"
    snapshot_path.parent.mkdir(parents=True)
    snapshot_path.write_bytes(b"x" * (exporter.MAX_EXISTING_SNAPSHOT_BYTES + 1))

    with pytest.raises(ValueError, match=re.escape(exporter.SAFE_INITIALIZATION_ERROR)):
        exporter._load_last_sequence(str(snapshot_path))

    snapshot_path.unlink()
    snapshot_path.mkdir()
    with pytest.raises(ValueError, match=re.escape(exporter.SAFE_INITIALIZATION_ERROR)):
        exporter._load_last_sequence(str(snapshot_path))


@pytest.mark.parametrize("key_bytes", [None, b"AA" * 32])
def test_init_missing_or_invalid_binding_key_fails_closed_and_releases_lock(
    tmp_path: Path, key_bytes: bytes | None
) -> None:
    exporter = load_exporter("qmt_exporter_bad_key")
    exporter.BRIDGE_ROOT = str(tmp_path)
    exporter.account = "account-must-not-appear"
    exporter.accountType = "STOCK"
    if key_bytes is not None:
        write_binding_key(tmp_path, key_bytes)

    with pytest.raises(RuntimeError) as raised:
        exporter.init(NoTimerContext())

    assert str(raised.value) == exporter.SAFE_INITIALIZATION_ERROR
    assert "account-must-not-appear" not in str(raised.value)
    assert exporter.G.lock_handle is None
    assert exporter.G.lock_fd is None
    assert exporter.G.account_id is None
    assert exporter.G.redacted_account_id is None
    verifier = load_exporter("qmt_exporter_key_lock_verifier")
    assert verifier._acquire_writer_lock(str(tmp_path)) is True
    verifier._release_writer_lock()


def test_init_invalid_final_never_replaces_it_and_releases_lock(tmp_path: Path) -> None:
    exporter = load_exporter("qmt_exporter_bad_final")
    exporter.BRIDGE_ROOT = str(tmp_path)
    exporter.account = "account-must-not-appear"
    exporter.accountType = "STOCK"
    write_binding_key(tmp_path)
    snapshot_path = tmp_path / "snapshots" / "latest_snapshot_v1.json"
    snapshot_path.parent.mkdir(parents=True)
    original = b'{"malformed":'
    snapshot_path.write_bytes(original)

    with pytest.raises(RuntimeError) as raised:
        exporter.init(NoTimerContext())

    assert str(raised.value) == exporter.SAFE_INITIALIZATION_ERROR
    assert snapshot_path.read_bytes() == original
    assert exporter.G.lock_handle is None
    assert exporter.G.lock_fd is None
    assert exporter.G.account_id is None
    verifier = load_exporter("qmt_exporter_final_lock_verifier")
    assert verifier._acquire_writer_lock(str(tmp_path)) is True
    verifier._release_writer_lock()


def test_valid_final_with_stale_temp_resumes_and_replaces_only_from_handlebar(
    tmp_path: Path,
) -> None:
    exporter = load_exporter("qmt_exporter_resume")
    configure_exporter(exporter, tmp_path, "resume-account", "STOCK")
    paths = exporter._bridge_paths(str(tmp_path))
    snapshot_path = Path(paths["snapshot"])
    temporary_path = Path(paths["temporary"])
    snapshot_path.parent.mkdir(parents=True)
    original = completed_sequence_payload(exporter, 41)
    snapshot_path.write_bytes(original)
    temporary_path.write_bytes(b"stale-partial-data")
    queried = []
    exporter.get_trade_detail_data = successful_query(queried)

    exporter.init(NoTimerContext())
    assert exporter.G.sequence == 41
    assert snapshot_path.read_bytes() == original
    assert temporary_path.read_bytes() == b"stale-partial-data"

    exporter.after_init(NoTimerContext())
    assert exporter.G.query_due is True
    assert queried == []
    assert snapshot_path.read_bytes() == original
    assert temporary_path.read_bytes() == b"stale-partial-data"

    exporter.handlebar(NoTimerContext())
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert payload["sequence"] == 42
    assert payload["snapshot_id"] == "qmt-42"
    assert queried == [
        ("resume-account", "STOCK", "account"),
        ("resume-account", "STOCK", "position"),
        ("resume-account", "STOCK", "order"),
        ("resume-account", "STOCK", "deal"),
    ]
    assert not temporary_path.exists()
    assert BINDING_KEY_HEX not in snapshot_path.read_bytes()
    assert BINDING_KEY not in snapshot_path.read_bytes()
    exporter.stop(NoTimerContext())


@pytest.mark.parametrize(
    ("failed_data_type", "failed_section"),
    [
        pytest.param("account", "account", id="account"),
        pytest.param("position", "positions", id="position"),
        pytest.param("order", "orders", id="order"),
        pytest.param("deal", "trades", id="deal"),
    ],
)
def test_attribute_error_is_isolated_by_section_and_completed_snapshot_consumes_due_cycle(
    monkeypatch,
    tmp_path: Path,
    failed_data_type: str,
    failed_section: str,
) -> None:
    exporter = load_exporter("qmt_exporter_section_failure_{0}".format(failed_data_type))
    raw_account = "raw-account-secret"
    configure_exporter(exporter, tmp_path, raw_account, "STOCK")
    calls = []
    now = [100.0]
    monkeypatch.setattr(exporter, "time", SimpleNamespace(monotonic=lambda: now[0]))

    def fake_query(account_id, account_type, data_type):
        calls.append((account_id, account_type, data_type))
        if data_type == failed_data_type:
            raise AttributeError(
                "provider details intentionally suppressed for {0}".format(raw_account)
            )
        if data_type == "account":
            return [
                SimpleNamespace(
                    m_strAccountID=raw_account,
                    m_strAccountKey="raw-account-key",
                    m_dBalance=1000.0,
                    m_strStatus="connected",
                    m_strTradingDate="20260714",
                )
            ]
        return []

    exporter.get_trade_detail_data = fake_query
    context = RecordingContext()
    exporter.init(context)
    exporter.after_init(context)
    exporter.handlebar(context)

    assert calls == [
        (raw_account, "STOCK", "account"),
        (raw_account, "STOCK", "position"),
        (raw_account, "STOCK", "order"),
        (raw_account, "STOCK", "deal"),
    ]
    snapshot_path = tmp_path / "snapshots" / "latest_snapshot_v1.json"
    payload = snapshot_path.read_bytes()
    snapshot = json.loads(payload)
    assert snapshot["snapshot_id"] == "qmt-1"
    assert snapshot["environment"] == "simulation_signal"
    for section in ("account", "positions", "orders", "trades"):
        expected = (
            {"ok": False, "error": "qmt_query_failed"}
            if section == failed_section
            else {"ok": True, "error": None}
        )
        assert snapshot["query_status"][section] == expected
    assert snapshot["failures"] == [
        {
            "section": failed_section,
            "code": "qmt_query_failed",
            "message": "QMT read-only {0} query failed".format(failed_section),
            "exception_type": "AttributeError",
        }
    ]
    if failed_section == "account":
        assert snapshot["account"] is None
    else:
        assert snapshot["account"]["total_assets"] == 1000.0
    assert snapshot["positions"] == []
    assert snapshot["orders"] == []
    assert snapshot["trades"] == []
    assert snapshot["safety"] == {
        "order_submission_enabled": False,
        "cancel_enabled": False,
        "passorder_invoked": False,
        "cancel_invoked": False,
    }
    assert raw_account.encode() not in payload
    assert b"raw-account-key" not in payload
    assert b"provider details intentionally suppressed" not in payload
    assert b"Traceback" not in payload
    assert BINDING_KEY_HEX not in payload
    assert BINDING_KEY not in payload
    assert not (tmp_path / "snapshots" / "latest_snapshot_v1.json.tmp").exists()
    assert snapshot["sequence"] == 1
    assert exporter.G.sequence == 1
    assert exporter.G.query_due is False

    exporter.handlebar(context)
    assert len(calls) == 4
    assert exporter.G.sequence == 1
    exporter.stop(context)


def test_serialization_is_compact_sorted_and_deterministic() -> None:
    exporter = load_exporter()
    payload = {"z": [3, 2, 1], "a": {"b": False, "a": None}}

    first = exporter._serialize_snapshot(payload)
    second = exporter._serialize_snapshot(payload)

    assert first == second == b'{"a":{"a":null,"b":false},"z":[3,2,1]}'


def test_duplicate_writer_is_rejected_and_stop_releases_fallback_lock(tmp_path: Path) -> None:
    first = load_exporter("qmt_exporter_first")
    second = load_exporter("qmt_exporter_second")

    assert first._acquire_writer_lock(str(tmp_path)) is True
    try:
        assert first._acquire_writer_lock(str(tmp_path)) is False
        assert second._acquire_writer_lock(str(tmp_path)) is False
    finally:
        first._release_writer_lock()
        second._release_writer_lock()

    assert second._acquire_writer_lock(str(tmp_path)) is True
    second._release_writer_lock()


def test_non_handlebar_lifecycle_callbacks_only_schedule_due_work(tmp_path: Path) -> None:
    exporter = load_exporter("qmt_exporter_non_handlebar_lifecycle")
    configure_exporter(exporter, tmp_path)
    queried = []
    exporter.get_trade_detail_data = successful_query(queried)
    context = RecordingContext()
    snapshot_path = tmp_path / "snapshots" / "latest_snapshot_v1.json"

    exporter.init(context)
    assert queried == []
    assert exporter.G.query_due is False
    assert not snapshot_path.exists()
    assert context.timer_calls == [
        (
            "export_qmt_snapshot",
            "{0}nSecond".format(exporter.HEARTBEAT_INTERVAL_SECONDS),
            "2019-10-14 13:20:00",
        )
    ]

    exporter.handlebar(context)
    assert queried == []
    assert exporter.G.query_due is False
    assert not snapshot_path.exists()

    exporter.after_init(context)
    assert queried == []
    assert exporter.G.query_due is True
    assert not snapshot_path.exists()

    exporter.export_qmt_snapshot(context)
    exporter.export_qmt_snapshot(context)
    assert queried == []
    assert exporter.G.query_due is True
    assert not snapshot_path.exists()

    exporter.stop(context)
    assert queried == []
    assert exporter.G.stopped is True
    assert exporter.G.query_due is False
    assert exporter.G.account_id is None
    assert exporter.G.lock_handle is None
    assert exporter.G.lock_fd is None


def test_due_handlebar_queries_exact_order_with_raw_args_and_writes_once(
    monkeypatch,
    tmp_path: Path,
) -> None:
    exporter = load_exporter("qmt_exporter_exact_due_cycle")
    raw_account = "  injected-account  "
    raw_account_type = "stock"
    configure_exporter(exporter, tmp_path, raw_account, raw_account_type)
    queried = []
    exporter.get_trade_detail_data = successful_query(queried)
    context = RecordingContext()
    now = [100.0]
    monkeypatch.setattr(exporter, "time", SimpleNamespace(monotonic=lambda: now[0]))
    original_atomic_write = exporter._atomic_write
    writes = []

    def recording_atomic_write(snapshot, root=None):
        writes.append((snapshot["sequence"], root))
        return original_atomic_write(snapshot, root)

    monkeypatch.setattr(exporter, "_atomic_write", recording_atomic_write)
    exporter.init(context)
    exporter.after_init(context)
    exporter.export_qmt_snapshot(context)
    exporter.export_qmt_snapshot(context)
    exporter.handlebar(context)

    assert queried == [
        (raw_account, raw_account_type, "account"),
        (raw_account, raw_account_type, "position"),
        (raw_account, raw_account_type, "order"),
        (raw_account, raw_account_type, "deal"),
    ]
    assert writes == [(1, str(tmp_path.resolve()))]
    assert exporter.G.query_due is False
    assert exporter.G.query_in_progress is False
    assert exporter.G.sequence == 1
    snapshot_path = tmp_path / "snapshots" / "latest_snapshot_v1.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert snapshot["sequence"] == 1
    assert snapshot["account_type"] == "STOCK"
    assert snapshot["query_status"]["positions"] == {"ok": True, "error": None}
    assert snapshot["query_status"]["orders"] == {"ok": True, "error": None}
    assert snapshot["query_status"]["trades"] == {"ok": True, "error": None}
    assert raw_account.encode() not in snapshot_path.read_bytes()
    assert not (tmp_path / "snapshots" / "latest_snapshot_v1.json.tmp").exists()

    exporter.handlebar(context)
    assert len(queried) == 4
    assert len(writes) == 1
    exporter.stop(context)


def test_scheduled_due_cycle_remains_interval_throttled(monkeypatch, tmp_path: Path) -> None:
    exporter = load_exporter("qmt_exporter_throttled_due_cycle")
    configure_exporter(exporter, tmp_path)
    queried = []
    exporter.get_trade_detail_data = successful_query(queried)
    context = RecordingContext()
    now = [100.0]
    monkeypatch.setattr(exporter, "time", SimpleNamespace(monotonic=lambda: now[0]))

    exporter.init(context)
    exporter.after_init(context)
    exporter.handlebar(context)
    assert len(queried) == 4
    assert exporter.G.sequence == 1

    exporter.export_qmt_snapshot(context)
    assert exporter.G.query_due is True
    assert len(queried) == 4

    now[0] += exporter.HEARTBEAT_INTERVAL_SECONDS - 0.001
    exporter.handlebar(context)
    exporter.handlebar(context)
    assert exporter.G.query_due is True
    assert len(queried) == 4
    assert exporter.G.sequence == 1

    now[0] += 0.001
    exporter.handlebar(context)
    assert len(queried) == 8
    assert exporter.G.query_due is False
    assert exporter.G.sequence == 2
    exporter.stop(context)


def test_timer_unavailable_fallback_schedules_only_after_interval(
    monkeypatch,
    tmp_path: Path,
) -> None:
    exporter = load_exporter("qmt_exporter_timer_fallback")
    configure_exporter(exporter, tmp_path)
    queried = []
    exporter.get_trade_detail_data = successful_query(queried)
    context = RecordingContext(timer_error=RuntimeError("timer unavailable in offline test"))
    now = [100.0]
    monkeypatch.setattr(exporter, "time", SimpleNamespace(monotonic=lambda: now[0]))

    exporter.init(context)
    assert exporter.G.timer_registered is False
    assert exporter.G.timer_error_type == "RuntimeError"
    exporter.after_init(context)
    assert queried == []
    exporter.handlebar(context)
    assert len(queried) == 4

    now[0] += exporter.HEARTBEAT_INTERVAL_SECONDS - 0.001
    exporter.handlebar(context)
    assert len(queried) == 4
    assert exporter.G.query_due is False

    now[0] += 0.001
    exporter.handlebar(context)
    assert len(queried) == 8
    assert exporter.G.sequence == 2
    assert exporter.G.query_due is False
    exporter.stop(context)


def test_snapshot_write_failure_preserves_due_cycle_for_later_handlebar_retry(
    monkeypatch,
    tmp_path: Path,
) -> None:
    exporter = load_exporter("qmt_exporter_write_retry")
    configure_exporter(exporter, tmp_path)
    queried = []
    exporter.get_trade_detail_data = successful_query(queried)
    context = RecordingContext()
    now = [100.0]
    monkeypatch.setattr(exporter, "time", SimpleNamespace(monotonic=lambda: now[0]))
    original_atomic_write = exporter._atomic_write
    write_attempts = []

    def fail_once(snapshot, root=None):
        write_attempts.append(snapshot["sequence"])
        if len(write_attempts) == 1:
            raise OSError("synthetic atomic write failure")
        return original_atomic_write(snapshot, root)

    monkeypatch.setattr(exporter, "_atomic_write", fail_once)
    exporter.init(context)
    exporter.after_init(context)

    with pytest.raises(OSError, match="synthetic atomic write failure"):
        exporter.handlebar(context)

    assert len(queried) == 4
    assert write_attempts == [1]
    assert exporter.G.sequence == 0
    assert exporter.G.query_due is True
    assert exporter.G.query_in_progress is False
    assert exporter.G.in_write is False
    assert not (tmp_path / "snapshots" / "latest_snapshot_v1.json").exists()

    exporter.handlebar(context)
    assert len(queried) == 4
    assert exporter.G.query_due is True

    now[0] += exporter.HEARTBEAT_INTERVAL_SECONDS
    exporter.handlebar(context)
    assert len(queried) == 8
    assert write_attempts == [1, 1]
    assert exporter.G.sequence == 1
    assert exporter.G.query_due is False
    assert (tmp_path / "snapshots" / "latest_snapshot_v1.json").is_file()
    exporter.stop(context)


def test_reentrant_handlebar_is_blocked_and_timer_due_is_not_lost(
    monkeypatch,
    tmp_path: Path,
) -> None:
    exporter = load_exporter("qmt_exporter_reentrant_cycle")
    configure_exporter(exporter, tmp_path)
    context = RecordingContext()
    calls = []
    writes = []
    reentered = [False]
    now = [100.0]
    monkeypatch.setattr(exporter, "time", SimpleNamespace(monotonic=lambda: now[0]))
    original_atomic_write = exporter._atomic_write

    def recording_atomic_write(snapshot, root=None):
        writes.append(snapshot["sequence"])
        return original_atomic_write(snapshot, root)

    def reentrant_query(account_id, account_type, data_type):
        calls.append((account_id, account_type, data_type))
        if data_type == "account" and not reentered[0]:
            reentered[0] = True
            exporter.handlebar(context)
            exporter.export_qmt_snapshot(context)
        if data_type == "account":
            return [SimpleNamespace(m_dBalance=1000.0)]
        return []

    monkeypatch.setattr(exporter, "_atomic_write", recording_atomic_write)
    exporter.get_trade_detail_data = reentrant_query
    exporter.init(context)
    exporter.after_init(context)
    exporter.handlebar(context)

    assert [data_type for _, _, data_type in calls] == [
        "account",
        "position",
        "order",
        "deal",
    ]
    assert writes == [1]
    assert exporter.G.sequence == 1
    assert exporter.G.query_in_progress is False
    assert exporter.G.query_due_after_current is False
    assert exporter.G.query_due is True

    exporter.handlebar(context)
    assert len(calls) == 4
    assert writes == [1]

    now[0] += exporter.HEARTBEAT_INTERVAL_SECONDS
    exporter.handlebar(context)
    assert [data_type for _, _, data_type in calls] == [
        "account",
        "position",
        "order",
        "deal",
        "account",
        "position",
        "order",
        "deal",
    ]
    assert writes == [1, 2]
    assert exporter.G.sequence == 2
    assert exporter.G.query_due is False

    exporter.stop(context)
