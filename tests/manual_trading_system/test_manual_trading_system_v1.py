from __future__ import annotations

import ast
import json
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import pytest

from quantpilot_core.manual_trading_system import (
    AfterCloseConfig,
    EndOfDayConfig,
    IntradayConfig,
    ManualMarketDataStore,
    PersistentMarkerPublisher,
    ResilientTDXProvider,
    acceptance_summary,
    load_manual_production_input,
    run_after_close,
    run_end_of_day,
    run_intraday,
)
from quantpilot_core.quant_firm import (
    DeepSeekAdvisoryAgent,
    DeepSeekClientConfig,
)
from quantpilot_core.real_data_provider import (
    NormalizedIntradayBar,
    ProviderName,
)
from quantpilot_core.tdx_manual_signal_bridge import tq_visibility
import scripts.run_quantpilot_manual_system_v1 as manual_cli
from scripts.run_quantpilot_manual_system_v1 import _parser


SHANGHAI = ZoneInfo("Asia/Shanghai")


def _production_input(path: Path, *, symbols: tuple[str, ...] = ("000001.SZ", "600519.SH")) -> Path:
    rows = []
    for offset, symbol in enumerate(symbols):
        rows.extend(
            [
                {
                    "symbol": symbol,
                    "date": "2026-08-02",
                    "open": 9.8 + offset,
                    "high": 10.1 + offset,
                    "low": 9.7 + offset,
                    "close": 9.9 + offset,
                    "volume": 10000,
                },
                {
                    "symbol": symbol,
                    "date": "2026-08-03",
                    "open": 9.9 + offset,
                    "high": 10.2 + offset,
                    "low": 9.8 + offset,
                    "close": 10.0 + offset,
                    "volume": 11000,
                },
            ]
        )
    payload = {
        "symbols": list(symbols),
        "bars": rows,
        "information_signals": [
            {
                "signal": {"signal_id": "known-at-close"},
                "available_at": "2026-08-03T14:00:00+08:00",
            }
        ],
        "information_provenance": {
            "daily_production_input_v1": {
                "decision_session": "2026-08-03",
                "future_market_rows_serialized": 0,
                "selected_scores": {symbol: 0.9 - index * 0.1 for index, symbol in enumerate(symbols)},
            }
        },
        "quant_firm_context": {
            "daily_production_input_v1": {
                "decision_session": "2026-08-03",
                "execution_session": "2026-08-04",
            }
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class _FakeRealTransport:
    def __init__(self, *, failing_roles: set[str] | None = None, secret: str | None = None) -> None:
        self.failing_roles = failing_roles or set()
        self.secret = secret
        self.calls: list[Mapping[str, Any]] = []
        self.physical_request_count = 0

    def __call__(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls.append(request)
        self.physical_request_count += 1
        prompt = str(request["messages"][1]["content"])
        role = next(
            role
            for role in (
                "investment_committee", "research_desk", "information_desk",
                "backtest_desk", "portfolio_desk", "execution_simulation_desk",
                "learning_desk",
            )
            if f"Role: {role}" in prompt
        )
        if role in self.failing_roles:
            detail = f" authorization={self.secret}" if self.secret else ""
            raise RuntimeError(f"provider failure{detail}")
        return {
            "content": f"real response for {role}",
            "finish_reason": "stop",
            "model": "deepseek-v4-flash",
            "usage": {
                "prompt_tokens": 100,
                "prompt_cache_hit_tokens": 10,
                "completion_tokens": 20,
            },
        }


def _live_agent(transport: _FakeRealTransport) -> DeepSeekAdvisoryAgent:
    return DeepSeekAdvisoryAgent(
        DeepSeekClientConfig(enable_live_call=True),
        live_client=transport,
    )


def test_after_close_runs_seven_live_desks_writes_first_and_preserves_qpty_symbols(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "process-only-secret")
    input_path = _production_input(tmp_path / "input dir" / "production input.json")
    root = tmp_path / "system dir with spaces"
    transport = _FakeRealTransport(failing_roles={"backtest_desk"})
    agent = _live_agent(transport)
    publication_calls = []

    def publish(plan: Mapping[str, Any], report_path: str) -> Mapping[str, Any]:
        durable = json.loads(Path(report_path).read_text(encoding="utf-8"))
        assert durable["tdx_publication"]["status"] == "not_attempted_before_durable_report"
        symbols = [item["symbol"] for item in plan["candidates"]]
        publication_calls.append(symbols)
        return {
            "visibility_success": True,
            "block_code": "QPTY",
            "block_name": "QP候选",
            "published_symbols": symbols,
        }

    report = run_after_close(
        AfterCloseConfig(input_path, root, live_ai=True),
        advisory_agent=agent,
        visibility_publisher=publish,
        clock=lambda: datetime(2026, 8, 3, 16, 0, tzinfo=SHANGHAI),
    )

    assert len(transport.calls) == 7
    assert report["deepseek"]["physical_model_calls"] == 7
    assert report["deepseek"]["successful_desk_count"] == 6
    assert report["deepseek"]["status"] == "partial_desk_success"
    assert report["deepseek"]["actual_models"] == ["deepseek-v4-flash"]
    assert all(
        item["output"]["raw_response_usage"]["prompt_tokens"] == 100
        for item in report["deepseek"]["desks"]
        if item["status"] == "succeeded"
    )
    assert report["final_watchlist"] == ["000001.SZ", "600519.SH"]
    assert [item["manual_decision"] for item in report["candidate_decisions"]] == ["WAIT", "WAIT"]
    assert publication_calls == [["000001.SZ", "600519.SH"]]
    assert report["tdx_publication"]["published_symbols"] == report["final_watchlist"]
    assert report["durable_report_existed_before_tdx_publication"] is True
    assert Path(report["durable_report_path"]).is_file()
    report_bytes = Path(report["durable_report_path"]).read_bytes()
    parsed_utf8_report = json.loads(report_bytes.decode("utf-8"))
    assert parsed_utf8_report["tdx_publication"]["block_name"] == "QP候选"
    assert report["broker_calls"] == report["order_submission_calls"] == 0


@pytest.mark.parametrize("fail_all", [False, True])
def test_missing_key_or_all_desk_failure_never_erases_watchlist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fail_all: bool
) -> None:
    input_path = _production_input(tmp_path / "production.json")
    root = tmp_path / ("all fail" if fail_all else "key absent")
    if fail_all:
        monkeypatch.setenv("DEEPSEEK_API_KEY", "secret-value")
        transport = _FakeRealTransport(failing_roles={role for role in (
            "investment_committee", "research_desk", "information_desk", "backtest_desk",
            "portfolio_desk", "execution_simulation_desk", "learning_desk",
        )}, secret="secret-value")
        agent = _live_agent(transport)
    else:
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        transport = _FakeRealTransport()
        agent = _live_agent(transport)
    report = run_after_close(
        AfterCloseConfig(input_path, root, live_ai=True), advisory_agent=agent
    )
    assert report["final_watchlist"] == ["000001.SZ", "600519.SH"]
    assert report["watchlist_preserved"] is True
    assert len(report["candidate_decisions"]) == 2
    if fail_all:
        assert report["deepseek"]["physical_model_calls"] == 7
        assert "all_desks_failed" in report["deepseek"]["status"]
        persisted = "\n".join(
            path.read_text(encoding="utf-8")
            for path in root.rglob("*") if path.is_file()
        )
        assert "secret-value" not in persisted
        assert "<redacted>" in persisted
        assert report["broker_calls"] == report["order_submission_calls"] == 0
    else:
        assert not transport.calls
        assert report["deepseek"]["physical_model_calls"] == 0
        assert report["deepseek"]["status"] == "credential_unavailable_watchlist_retained"


def test_seven_real_transport_responses_are_counted_and_costed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "process-secret")
    transport = _FakeRealTransport()
    report = run_after_close(
        AfterCloseConfig(_production_input(tmp_path / "input.json"), tmp_path / "system", live_ai=True),
        advisory_agent=_live_agent(transport),
        clock=lambda: datetime(2026, 8, 3, 16, 0, tzinfo=SHANGHAI),
    )
    assert transport.physical_request_count == 7
    assert report["deepseek"]["physical_model_calls"] == 7
    assert report["deepseek"]["successful_desk_count"] == 7
    assert report["deepseek"]["actual_models"] == ["deepseek-v4-flash"]
    assert report["deepseek"]["estimated_api_cost_usd"] > 0
    assert all(item["physical_call"] is True for item in report["deepseek"]["desks"])
    assert all(item["status"] == "succeeded" for item in report["deepseek"]["desks"])
    assert all(item["output"]["is_fallback"] is False for item in report["deepseek"]["desks"])
    assert all(item["output"]["used_model"] == "deepseek-v4-flash" for item in report["deepseek"]["desks"])
    assert all(
        item["output"]["raw_response_usage"]["completion_tokens"] == 20
        for item in report["deepseek"]["desks"]
    )


def test_provider_bad_request_error_is_failed_physical_call_with_redaction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class BadRequestError(RuntimeError):
        pass

    class _BadRequestTransport:
        def __init__(self) -> None:
            self.physical_request_count = 0

        def __call__(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
            self.physical_request_count += 1
            raise BadRequestError(
                "400 Prompt must contain the word 'json' in some form to use "
                "'response_format' of type 'json_object'. authorization=process-secret"
            )

    monkeypatch.setenv("DEEPSEEK_API_KEY", "process-secret")
    input_path = _production_input(tmp_path / "production.json")
    root = tmp_path / "provider 400"
    transport = _BadRequestTransport()
    report = run_after_close(
        AfterCloseConfig(input_path, root, live_ai=True),
        advisory_agent=_live_agent(transport),
    )
    assert transport.physical_request_count == 7
    assert report["deepseek"]["physical_model_calls"] == 7
    assert report["deepseek"]["successful_desk_count"] == 0
    assert report["deepseek"]["actual_models"] == []
    assert all(item["status"] == "failed" for item in report["deepseek"]["desks"])
    assert all(item["physical_call"] is True for item in report["deepseek"]["desks"])
    assert all(
        "process-secret" not in item["sanitized_error"]
        for item in report["deepseek"]["desks"]
    )
    assert all(
        "<redacted>" in item["sanitized_error"]
        for item in report["deepseek"]["desks"]
    )
    assert report["final_watchlist"] == ["000001.SZ", "600519.SH"]
    assert report["watchlist_preserved"] is True
    assert report["broker_calls"] == report["order_submission_calls"] == 0


def test_pre_transport_failure_never_counts_as_physical_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _OfflineTransport:
        def __init__(self) -> None:
            self.physical_request_count = 0

        def __call__(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
            raise RuntimeError("missing optional client dependency before transport")

    monkeypatch.setenv("DEEPSEEK_API_KEY", "process-secret")
    report = run_after_close(
        AfterCloseConfig(
            _production_input(tmp_path / "production.json"),
            tmp_path / "system",
            live_ai=True,
        ),
        advisory_agent=_live_agent(_OfflineTransport()),
    )
    assert report["deepseek"]["physical_model_calls"] == 0
    assert report["deepseek"]["successful_desk_count"] == 0
    assert all(item["status"] == "failed" for item in report["deepseek"]["desks"])
    assert all(item["physical_call"] is False for item in report["deepseek"]["desks"])
    assert report["final_watchlist"] == ["000001.SZ", "600519.SH"]
    assert report["watchlist_preserved"] is True
    assert report["broker_calls"] == report["order_submission_calls"] == 0


def test_deterministic_fallback_never_counts_as_physical_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "present-but-client-offline")
    fallback_agent = DeepSeekAdvisoryAgent(
        DeepSeekClientConfig(enable_live_call=False)
    )
    report = run_after_close(
        AfterCloseConfig(_production_input(tmp_path / "input.json"), tmp_path / "system", live_ai=True),
        advisory_agent=fallback_agent,
    )
    assert report["deepseek"]["physical_model_calls"] == 0
    assert report["deepseek"]["successful_desk_count"] == 0
    assert report["deepseek"]["actual_models"] == []
    assert report["deepseek"]["estimated_api_cost_usd"] == 0.0
    assert all(item["status"] == "fallback" for item in report["deepseek"]["desks"])
    assert all(item["physical_call"] is False for item in report["deepseek"]["desks"])


def test_minimal_input_rejects_future_rows_without_account_fee_or_manifest_gates(tmp_path: Path) -> None:
    path = _production_input(tmp_path / "production.json")
    value = load_manual_production_input(path)
    assert value["validation"] == {
        "minimal_manual_contract": True,
        "future_market_rows": 0,
        "candidate_count": 2,
        "account_capability_checked": False,
        "fee_profile_checked": False,
        "manifest_digest_equality_checked": False,
        "continuous_paper_checked": False,
        "database_checked": False,
    }
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["bars"][0]["date"] = "2026-08-05"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="future"):
        load_manual_production_input(path)

    path = _production_input(tmp_path / "future information.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["information_signals"][0]["available_at"] = "2026-08-03T15:00:01+08:00"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="future information"):
        load_manual_production_input(path)


def _marker(symbol: str, timestamp: str, state: str, *, signal_id: str) -> Mapping[str, Any]:
    labels = {"ENTRY": "买", "HOLD": "持", "WEAKENING": "弱", "EXIT": "卖", "INVALIDATED": "失效"}
    return {
        "schema_version": "tdx_prediction_signal_v1",
        "signal_id": signal_id,
        "symbol": symbol,
        "timestamp": timestamp,
        "decision_timestamp": timestamp,
        "state": state,
        "state_label_zh": labels[state],
        "decision_price": 10.0,
        "entry_probability": 0.7,
        "continuation_probability": 0.6,
        "exit_probability": 0.3,
        "expected_return": 0.01,
        "entry_zone_low": 9.9,
        "entry_zone_high": 10.1,
        "invalidation_price": 9.7,
        "first_target_price": 10.4,
        "intraday_score": 0.2,
        "material_change": True,
        "reason_code": "causal_completed_bar",
    }


def test_marker_ledger_is_persistent_deduplicated_and_repaint_safe(tmp_path: Path) -> None:
    root = tmp_path / "marker output"
    publisher = PersistentMarkerPublisher(root)
    publisher.initialize_wait_states(
        ("000001.SZ",), timestamp="2026-08-04T09:30:00+08:00", reference_prices={"000001.SZ": 10.0}
    )
    entry = _marker("000001.SZ", "2026-08-04T10:45:00+08:00", "ENTRY", signal_id="entry-1")
    publisher((entry,))
    publisher((entry,))
    assert len(publisher.records) == 2
    assert publisher.report()["duplicate_transition_count"] == 1
    assert [item["state"] for item in publisher.records] == ["WAIT", "ENTRY"]
    assert (root / "marker_events.csv").is_file()
    formula = (root / "formula_bundle" / "QP_MANUAL_MARKERS.formula.txt").read_text(encoding="utf-8")
    assert all(label in formula for label in ("买", "持", "弱", "卖", "失效"))

    resumed = PersistentMarkerPublisher(root)
    resumed((entry,))
    assert len(resumed.records) == 2
    older = _marker("000001.SZ", "2026-08-04T10:00:00+08:00", "HOLD", signal_id="late-backfill")
    with pytest.raises(ValueError, match="non-causal"):
        resumed((older,))
    assert len(resumed.records) == 2


def test_marker_restart_republishes_persisted_baseline_without_live_warning(tmp_path: Path) -> None:
    class Delegate:
        def __init__(self) -> None:
            self.baselines = []

        def publish_baseline(self, records: Any) -> Mapping[str, Any]:
            self.baselines.append(tuple(records))
            return {"historical_baseline": True}

    root = tmp_path / "markers"
    first = PersistentMarkerPublisher(root)
    first((_marker("000001.SZ", "2026-08-04T10:45:00+08:00", "ENTRY", signal_id="entry"),))
    delegate = Delegate()
    resumed = PersistentMarkerPublisher(root, delegate=delegate)
    report = resumed.restore_transport_baseline()
    assert len(delegate.baselines) == 1
    assert [item["signal_id"] for item in delegate.baselines[0]] == ["entry"]
    assert report["transport"] == {"historical_baseline": True}


class _Provider:
    provider_name = ProviderName.TDX_LEVEL1

    def __init__(self) -> None:
        self._api = object()
        self.closed = False

    def initialize(self) -> None:
        return None

    def get_historical_intraday_bars(self, *_args: Any, **_kwargs: Any) -> tuple[Any, ...]:
        return ()

    def get_market_snapshot(self, _symbols: Any) -> tuple[Any, ...]:
        return ()

    def subscribe_hq(self, _symbols: Any, _callback: Any) -> object:
        return object()

    def unsubscribe_hq(self, _subscription: Any) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    def callback_diagnostics(self) -> Mapping[str, Any]:
        return {}


class _Collector:
    def __init__(self, provider: Any, symbols: Any, *, sink: Any, **_kwargs: Any) -> None:
        self.provider = provider
        self.symbols = tuple(symbols)
        self.sink = sink

    def run(self, _duration: float) -> Mapping[str, Any]:
        self.provider.close()
        return {
            "connection_status": "subscribed",
            "symbols": self.symbols,
            "snapshot_count": 1,
            "event_count": 0,
            "bar_count": 0,
        }


def test_resilient_provider_keeps_other_symbols_after_one_snapshot_failure() -> None:
    class Delegate:
        provider_name = ProviderName.TDX_LEVEL1

        def get_market_snapshot(self, symbols: Any) -> tuple[str, ...]:
            if tuple(symbols) == ("000001.SZ",):
                raise RuntimeError("one symbol unavailable")
            return tuple(symbols)

    provider = ResilientTDXProvider(Delegate())
    result = provider.get_market_snapshot(("000001.SZ", "600519.SH"))
    assert result == ("600519.SH",)
    assert provider.errors[0]["symbol"] == "000001.SZ"
    assert provider.errors[0]["error_type"] == "RuntimeError"


def test_intraday_starts_without_account_and_restart_does_not_duplicate_wait(tmp_path: Path) -> None:
    input_path = _production_input(tmp_path / "production.json")
    root = tmp_path / "runtime with spaces"
    run_after_close(AfterCloseConfig(input_path, root, live_ai=False))
    first = run_intraday(
        IntradayConfig(root, "D:/tongdaxin/PYPlugins/user", duration_seconds=0, publish_to_tq=False),
        provider=_Provider(),
        collector_factory=_Collector,
    )
    second = run_intraday(
        IntradayConfig(root, "D:/tongdaxin/PYPlugins/user", duration_seconds=0, publish_to_tq=False),
        provider=_Provider(),
        collector_factory=_Collector,
    )
    assert first["service_started"] is second["service_started"] is True
    assert first["state_machine"]["states"][0] == "WAIT"
    assert second["marker_adapter"]["persisted_transition_count"] == 2
    states = json.loads((root / "intraday" / "current_states.json").read_text(encoding="utf-8"))
    assert set(states) == {"000001.SZ", "600519.SH"}
    assert all(item["state"] == "WAIT" for item in states.values())
    assert first["broker_calls"] == first["order_submission_calls"] == 0


def _bar(symbol: str, minute: int, close: float) -> NormalizedIntradayBar:
    start = datetime(2026, 8, 4, 14, 58, tzinfo=SHANGHAI) + timedelta(minutes=minute)
    return NormalizedIntradayBar(
        symbol=symbol,
        start=start,
        end=start + timedelta(minutes=1),
        interval_minutes=1,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1000,
        amount=1000 * close,
        average_price=close,
        event_count=1,
    )


def test_market_store_replaces_restart_partial_with_completed_bar(tmp_path: Path) -> None:
    store = ManualMarketDataStore(tmp_path / "intraday")
    partial = replace(_bar("000001.SZ", 0, 10.0), partial=True)
    completed = replace(_bar("000001.SZ", 0, 10.2), partial=False)
    store.persist_market_data((), (partial,))
    store.persist_market_data((), (completed,))
    assert len(store.bar_records()) == 1
    assert store.bar_records()[0]["partial"] is False
    assert store.bar_records()[0]["close"] == 10.2


def test_end_of_day_report_contains_candidate_and_signal_accuracy(tmp_path: Path) -> None:
    input_path = _production_input(tmp_path / "production.json")
    root = tmp_path / "system"
    run_after_close(AfterCloseConfig(input_path, root, live_ai=False))
    store = ManualMarketDataStore(root / "intraday")
    store.persist_market_data((), (_bar("000001.SZ", 0, 10.5), _bar("600519.SH", 0, 10.5)))
    publisher = PersistentMarkerPublisher(root / "intraday")
    publisher((_marker("000001.SZ", "2026-08-04T10:45:00+08:00", "ENTRY", signal_id="entry-1"),))
    report = run_end_of_day(EndOfDayConfig(root))
    assert report["original_deterministic_candidates"] == ["000001.SZ", "600519.SH"]
    assert report["candidate_accuracy_counts"] == {"hit": 1, "miss": 1, "unresolved": 0}
    assert report["signal_accuracy_counts"] == {"hit": 1, "miss": 0, "unresolved": 0}
    assert report["entry_marker_timestamps"] == ["2026-08-04T10:45:00+08:00"]
    assert report["no_lookahead_audit"]["passed"] is True
    assert Path(report["human_report_path"]).is_file()
    assert report["broker_calls"] == report["order_submission_calls"] == 0


def test_live_tq_marker_transport_reuses_injected_level1_api(monkeypatch: pytest.MonkeyPatch) -> None:
    api = object()
    calls = []

    def publish(records: Any, **kwargs: Any) -> Mapping[str, Any]:
        calls.append((records, kwargs))
        return {"transport_accepted": True}

    monkeypatch.setattr(tq_visibility, "publish_to_tq", publish)
    monkeypatch.setattr(
        tq_visibility,
        "publish_transition_warnings",
        lambda records, *, api: {"warning_count": len(records), "api_matches": api is not None},
    )
    publisher = tq_visibility.LiveTQVisibilityPublisher(api=api)
    publisher((_marker("000001.SZ", "2026-08-04T10:45:00+08:00", "ENTRY", signal_id="entry"),))
    assert calls[0][1]["api"] is api
    assert calls[0][1]["manage_tq_lifecycle"] is False


def test_cli_has_all_daily_actions_and_explicit_qpty_defaults() -> None:
    parser = _parser()
    after = parser.parse_args([
        "after-close", "--production-input", r"D:\Data Folder\production input.json",
        "--tdx-user-dir", r"D:\tongdaxin\PYPlugins\user",
    ])
    assert after.tq_block_code == "QPTY"
    assert after.tq_block_name == "QP候选"
    assert after.live_ai is True
    explicitly_enabled = parser.parse_args([
        "after-close", "--production-input", r"D:\Data\input.json",
        "--tdx-user-dir", r"D:\tongdaxin\PYPlugins\user", "--enable-live-ai",
    ])
    assert explicitly_enabled.live_ai is True
    for phase in ("intraday", "end-of-day"):
        args = [phase]
        if phase == "intraday":
            args += ["--tdx-user-dir", r"D:\tongdaxin\PYPlugins\user"]
        assert parser.parse_args(args).phase == phase


def test_cli_stdout_is_ascii_json_safe_for_windows_powershell_51(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        manual_cli,
        "_run_after",
        lambda _args: {"phase": "after-close", "block_name": "QP候选"},
    )
    exit_code = manual_cli.main([
        "after-close", "--production-input", r"D:\Data\input.json",
        "--tdx-user-dir", r"D:\tongdaxin\PYPlugins\user",
    ])
    stdout = capsys.readouterr().out
    assert exit_code == 0
    assert stdout.isascii()
    assert json.loads(stdout)["block_name"] == "QP候选"


def test_windows_wrappers_are_ascii_and_json_reads_force_utf8() -> None:
    wrapper_root = Path("scripts/windows")
    wrappers = tuple(sorted(wrapper_root.glob("*.ps1")))
    assert wrappers
    for path in wrappers:
        raw = path.read_bytes()
        assert raw.isascii(), f"PowerShell 5.1-unsafe source encoding: {path}"
        text = raw.decode("ascii")
        for line in text.splitlines():
            if "Get-Content" in line:
                assert "-Encoding UTF8" in line
    common = (wrapper_root / "manual_system_common_v1.ps1").read_text(encoding="ascii")
    assert "Get-Content -LiteralPath $Path -Raw -Encoding UTF8" in common
    assert "ConvertFrom-Json" in common


def test_acceptance_never_turns_transport_into_visual_proof(tmp_path: Path) -> None:
    durable = tmp_path / "after_close_report.json"
    durable.write_text("{}", encoding="utf-8")
    result = acceptance_summary(
        {
            "deepseek": {
                "physical_model_calls": 7,
                "successful_desk_count": 7,
                "actual_models": ["deepseek-v4-flash"],
            },
            "durable_report_path": str(durable),
            "final_watchlist": ["000001.SZ"],
            "tdx_publication": {"visibility_success": True, "transport_response": {"ErrorId": 0}},
            "broker_calls": 0,
            "order_submission_calls": 0,
        },
        {
            "service_started": True,
            "marker_adapter": {
                "marker_adapter_initialized": True,
                "ordinary_chart_overlay_status": "pending_windows_visual_confirmation",
            },
            "broker_calls": 0,
            "order_submission_calls": 0,
        },
    )
    assert result["automated_checks_passed"] is True
    assert result["accepted"] is False
    assert result["ordinary_chart_overlay_proven"] is False
    assert result["transport_success_is_visual_proof"] is False


def test_manual_workflow_module_has_no_broker_order_or_continuous_paper_imports() -> None:
    source_path = Path("src/quantpilot_core/manual_trading_system/system.py")
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert not any(
        forbidden in name
        for name in imported
        for forbidden in ("broker", "order", "continuous_paper", "paper_trading", "account_capability")
    )
