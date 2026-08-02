from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import scripts.run_tdx_prediction_integration_v1 as runner
from quantpilot_core.real_data_provider import NormalizedIntradayBar


SHANGHAI = ZoneInfo("Asia/Shanghai")


def _bars() -> tuple[NormalizedIntradayBar, ...]:
    start = datetime(2026, 8, 3, 9, 30, tzinfo=SHANGHAI)
    output = []
    price = 10.0
    for index in range(60):
        opened = price
        price *= 1.001
        output.append(
            NormalizedIntradayBar(
                symbol="000001.SZ",
                start=start + timedelta(minutes=index),
                end=start + timedelta(minutes=index + 1),
                interval_minutes=1,
                open=opened,
                high=price * 1.001,
                low=opened * 0.999,
                close=price,
                volume=10_000,
                amount=10_000 * price,
                average_price=price,
                event_count=1,
            )
        )
    return tuple(output)


class _Provider:
    def __init__(self, _path) -> None:
        self.initialized = 0
        self.closed = 0
        self.history_call = None

    def initialize(self) -> None:
        self.initialized += 1

    def get_historical_intraday_bars(self, symbols, **kwargs):
        self.history_call = {"symbols": tuple(symbols), **kwargs}
        return _bars()

    def close(self) -> None:
        self.closed += 1


def test_replay_cli_uses_real_pr130_history_method_and_writes_artifacts(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    providers = []

    def provider(path):
        value = _Provider(path)
        providers.append(value)
        return value

    monkeypatch.setattr(runner, "TDXLevel1Provider", provider)
    result = runner.main(
        [
            "--mode", "replay",
            "--symbols", "000001.SZ",
            "--tdx-user-dir", r"D:\tongdaxin\PYPlugins\user",
            "--history-count", "60",
            "--report-path", str(tmp_path / "report.json"),
            "--tdx-output-dir", str(tmp_path / "tdx"),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 0
    assert payload["status"] == "ok"
    assert payload["mode"] == "replay"
    assert payload["signal_count_by_state"].keys() == {
        "WATCH", "ENTRY", "HOLD", "WEAKENING", "EXIT", "INVALIDATED"
    }
    assert payload["lifecycle_counts"].keys() == {
        "lifecycle_started_count",
        "lifecycle_completed_count",
        "open_lifecycle_count",
        "exit_count",
        "invalidation_count",
    }
    assert providers[0].history_call["period"] == "1m"
    assert providers[0].history_call["fields"] == (
        "Open", "High", "Low", "Close", "Volume", "Amount"
    )
    assert providers[0].closed == 1
    assert Path(payload["report_path"]).exists()
    assert Path(payload["tdx_json_path"]).exists()


def test_live_shadow_cli_reuses_engine_and_never_requests_broker_calls(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    class Store:
        def persist_market_data(self, _events, _bars):
            return None

    class Collector:
        def __init__(self, _provider, _symbols, **kwargs):
            self.sink = kwargs["sink"]

        def run(self, _duration):
            return SimpleNamespace(
                as_dict=lambda: {
                    "connection_status": "subscribed",
                    "event_count": 1,
                    "bar_count": 1,
                }
            )

    monkeypatch.setattr(runner, "TDXLevel1Provider", _Provider)
    monkeypatch.setattr(runner, "LiveLevel1Collector", Collector)
    monkeypatch.setattr(
        runner,
        "initialize_reporting_store",
        lambda _name: (Store(), "memory"),
    )

    result = runner.main(
        [
            "--mode", "live-shadow",
            "--symbols", "000001.SZ",
            "--tdx-user-dir", r"D:\tongdaxin\PYPlugins\user",
            "--duration", "0",
            "--history-count", "60",
            "--report-path", str(tmp_path / "live.json"),
            "--tdx-output-dir", str(tmp_path / "tdx"),
            "--store-provider", "memory",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 0
    assert payload["mode"] == "live-shadow"
    assert payload["broker_or_order_api_calls"] is False
    assert payload["deepseek_live_calls"] is False
    assert payload["prediction_engine"] == "tdx_prediction_engine_v1"
    assert "lifecycle_counts" in payload


def test_live_shadow_cli_uses_plan_for_candidate_block_and_warning_publisher(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    class Store:
        def persist_market_data(self, _events, _bars):
            return None

    class Collector:
        def __init__(self, _provider, symbols, **kwargs):
            assert tuple(symbols) == ("000001.SZ",)
            assert kwargs["sink"].publisher is warning_publisher

        def run(self, _duration):
            return SimpleNamespace(
                as_dict=lambda: {
                    "connection_status": "polling_fallback",
                    "event_count": 0,
                    "bar_count": 0,
                }
            )

    plan = {
        "schema_version": "tdx_next_day_experience_plan_v1",
        "plan_id": "tdx-plan-test",
        "generated_at": "2026-08-03T16:30:00+08:00",
        "data_asof": "2026-08-03T15:00:00+08:00",
        "decision_session": "2026-08-03",
        "target_session": "2026-08-04",
        "candidates": [
            {
                "symbol": "000001.SZ",
                "candidate_rank": 1,
                "candidate_confidence": 0.7,
                "deepseek_stance": "bullish",
                "timestamps": {"data_asof": "2026-08-03T15:00:00+08:00"},
                "provenance": {"evidence_refs": ["candidate:test"]},
            }
        ],
        "ai_analysis": {"roles": []},
    }
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    block_calls = []
    warning_publisher = lambda _records: {"warning_fallback_active": True}

    monkeypatch.setattr(runner, "TDXLevel1Provider", _Provider)
    monkeypatch.setattr(runner, "LiveLevel1Collector", Collector)
    monkeypatch.setattr(
        runner,
        "initialize_reporting_store",
        lambda _name: (Store(), "memory"),
    )
    monkeypatch.setattr(
        runner,
        "publish_experience_plan_visibility",
        lambda value, **kwargs: block_calls.append((value, kwargs))
        or {
            "status": "candidate_block_published",
            "sector_create_response": {"accepted": True, "error_id": 0},
            "user_block_response": {"accepted": True, "error_id": 0},
            "message_response": {"accepted": True, "error_id": 0},
            "block_code": kwargs["block_code"],
            "block_name": kwargs["block_name"],
            "published_symbols": ["000001.SZ"],
            "visibility_success": True,
        },
    )
    monkeypatch.setattr(
        runner,
        "LiveTQVisibilityPublisher",
        lambda **_kwargs: warning_publisher,
    )

    result = runner.main(
        [
            "--mode", "live-shadow",
            "--experience-plan", str(plan_path),
            "--tdx-user-dir", r"D:\tongdaxin\PYPlugins\user",
            "--duration", "0",
            "--history-count", "60",
            "--report-path", str(tmp_path / "live.json"),
            "--tdx-output-dir", str(tmp_path / "tdx"),
            "--store-provider", "memory",
            "--publish-to-tq",
            "--tq-block-code", "QPX1",
            "--tq-block-name", "量化候选",
            "--no-tq-block-show",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 0
    assert block_calls[0][0] == plan
    assert block_calls[0][1] == {
        "block_code": "QPX1",
        "block_name": "量化候选",
        "show": False,
    }
    assert payload["tq_plan_visibility"]["status"] == "candidate_block_published"
    assert payload["block_code"] == "QPX1"
    assert payload["block_name"] == "量化候选"
    assert payload["published_symbols"] == ["000001.SZ"]
    assert payload["visibility_success"] is True
    assert payload["tq_warning_fallback_active"] is True


def test_direct_cli_imports_with_only_src_on_pythonpath() -> None:
    root = Path(__file__).resolve().parents[2]
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(root / "src")

    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "run_tdx_prediction_integration_v1.py"),
            "--help",
        ],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "live-shadow" in result.stdout


def test_prediction_cli_has_no_private_script_import() -> None:
    source = Path(runner.__file__).read_text(encoding="utf-8")

    assert "from scripts." not in source
    assert "import scripts." not in source
