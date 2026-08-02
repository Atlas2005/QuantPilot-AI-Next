from __future__ import annotations

from datetime import date, timedelta
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from quantpilot_core.continuous_paper import (
    ContinuousPaperCycle,
    ContinuousPaperCycleConfig,
    InMemoryReportingStore,
    load_production_input_payload,
    load_production_pipeline_config,
)
from quantpilot_core.daily_production_input import (
    AUTHORITATIVE_PRODUCTION_PRESELECTOR,
    DailyProductionInputConfig,
    DailyProductionInputError,
    build_daily_production_input_v1,
)
from quantpilot_core.daily_paper_loop.state import payload_digest
from quantpilot_core.production_candidate import (
    build_production_candidate_manifest,
    write_manifest_atomic,
)
from quantpilot_core.real_candidate_pipeline import (
    build_real_candidate_daily_paper_input,
)
from quantpilot_core.real_data_provider import (
    NormalizedDailyBar,
    ProviderName,
    TradingCalendar,
)
from quantpilot_core.tdx_manual_signal_bridge.tq_visibility import (
    publish_experience_plan_visibility,
)
from quantpilot_core.tdx_prediction_integration import (
    build_next_day_experience_plan_v1,
)


SYMBOLS = (
    "000001.SZ",
    "000002.SZ",
    "000003.SZ",
    "000004.SZ",
    "600000.SH",
    "600001.SH",
    "600002.SH",  # suspended on D
    "600003.SH",  # zero volume on D
    "430001.BJ",  # outside the existing production input symbol contract
)


def _sessions() -> tuple[date, ...]:
    rows = []
    cursor = date(2026, 1, 5)
    while len(rows) < 62:
        if cursor.weekday() < 5:
            rows.append(cursor)
        cursor += timedelta(days=1)
    return tuple(rows)


class _Loader:
    def __init__(self, sessions: tuple[date, ...]) -> None:
        self._sessions = sessions

    def sessions(self):
        return tuple(day.strftime("%Y%m%d") for day in self._sessions)

    def listed_universe(self, _day):
        return tuple({"ts_code": symbol} for symbol in SYMBOLS)

    def daily(self, day):
        assert day == self._sessions[-2].strftime("%Y%m%d")
        return tuple({"ts_code": symbol} for symbol in SYMBOLS)


class _Bars:
    def __init__(self, sessions: tuple[date, ...], *, keep: int | None = None) -> None:
        self.sessions = sessions
        self.keep = keep

    def fetch_many_daily_bars_with_empty_symbols(self, requests):
        bars = []
        requested = tuple(request.symbol for request in requests)
        allowed = set(requested[: self.keep]) if self.keep is not None else set(requested)
        for request in requests:
            if request.symbol not in allowed:
                continue
            symbol_index = SYMBOLS.index(request.symbol)
            for session_index, session in enumerate(self.sessions):
                if not request.start_date <= session <= request.end_date:
                    continue
                close = 8.0 + symbol_index + session_index * (0.01 + symbol_index * 0.001)
                volume = 0.0 if request.symbol == "600003.SH" and session == self.sessions[-2] else 100_000.0 + symbol_index
                bars.append(
                    NormalizedDailyBar(
                        symbol=request.symbol,
                        trade_date=session,
                        open=close,
                        high=close + 0.2,
                        low=close - 0.2,
                        close=close,
                        previous_close=close - 0.01,
                        volume=volume,
                        amount=close * volume,
                        provider=ProviderName.SNAPSHOT,
                    )
                )
        bars.sort(key=lambda bar: (bar.symbol, bar.trade_date))
        present = {bar.symbol for bar in bars}
        return bars, tuple(symbol for symbol in requested if symbol not in present)

    def tradability_metadata(self, start_date, end_date):
        assert start_date == end_date == self.sessions[-2]
        return {
            "a_share_tradability_metadata": {
                "enabled": True,
                "primary_price_provider": ProviderName.SNAPSHOT.value,
                "fetched_at": f"{start_date.isoformat()}T15:00:00+08:00",
                "tradability_overrides": [
                    {
                        "trade_date": start_date.isoformat(),
                        "symbol": symbol,
                        "is_suspended": symbol == "600002.SH",
                        "upper_limit": 50.0,
                        "lower_limit": 1.0,
                        "source": ProviderName.SNAPSHOT.value,
                        "data_quality": "snapshot",
                    }
                    for symbol in SYMBOLS
                ],
            }
        }


def _manifest(tmp_path: Path, *, target: int = 2, maximum: int = 6):
    tmp_path.mkdir(parents=True, exist_ok=True)
    pr121 = tmp_path / "pr121.json"
    pr122 = tmp_path / "pr122.json"
    pr121.write_text("{}", encoding="utf-8")
    pr122.write_text("{}", encoding="utf-8")
    return build_production_candidate_manifest(
        created_at="2026-07-12T00:00:00+00:00",
        code_revision="manifest-revision",
        snapshot_digest="a" * 64,
        benchmark={"symbol": "000300.SH"},
        source_artifacts={"pr121": pr121, "pr122": pr122},
        frozen_strategy_parameters={
            "initial_capital": 100_000.0,
            "target_symbol_count": target,
            "max_execution_symbols": maximum,
            "strategy_id": "equal_weight_baseline",
        },
        frozen_portfolio_parameters={
            "target_position_count": target,
            "max_position_weight": 0.1,
            "reserve_cash_weight": 0.02,
        },
        frozen_execution_parameters={"min_order_lot": 100},
        fee_profile_policy={
            "profile_id": "engineering-fallback-from-paper-fill-cost-assumptions",
            "required_provenance": "engineering_fallback",
        },
        account_capability_policy={"capability_digest": payload_digest(None)},
    )


def _validation(sessions: tuple[date, ...]):
    return SimpleNamespace(
        ok=True,
        errors=(),
        manifest={
            "status": "completed",
            "digest": "b" * 64,
            "requested_date_range": {
                "start": sessions[0].strftime("%Y%m%d"),
                "end": sessions[-1].strftime("%Y%m%d"),
            },
            "actual_date_range": {
                "start": sessions[0].strftime("%Y%m%d"),
                "end": sessions[-1].strftime("%Y%m%d"),
            },
            "capabilities": {"suspend": "available", "limits": "available"},
        },
    )


def _build(tmp_path: Path, *, target: int = 2, bars=None):
    sessions = _sessions()
    return build_daily_production_input_v1(
        DailyProductionInputConfig(
            production_manifest=_manifest(tmp_path, target=target),
            snapshot_root=tmp_path / "snapshot",
            requested_decision_session=sessions[-2].isoformat(),
            runtime_code_revision="runtime-revision",
        ),
        snapshot_loader=_Loader(sessions),
        bar_provider=bars or _Bars(sessions),
        snapshot_validation=_validation(sessions),
    )


def test_manifest_cap_filters_pit_cutoff_schema_and_deterministic_order(tmp_path):
    first = _build(tmp_path / "first")
    second = _build(tmp_path / "second")
    payload = first.payload
    assert first.ranking_method == AUTHORITATIVE_PRODUCTION_PRESELECTOR
    assert first.selected_symbols == second.selected_symbols
    assert 1 <= len(first.selected_symbols) == 2 <= 6
    assert set(payload) == {
        "symbols",
        "bars",
        "information_signals",
        "information_provenance",
        "advisory_provenance",
        "quant_firm_context",
    }
    assert payload["symbols"] == list(first.selected_symbols)
    assert "430001.BJ" not in payload["symbols"]
    assert "600002.SH" not in payload["symbols"]
    assert "600003.SH" not in payload["symbols"]
    assert max(date.fromisoformat(row["date"]) for row in payload["bars"]) == date.fromisoformat(first.decision_session)
    assert payload["information_provenance"]["daily_production_input_v1"]["future_market_rows_serialized"] == 0
    assert payload["advisory_provenance"]["deepseek_live_call"] is False


def test_payload_round_trips_and_serialized_calendar_binds_continuous_paper(tmp_path):
    result = _build(tmp_path / "build")
    input_path = tmp_path / "production_input.json"
    input_path.write_text(json.dumps(result.payload), encoding="utf-8")
    manifest_path = write_manifest_atomic(
        _manifest(tmp_path / "manifest"), tmp_path / "manifest.json"
    )
    loaded = load_production_input_payload(input_path)
    config = load_production_pipeline_config(
        manifest_path=manifest_path,
        decision_session=result.decision_session,
        state_path=tmp_path / "state.json",
        report_path=tmp_path / "report.json",
        input_payload=loaded,
    )
    expected_calendar = tuple(
        result.payload["quant_firm_context"]["daily_production_input_v1"][
            "calendar_sessions"
        ]
    )
    assert config.symbols == result.selected_symbols
    assert config.input_calendar_sessions == expected_calendar
    assert config.input_calendar_provider == ProviderName.SNAPSHOT.value
    built = build_real_candidate_daily_paper_input(config)
    assert {candidate.symbol for candidate in built.candidate_report.candidates} == set(
        result.selected_symbols
    )
    cycle = ContinuousPaperCycle(InMemoryReportingStore()).run_once(
        ContinuousPaperCycleConfig(config, run_id="daily-input-compatibility")
    )
    assert cycle.status in {"completed", "no_trade", "idempotent_replay"}
    report = json.loads(Path(config.report_path).read_text(encoding="utf-8"))
    plan = build_next_day_experience_plan_v1(
        report, generated_at=f"{result.decision_session}T15:00:00+08:00"
    )

    class Api:
        def __init__(self):
            self.calls = []

        def create_sector(self, block_code, block_name):
            self.calls.append(("create", block_code, block_name))
            return {"ErrorId": 0}

        def send_user_block(self, block_code, stocks, show):
            self.calls.append(("block", block_code, tuple(stocks), show))
            return {"ErrorId": 0}

        def send_message(self, message):
            self.calls.append(("message", message))
            return {"ErrorId": 0}

    api = Api()
    visibility = publish_experience_plan_visibility(plan, api=api)
    assert visibility["visibility_success"] is True
    assert visibility["block_code"] == "QPTY"
    assert set(visibility["published_symbols"]) == set(result.selected_symbols)
    assert api.calls[0] == ("create", "QPTY", "QP候选")


def test_fails_instead_of_using_fixture_when_snapshot_or_survivors_are_missing(tmp_path):
    sessions = _sessions()
    with pytest.raises(DailyProductionInputError, match="no valid PIT snapshot"):
        build_daily_production_input_v1(
            DailyProductionInputConfig(
                production_manifest=_manifest(tmp_path / "invalid"),
                snapshot_root=tmp_path / "missing",
                requested_decision_session=sessions[-2].isoformat(),
            ),
            snapshot_validation=SimpleNamespace(
                ok=False, errors=("manifest.json is missing",), manifest={}
            ),
        )
    with pytest.raises(DailyProductionInputError, match="fewer symbols"):
        _build(tmp_path / "few", target=6, bars=_Bars(sessions, keep=2))


def test_stale_cached_request_and_manifest_conflict_fail_clearly(tmp_path):
    sessions = _sessions()
    stale = _validation(sessions)
    stale.manifest["requested_date_range"]["end"] = sessions[-3].strftime("%Y%m%d")
    with pytest.raises(DailyProductionInputError, match="stale"):
        build_daily_production_input_v1(
            DailyProductionInputConfig(
                production_manifest=_manifest(tmp_path / "stale"),
                snapshot_root=tmp_path / "snapshot",
                requested_decision_session=sessions[-2].isoformat(),
            ),
            snapshot_loader=_Loader(sessions),
            bar_provider=_Bars(sessions),
            snapshot_validation=stale,
        )
    with pytest.raises(DailyProductionInputError, match="symbol counts conflict"):
        build_daily_production_input_v1(
            DailyProductionInputConfig(
                production_manifest=_manifest(tmp_path / "conflict", target=7, maximum=7),
                snapshot_root=tmp_path / "snapshot",
                requested_decision_session=sessions[-2].isoformat(),
            ),
            snapshot_loader=_Loader(sessions),
            bar_provider=_Bars(sessions),
            snapshot_validation=_validation(sessions),
        )


def _cli_module():
    path = Path(__file__).parents[2] / "scripts" / "build_daily_production_input_v1.py"
    spec = importlib.util.spec_from_file_location("daily_production_input_cli", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_real_mode_requires_environment_token_and_sanitizes_credentials(tmp_path, monkeypatch, capsys):
    module = _cli_module()
    manifest_path = write_manifest_atomic(
        _manifest(tmp_path / "manifest"), tmp_path / "manifest.json"
    )
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    rc = module.main(
        [
            "--mode",
            "tushare",
            "--production-manifest",
            manifest_path,
            "--snapshot-root",
            str(tmp_path / "snapshot"),
            "--snapshot-start-date",
            "20260101",
            "--decision-session",
            "2026-03-31",
            "--output",
            str(tmp_path / "output.json"),
        ]
    )
    assert rc == 2
    assert "TUSHARE_TOKEN is required" in capsys.readouterr().out
    placeholder = "test-only-placeholder"
    monkeypatch.setenv("TUSHARE_TOKEN", placeholder)
    assert placeholder not in module._sanitize_error(
        RuntimeError(f"token={placeholder}")
    )


def test_cached_cli_propagates_manifest_snapshot_session_and_writes_payload(
    tmp_path, monkeypatch, capsys
):
    module = _cli_module()
    manifest_path = write_manifest_atomic(
        _manifest(tmp_path / "manifest"), tmp_path / "manifest.json"
    )
    output = tmp_path / "production_input.json"
    captured = {}
    payload = {
        "symbols": ["600000.SH"],
        "bars": [],
        "information_signals": [],
        "information_provenance": {},
        "advisory_provenance": {},
        "quant_firm_context": {},
    }

    def fake_build(config, *, calendar=None):
        captured["config"] = config
        captured["calendar"] = calendar
        return SimpleNamespace(
            payload=payload,
            decision_session="2026-03-30",
            execution_session="2026-03-31",
            selected_symbols=("600000.SH",),
            tradable_universe_size=100,
            ranking_method=AUTHORITATIVE_PRODUCTION_PRESELECTOR,
            snapshot_digest="b" * 64,
            manifest_digest="c" * 64,
        )

    monkeypatch.setattr(module, "build_daily_production_input_v1", fake_build)
    assert module.main(
        [
            "--mode",
            "cached",
            "--production-manifest",
            manifest_path,
            "--snapshot-root",
            str(tmp_path / "snapshot"),
            "--decision-session",
            "2026-03-30",
            "--output",
            str(output),
        ]
    ) == 0
    assert captured["calendar"] is None
    assert captured["config"].snapshot_root == str(tmp_path / "snapshot")
    assert captured["config"].requested_decision_session == "2026-03-30"
    assert json.loads(output.read_text(encoding="utf-8")) == payload
    assert json.loads(capsys.readouterr().out)["symbols"] == ["600000.SH"]
