from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "tools" / "manual_backtest_prototypes" / "rqalpha_local_run_attempt.py"
SRC_ROOT = ROOT / "src"


def _script_text() -> str:
    return SCRIPT_PATH.read_text(encoding="utf-8")


def _load_script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "rqalpha_local_run_attempt_contract_subject",
        SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rqalpha_local_run_attempt_script_exists() -> None:
    assert SCRIPT_PATH.exists()


def test_rqalpha_local_run_attempt_artifact_path_is_declared() -> None:
    text = _script_text()

    assert "local_artifacts" in text
    assert "backtest_prototypes" in text
    assert "rqalpha_local_run_result.json" in text


def test_production_source_does_not_import_rqalpha_for_run_attempt() -> None:
    violations: list[str] = []
    for path in SRC_ROOT.rglob("*.py"):
        relative = path.relative_to(SRC_ROOT)
        text = path.read_text(encoding="utf-8").lower()
        for fragment in ("import rqalpha", "from rqalpha"):
            if fragment in text:
                violations.append(f"{relative}: {fragment}")

    assert violations == []


def test_production_source_does_not_use_process_or_network_for_run_attempt() -> None:
    violations: list[str] = []
    checked_roots = (
        SRC_ROOT / "quantpilot_core" / "rqalpha_isolated_prototype_runner_review",
        SRC_ROOT / "quantpilot_core" / "rqalpha_data_bundle_config_review",
        SRC_ROOT / "quantpilot_core" / "rqalpha_ashare_backtest_adapter",
    )
    forbidden = (
        "subprocess",
        "requests.",
        "urllib.request",
        "http.client",
        "httpx",
        "socket",
        "os.system",
    )

    for checked_root in checked_roots:
        for path in checked_root.rglob("*.py"):
            relative = path.relative_to(SRC_ROOT)
            text = path.read_text(encoding="utf-8").lower()
            for fragment in forbidden:
                if fragment in text:
                    violations.append(f"{relative}: {fragment}")

    assert violations == []


def test_script_contains_no_live_trading_module_or_broker_execution_surfaces() -> None:
    text = _script_text().lower()
    forbidden = (
        "mod-ctp",
        "mod_vnpy",
        "mod-vnpy",
        "connect_broker",
        "submit_order",
        "place_order",
        "send_order",
        "enable_live_trading",
    )

    assert [fragment for fragment in forbidden if fragment in text] == []


def test_script_contains_explicit_failure_fields() -> None:
    text = _script_text()

    for field in (
        "status",
        "failure_stage",
        "error_type",
        "error_message",
        "traceback_tail",
        "data_bundle_required_or_missing",
    ):
        assert field in text


def test_script_documents_metrics_must_not_be_invented() -> None:
    text = _script_text().lower()

    assert "metrics must not be invented" in text
    assert "explicit_metrics only copies explicit allowed metric keys" in text
    assert "allowed_metric_keys" in text
    assert "observed_trade_rows is evidence metadata" in text


def test_script_does_not_derive_trade_count_from_trade_rows() -> None:
    text = _script_text()

    assert 'explicit_metrics["trade_count"] = len(trades)' not in text
    assert "observed_trade_rows" in text


def test_trade_rows_are_metadata_not_explicit_metrics() -> None:
    module = _load_script_module()

    explicit_metrics, observed_trade_rows, report_keys, result_keys = (
        module._collect_metric_candidates(
            {
                "metrics": {
                    "total_return": 0.11,
                },
                "trades": [{"id": 1}, {"id": 2}],
            }
        )
    )

    assert explicit_metrics == {"total_return": 0.11}
    assert "trade_count" not in explicit_metrics
    assert observed_trade_rows == 2
    assert report_keys == []
    assert "metrics" in result_keys
