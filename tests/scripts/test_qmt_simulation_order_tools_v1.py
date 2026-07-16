from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest

from quantpilot_core.qmt_simulation_execution import (
    canonical_json_bytes,
    read_intent,
    reconcile_broker_records,
    redact_account_id,
    write_result_atomic,
)


CREATE_PATH = Path("scripts/create_qmt_simulation_order_intent_v1.py")
EXECUTOR_PATH = Path("scripts/qmt_builtin_simulation_executor_v1.py")
INSPECT_PATH = Path("scripts/inspect_qmt_simulation_order_v1.py")
KEY = bytes(range(32))
RAW_ACCOUNT = "offline-cli-account"
BINDING = redact_account_id(RAW_ACCOUNT, binding_key=KEY)


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _bridge(tmp_path: Path) -> Path:
    root = tmp_path / "bridge"
    key_path = root / "state" / "account_binding_key_v1.hex"
    key_path.parent.mkdir(parents=True)
    key_path.write_bytes(KEY.hex().encode("ascii"))
    return root


def _create_args(root: Path, *, confirm: bool) -> list[str]:
    args = [
        "--symbol",
        "600000.SH",
        "--side",
        "buy",
        "--quantity",
        "100",
        "--limit-price",
        "10.5",
        "--expected-redacted-account-id",
        BINDING,
        "--bridge-root",
        str(root),
        "--intent-id",
        "cli_intent_127",
        "--run-label",
        "manual-test",
    ]
    if confirm:
        args.append("--confirm-broker-simulation-order")
    return args


def _files(root: Path) -> dict[Path, bytes]:
    if not root.exists():
        return {}
    return {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_create_requires_exact_confirmation_and_changes_no_state_without_it(
    tmp_path: Path, capsys
) -> None:
    create = _load(CREATE_PATH, "create_qmt_simulation_order_intent_no_confirm")
    root = tmp_path / "must-not-exist"

    assert create.main(_create_args(root, confirm=False)) == 2
    assert not root.exists()
    assert "confirm_broker_simulation_order_required" in capsys.readouterr().err

    abbreviated = _create_args(root, confirm=False) + ["--confirm"]
    with pytest.raises(SystemExit) as error:
        create.main(abbreviated)
    assert error.value.code == 2
    assert not root.exists()


def test_confirmed_create_is_one_immutable_authenticated_intent(
    tmp_path: Path, capsys
) -> None:
    create = _load(CREATE_PATH, "create_qmt_simulation_order_intent_confirmed")
    executor = _load(
        EXECUTOR_PATH, "qmt_builtin_simulation_executor_for_created_intent"
    )
    root = _bridge(tmp_path)

    assert create.main(_create_args(root, confirm=True)) == 0
    first_output = capsys.readouterr().out
    first_files = _files(root)
    intent_files = list((root / "execution" / "intents").glob("*.json"))
    assert len(intent_files) == 1
    assert not (root / "execution" / "state").exists()
    assert not (root / "execution" / "acknowledgements").exists()
    assert json.loads(first_output)["status"] == "received"
    assert RAW_ACCOUNT not in intent_files[0].read_text(encoding="ascii")
    assert KEY.hex() not in intent_files[0].read_text(encoding="ascii")

    raw = intent_files[0].read_bytes()
    decoded = json.loads(raw.decode("utf-8"))
    assert raw == canonical_json_bytes(decoded, trailing_newline=True)
    assert raw == executor._file_bytes(decoded)
    assert raw.endswith(b"\n")
    assert not raw.endswith(b"\r\n")
    assert not raw.startswith(b"\xef\xbb\xbf")
    strict_payload, strict_raw = executor._read_bounded_json(
        str(intent_files[0]), executor.MAX_INTENT_BYTES
    )
    assert strict_payload == decoded
    assert strict_raw == raw
    executor.G.binding_key = KEY
    executor.G.redacted_account_id = BINDING
    created_at = executor._parse_utc_text(decoded["created_at"])
    assert (
        executor._validate_intent(
            strict_payload,
            strict_raw,
            str(intent_files[0]),
            created_at,
        )
        is False
    )

    repeated = create.main(_create_args(root, confirm=True))
    assert repeated in {0, 2}
    capsys.readouterr()
    assert _files(root) == first_files
    assert len(list((root / "execution" / "intents").glob("*.json"))) == 1


@pytest.mark.skipif(os.name != "nt", reason="Windows newline persistence regression")
def test_windows_production_writer_persists_exact_lf_bytes(
    tmp_path: Path, capsys
) -> None:
    create = _load(CREATE_PATH, "create_qmt_simulation_order_intent_windows_bytes")
    root = _bridge(tmp_path)

    assert create.main(_create_args(root, confirm=True)) == 0
    capsys.readouterr()
    path = root / "execution" / "intents" / "cli_intent_127.json"
    raw = path.read_bytes()
    decoded = json.loads(raw.decode("utf-8"))

    assert raw == canonical_json_bytes(decoded, trailing_newline=True)
    assert raw.endswith(b"\n")
    assert not raw.endswith(b"\r\n")


def test_inspection_is_read_only_bounded_and_never_connects_to_qmt(
    tmp_path: Path, capsys
) -> None:
    create = _load(CREATE_PATH, "create_qmt_simulation_order_for_inspection")
    inspect = _load(INSPECT_PATH, "inspect_qmt_simulation_order")
    root = _bridge(tmp_path)
    assert create.main(_create_args(root, confirm=True)) == 0
    capsys.readouterr()

    before_intent_inspection = _files(root)
    assert inspect.main(
        ["--bridge-root", str(root), "--intent-id", "cli_intent_127", "--format", "json"]
    ) == 0
    received = json.loads(capsys.readouterr().out)
    assert (received["artifact"], received["status"]) == ("intent", "received")
    assert _files(root) == before_intent_inspection

    intent = read_intent(root, "cli_intent_127")
    result = reconcile_broker_records(
        intent,
        [],
        [
            {
                "m_strRemark": intent.intent_id,
                "m_strTradeID": "deal-1",
                "m_nVolume": 100,
                "m_dPrice": 10.5,
            }
        ],
        passorder_attempted=True,
    )
    write_result_atomic(root, result)
    before_result_inspection = _files(root)
    assert inspect.main(
        ["--bridge-root", str(root), "--intent-id", intent.intent_id, "--format", "json"]
    ) == 0
    completed_text = capsys.readouterr().out
    completed = json.loads(completed_text)
    assert (completed["artifact"], completed["status"]) == (
        "acknowledgement",
        "filled",
    )
    assert RAW_ACCOUNT not in completed_text
    assert KEY.hex() not in completed_text
    assert _files(root) == before_result_inspection

    combined_source = CREATE_PATH.read_text() + INSPECT_PATH.read_text()
    assert "get_trade_detail_data" not in combined_source
    assert "passorder(" not in combined_source
    assert "xtquant" not in combined_source.casefold()


def test_powershell_wrappers_preserve_confirmation_and_read_only_boundaries() -> None:
    create_wrapper = Path("scripts/create_qmt_simulation_order_intent_v1.ps1").read_text()
    inspect_wrapper = Path("scripts/inspect_qmt_simulation_order_v1.ps1").read_text()

    assert "ConfirmBrokerSimulationOrder" in create_wrapper
    assert '"--confirm-broker-simulation-order"' in create_wrapper
    assert "create_qmt_simulation_order_intent_v1.py" in create_wrapper
    assert "inspect_qmt_simulation_order_v1.py" in inspect_wrapper
    assert "ConfirmBrokerSimulationOrder" not in inspect_wrapper
    assert "passorder" not in (create_wrapper + inspect_wrapper).casefold()
