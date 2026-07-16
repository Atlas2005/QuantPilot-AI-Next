from __future__ import annotations

import ast
import importlib.util
import json
import re
from pathlib import Path
from uuid import uuid4

import pytest


PROBE_PATH = Path("scripts/qmt_builtin_lifecycle_probe_v1.py")
RAW_ACCOUNT = "raw-probe-account-must-not-leak"
RAW_ACCOUNT_TYPE = "sensitive-injected-stock-type"


def load_probe():
    name = "qmt_builtin_lifecycle_probe_v1_{0}".format(uuid4().hex)
    spec = importlib.util.spec_from_file_location(name, PROBE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class RecordingContext:
    def __init__(self, timer_error=None, last_bar_error=None):
        self.timer_error = timer_error
        self.last_bar_error = last_bar_error
        self.timer_calls = []
        self.last_bar_calls = 0

    def run_time(self, *args):
        self.timer_calls.append(args)
        if self.timer_error is not None:
            raise self.timer_error

    def is_last_bar(self):
        self.last_bar_calls += 1
        if self.last_bar_error is not None:
            raise self.last_bar_error
        return True


def successful_query(calls, returned=None):
    def query(account_id, account_type, data_type):
        calls.append((account_id, account_type, data_type))
        return returned

    return query


def configure_probe(probe, root: Path, query):
    probe.BRIDGE_ROOT = str(root)
    probe.account = RAW_ACCOUNT
    probe.accountType = RAW_ACCOUNT_TYPE
    probe.get_trade_detail_data = query


def read_evidence(root: Path):
    path = root / "probe" / "lifecycle_probe_v1.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_source_is_ascii_gbk_python36_standard_library_and_read_only() -> None:
    source_bytes = PROBE_PATH.read_bytes()
    source = source_bytes.decode("gbk")
    tree = ast.parse(source, filename=str(PROBE_PATH), feature_version=(3, 6))

    assert source_bytes.splitlines()[0] == b"#coding:gbk"
    assert all(value < 128 for value in source_bytes)
    assert not any(
        isinstance(node, (ast.AnnAssign, ast.AsyncFunctionDef, ast.Await, ast.JoinedStr))
        for node in ast.walk(tree)
    )

    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert imports <= {"datetime", "errno", "json", "os"}
    assert "xtquant" not in source.lower()

    prohibited = {
        "passorder",
        "algo_passorder",
        "cancel",
        "cancel_order",
        "cancel_task",
        "buy",
        "sell",
        "cancelorder",
        "order_stock",
        "submit_order",
        "place_order",
        "insert_order",
        "send_order",
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
    referenced_names = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    } | {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    assert referenced_names.isdisjoint(prohibited)
    for name in prohibited:
        assert re.search(r"\b{0}\s*\(".format(re.escape(name)), source) is None


def test_query_is_direct_and_reachable_from_every_lifecycle_callback() -> None:
    source = PROBE_PATH.read_text(encoding="gbk")
    tree = ast.parse(source, filename=str(PROBE_PATH), feature_version=(3, 6))
    functions = {
        node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)
    }
    direct_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "get_trade_detail_data"
    ]
    assert len(direct_calls) == 1
    call = direct_calls[0]
    assert len(call.args) == 3
    assert call.keywords == []
    assert isinstance(call.args[0], ast.Attribute)
    assert isinstance(call.args[0].value, ast.Name)
    assert call.args[0].value.id == "G"
    assert call.args[0].attr == "account_id"
    assert isinstance(call.args[1], ast.Attribute)
    assert isinstance(call.args[1].value, ast.Name)
    assert call.args[1].value.id == "G"
    assert call.args[1].attr == "account_type"
    assert isinstance(call.args[2], ast.Name) and call.args[2].id == "query_name"

    references = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id == "get_trade_detail_data"
    ]
    assert references == [call.func]

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

    def reaches_query(name):
        pending = [name]
        visited = set()
        while pending:
            current = pending.pop()
            if current in visited:
                continue
            visited.add(current)
            if current == "_attempt_query":
                return True
            pending.extend(call_graph[current])
        return False

    assert all(
        reaches_query(name)
        for name in (
            "init",
            "after_init",
            "lifecycle_probe_timer_callback",
            "handlebar",
            "stop",
        )
    )


def test_timer_registration_success_uses_established_qmt_signature(
    monkeypatch, tmp_path: Path
) -> None:
    probe = load_probe()
    calls = []
    configure_probe(probe, tmp_path, successful_query(calls))
    monkeypatch.setattr(probe, "_utc_now_text", lambda: "2026-07-16T01:00:00Z")
    context = RecordingContext()

    probe.init(context)

    assert context.timer_calls == [
        (
            "lifecycle_probe_timer_callback",
            "{0}nSecond".format(probe.PROBE_INTERVAL_SECONDS),
            "2019-10-14 13:20:00",
        )
    ]
    payload = read_evidence(tmp_path)
    assert payload["timer_registration"] == {
        "attempted": True,
        "succeeded": True,
        "exception_type": None,
    }
    assert payload["lifecycle"]["init"] == {
        "count": 1,
        "latest_at": "2026-07-16T01:00:00Z",
    }
    assert calls == [
        (RAW_ACCOUNT, RAW_ACCOUNT_TYPE, name) for name in probe.QUERY_NAMES
    ]


@pytest.mark.parametrize(
    ("timer_error", "expected_exception_type"),
    [
        pytest.param(
            RuntimeError("secret provider detail " + RAW_ACCOUNT),
            "RuntimeError",
            id="ordinary_exception_type",
        ),
        pytest.param(
            type("T" * 81, (Exception,), {})("secret provider detail " + RAW_ACCOUNT),
            "Exception",
            id="overlong_exception_type",
        ),
    ],
)
def test_timer_registration_failure_is_bounded_and_does_not_crash(
    monkeypatch, tmp_path: Path, timer_error, expected_exception_type: str
) -> None:
    probe = load_probe()
    calls = []
    configure_probe(probe, tmp_path, successful_query(calls))
    monkeypatch.setattr(probe, "_utc_now_text", lambda: "2026-07-16T01:01:00Z")
    context = RecordingContext(timer_error=timer_error)

    probe.init(context)

    payload = read_evidence(tmp_path)
    assert payload["timer_registration"] == {
        "attempted": True,
        "succeeded": False,
        "exception_type": expected_exception_type,
    }
    encoded = (tmp_path / "probe" / "lifecycle_probe_v1.json").read_bytes()
    assert RAW_ACCOUNT.encode("ascii") not in encoded
    assert b"secret provider detail" not in encoded


def test_exception_class_name_cannot_leak_injected_identity(
    monkeypatch, tmp_path: Path
) -> None:
    probe = load_probe()
    raw_account = "123456789"
    probe.BRIDGE_ROOT = str(tmp_path)
    probe.account = raw_account
    probe.accountType = "STOCK"
    probe.get_trade_detail_data = successful_query([])
    monkeypatch.setattr(probe, "_utc_now_text", lambda: "2026-07-16T01:02:00Z")
    sensitive_error = type("Account123456789Error", (Exception,), {})

    probe.init(RecordingContext(timer_error=sensitive_error("private")))

    payload = read_evidence(tmp_path)
    assert payload["timer_registration"]["exception_type"] == "Exception"
    assert raw_account not in json.dumps(payload)


def test_exact_lifecycle_counts_latest_timestamps_and_one_query_cycle_each(
    monkeypatch, tmp_path: Path
) -> None:
    probe = load_probe()
    calls = []
    configure_probe(probe, tmp_path, successful_query(calls, returned=[object()]))
    timestamps = iter(
        "2026-07-16T02:00:{0:02d}Z".format(index) for index in range(8)
    )
    monkeypatch.setattr(probe, "_utc_now_text", lambda: next(timestamps))
    context = RecordingContext()

    probe.init(context)
    probe.after_init(context)
    probe.after_init(context)
    probe.lifecycle_probe_timer_callback(context)
    probe.lifecycle_probe_timer_callback(context)
    probe.handlebar(context)
    probe.handlebar(context)
    probe.stop(context)

    payload = read_evidence(tmp_path)
    assert payload["schema_version"] == 1
    assert payload["protocol_version"] == "qmt_builtin_lifecycle_probe_v1"
    assert payload["started_at"] == "2026-07-16T02:00:00Z"
    assert payload["updated_at"] == "2026-07-16T02:00:07Z"
    assert payload["lifecycle"] == {
        "init": {"count": 1, "latest_at": "2026-07-16T02:00:00Z"},
        "after_init": {"count": 2, "latest_at": "2026-07-16T02:00:02Z"},
        "timer_callback": {
            "count": 2,
            "latest_at": "2026-07-16T02:00:04Z",
        },
        "handlebar": {"count": 2, "latest_at": "2026-07-16T02:00:06Z"},
        "stop": {"count": 1, "latest_at": "2026-07-16T02:00:07Z"},
    }
    expected_query_status = {
        "attempted": True,
        "succeeded": True,
        "exception_type": None,
    }
    for callback_name in probe.CALLBACK_NAMES:
        assert payload["queries"][callback_name]["attempted"] is True
        for query_name in probe.QUERY_NAMES:
            assert payload["queries"][callback_name][query_name] == expected_query_status
    assert [data_type for _, _, data_type in calls] == list(probe.QUERY_NAMES) * 5
    assert all(account_id == RAW_ACCOUNT for account_id, _, _ in calls)
    assert all(account_type == RAW_ACCOUNT_TYPE for _, account_type, _ in calls)
    assert context.last_bar_calls == 2
    assert payload["handlebar_state"] == {
        "is_last_bar_call_attempted": True,
        "is_last_bar_callable": True,
        "is_last_bar_exception_type": None,
    }
    assert payload["safety"] == {
        "order_submission_enabled": False,
        "cancel_enabled": False,
        "passorder_invoked": False,
        "cancel_invoked": False,
    }


def test_query_failures_are_isolated_for_every_callback_and_query_kind(
    monkeypatch, tmp_path: Path
) -> None:
    probe = load_probe()
    calls = []

    class ProviderQueryFailure(Exception):
        pass

    def failing_query(account_id, account_type, data_type):
        calls.append((account_id, account_type, data_type))
        raise ProviderQueryFailure(
            "provider repr and raw identity must stay private: " + RAW_ACCOUNT
        )

    configure_probe(probe, tmp_path, failing_query)
    monkeypatch.setattr(probe, "_utc_now_text", lambda: "2026-07-16T03:00:00Z")
    context = RecordingContext()

    probe.init(context)
    probe.after_init(context)
    probe.lifecycle_probe_timer_callback(context)
    probe.handlebar(context)
    probe.stop(context)

    payload = read_evidence(tmp_path)
    for callback_name in probe.CALLBACK_NAMES:
        assert payload["queries"][callback_name]["attempted"] is True
        for query_name in probe.QUERY_NAMES:
            assert payload["queries"][callback_name][query_name] == {
                "attempted": True,
                "succeeded": False,
                "exception_type": "ProviderQueryFailure",
            }
    assert len(calls) == len(probe.CALLBACK_NAMES) * len(probe.QUERY_NAMES)
    encoded = (tmp_path / "probe" / "lifecycle_probe_v1.json").read_bytes()
    assert RAW_ACCOUNT.encode("ascii") not in encoded
    assert b"provider repr" not in encoded
    assert b"Traceback" not in encoded


def test_provider_results_account_key_and_paths_never_enter_evidence(
    monkeypatch, tmp_path: Path
) -> None:
    probe = load_probe()
    repr_calls = []
    raw_key = "0123456789abcdef" * 4
    shareholder = "private-shareholder-identifier"

    class ProviderResult:
        def __repr__(self):
            repr_calls.append(True)
            return "provider-object-{0}-{1}".format(raw_key, shareholder)

    calls = []
    configure_probe(probe, tmp_path, successful_query(calls, ProviderResult()))
    probe.account_binding_key = raw_key
    monkeypatch.setattr(probe, "_utc_now_text", lambda: "2026-07-16T04:00:00Z")

    probe.init(RecordingContext())

    path = tmp_path / "probe" / "lifecycle_probe_v1.json"
    encoded = path.read_bytes()
    assert repr_calls == []
    for forbidden in (
        RAW_ACCOUNT,
        RAW_ACCOUNT_TYPE,
        raw_key,
        shareholder,
        str(tmp_path),
        "ProviderResult",
    ):
        assert forbidden.encode("utf-8") not in encoded
    assert set(json.loads(encoded)) == {
        "schema_version",
        "protocol_version",
        "started_at",
        "updated_at",
        "lifecycle",
        "timer_registration",
        "handlebar_state",
        "queries",
        "safety",
    }


def test_handlebar_records_is_last_bar_failure_without_crashing(
    monkeypatch, tmp_path: Path
) -> None:
    probe = load_probe()
    calls = []
    configure_probe(probe, tmp_path, successful_query(calls))
    monkeypatch.setattr(probe, "_utc_now_text", lambda: "2026-07-16T05:00:00Z")
    context = RecordingContext(
        last_bar_error=AttributeError("provider details must not be serialized")
    )

    probe.init(context)
    probe.handlebar(context)

    payload = read_evidence(tmp_path)
    assert payload["handlebar_state"] == {
        "is_last_bar_call_attempted": True,
        "is_last_bar_callable": False,
        "is_last_bar_exception_type": "AttributeError",
    }
    assert payload["lifecycle"]["handlebar"]["count"] == 1
    assert payload["queries"]["handlebar"]["attempted"] is True


def test_serialization_is_canonical_deterministic_and_strictly_bounded() -> None:
    probe = load_probe()
    probe._reset_state("private", "STOCK", "/private/local/path", "2026-07-16T06:00:00Z")
    probe._record_callback("init", "2026-07-16T06:00:00Z")
    payload = probe._evidence_payload()

    first = probe._canonical_bytes(payload)
    second = probe._canonical_bytes(payload)

    assert first == second
    assert first == json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    assert len(first) < probe.MAX_EVIDENCE_BYTES
    assert b"\n" not in first
    assert b"/private/local/path" not in first
    with pytest.raises(ValueError, match="fixed bound"):
        probe._canonical_bytes({"oversized": "x" * probe.MAX_EVIDENCE_BYTES})


def test_atomic_write_flushes_and_replaces_only_from_same_directory(
    monkeypatch, tmp_path: Path
) -> None:
    probe = load_probe()
    probe._reset_state("private", "STOCK", str(tmp_path), "2026-07-16T07:00:00Z")
    probe._record_callback("init", "2026-07-16T07:00:00Z")
    payload = probe._evidence_payload()
    probe_dir = tmp_path / "probe"
    probe_dir.mkdir()
    final_path = probe_dir / "lifecycle_probe_v1.json"
    final_path.write_bytes(b"old-complete-evidence")
    real_replace = probe.os.replace
    replace_calls = []
    fsync_calls = []

    def recording_fsync(file_descriptor):
        fsync_calls.append(file_descriptor)

    def inspecting_replace(source, destination):
        source_path = Path(source)
        destination_path = Path(destination)
        assert source_path.parent == destination_path.parent
        assert source_path.read_bytes() == probe._canonical_bytes(payload)
        assert destination_path.read_bytes() == b"old-complete-evidence"
        replace_calls.append((source_path, destination_path))
        real_replace(source, destination)

    monkeypatch.setattr(probe.os, "fsync", recording_fsync)
    monkeypatch.setattr(probe.os, "replace", inspecting_replace)

    written = probe._atomic_write(payload, str(tmp_path))

    assert Path(written) == final_path
    assert len(fsync_calls) == 1
    assert replace_calls == [(final_path.with_suffix(".json.tmp"), final_path)]
    assert final_path.read_bytes() == probe._canonical_bytes(payload)
    assert not final_path.with_suffix(".json.tmp").exists()


def test_write_failure_never_crashes_callback_and_later_callback_persists_record(
    monkeypatch, tmp_path: Path
) -> None:
    probe = load_probe()
    calls = []
    configure_probe(probe, tmp_path, successful_query(calls))
    monkeypatch.setattr(probe, "_utc_now_text", lambda: "2026-07-16T08:00:00Z")
    real_atomic_write = probe._atomic_write
    attempts = []

    def fail_once(payload, root=None):
        attempts.append(payload["updated_at"])
        if len(attempts) == 1:
            raise OSError("synthetic local path and provider detail")
        return real_atomic_write(payload, root)

    monkeypatch.setattr(probe, "_atomic_write", fail_once)
    context = RecordingContext()

    probe.init(context)
    assert not (tmp_path / "probe" / "lifecycle_probe_v1.json").exists()
    probe.after_init(context)

    payload = read_evidence(tmp_path)
    assert attempts == ["2026-07-16T08:00:00Z", "2026-07-16T08:00:00Z"]
    assert payload["lifecycle"]["init"]["count"] == 1
    assert payload["lifecycle"]["after_init"]["count"] == 1
    assert payload["queries"]["init"]["attempted"] is True
    assert payload["queries"]["after_init"]["attempted"] is True


def test_stop_queries_once_writes_final_record_clears_identity_and_is_idempotent(
    monkeypatch, tmp_path: Path
) -> None:
    probe = load_probe()
    calls = []
    configure_probe(probe, tmp_path, successful_query(calls))
    monkeypatch.setattr(probe, "_utc_now_text", lambda: "2026-07-16T09:00:00Z")
    context = RecordingContext()

    probe.init(context)
    probe.stop(context)
    final_path = tmp_path / "probe" / "lifecycle_probe_v1.json"
    final_bytes = final_path.read_bytes()
    assert probe.G.stopped is True
    assert probe.G.account_id is None
    assert probe.G.account_type is None
    assert read_evidence(tmp_path)["lifecycle"]["stop"]["count"] == 1
    assert calls[-4:] == [
        (RAW_ACCOUNT, RAW_ACCOUNT_TYPE, name) for name in probe.QUERY_NAMES
    ]

    probe.after_init(context)
    probe.lifecycle_probe_timer_callback(context)
    probe.handlebar(context)
    probe.stop(context)

    assert final_path.read_bytes() == final_bytes
    assert len(calls) == 8
    assert context.last_bar_calls == 0
    assert not final_path.with_suffix(".json.tmp").exists()
