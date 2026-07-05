from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from quantpilot_core.daily_paper_loop import initialize_daily_state, save_daily_state_atomic
from quantpilot_core.a_share_market_reality_execution import SettlementLot
from quantpilot_core.paper_trading import PaperAccount
from quantpilot_core.real_data_provider import Adjustment, NormalizedDailyBar, ProviderName, TradingCalendar
from scripts.run_daily_paper_loop_v1 import _build_live_market_input, main


def write_candidate_input(path: Path, symbols=("600000.SH",)) -> None:
    path.write_text(
        json.dumps(
            {
                "calendar": {"sessions": ["2026-01-02", "2026-01-05"], "provider": "baostock"},
                "strategy_id": "json-exec1",
                "aggregate_score": 0.2,
                "candidates": [
                    {
                        "symbol": symbol,
                        "direction": "long",
                        "confidence": 0.8,
                        "expected_return": 0.08,
                        "risk_score": 0.2,
                        "liquidity_score": 0.9,
                        "timestamp": "2026-01-02T14:55:00+08:00",
                        "metadata": {"candidate_id": f"json-{symbol}"},
                    }
                    for symbol in symbols
                ],
                "market": {"decision_rows_by_symbol": {}, "execution_rows_by_symbol": {}},
                "information_provenance": {"max_timestamp": "2026-01-02T15:00:00+08:00"},
            }
        ),
        encoding="utf-8",
    )


class FakeCalendarProvider:
    def __init__(self, sessions=(date(2026, 1, 2), date(2026, 1, 5), date(2026, 1, 6))) -> None:
        self.requests = []
        self.sessions = tuple(sessions)

    def fetch_calendar_with_provenance(self, start_date, end_date):
        self.requests.append((start_date, end_date))
        calendar = TradingCalendar(self.sessions, ProviderName.TUSHARE)
        return SimpleNamespace(
            selected_provider=ProviderName.TUSHARE,
            calendar=calendar,
            fallback_used=False,
            attempts=(SimpleNamespace(provider=ProviderName.TUSHARE, status="success", reason="sessions:3"),),
        )


class FakeBarProvider:
    def __init__(self, *, reverse=False, fallback=False, trade_status=None) -> None:
        self.requests = []
        self.reverse = reverse
        self.fallback = fallback
        self.trade_status = trade_status

    def fetch_daily_bars_with_provenance(self, request):
        self.requests.append(request)
        bars = [
            NormalizedDailyBar(request.symbol, date(2026, 1, 2), 10.0, 10.0, 10.2, 9.8, 100000, trade_status=self.trade_status, provider=ProviderName.TUSHARE),
            NormalizedDailyBar(request.symbol, date(2026, 1, 5), 10.1, 10.3, 10.4, 10.0, 100000, trade_status=self.trade_status, provider=ProviderName.TUSHARE),
        ]
        if self.reverse:
            bars.reverse()
        attempts = [SimpleNamespace(provider=ProviderName.TUSHARE, status="empty" if self.fallback else "success", reason="bars:0" if self.fallback else "bars:2")]
        selected = ProviderName.TUSHARE
        if self.fallback:
            attempts.append(SimpleNamespace(provider=ProviderName.BAOSTOCK, status="success", reason="bars:2"))
            selected = ProviderName.BAOSTOCK
        return SimpleNamespace(
            selected_provider=selected,
            bars=tuple(bars),
            fallback_used=self.fallback,
            attempts=tuple(attempts),
            requested_adjustment=Adjustment.NONE,
            symbol=request.symbol,
            date_range=(request.start_date, request.end_date),
        )


def test_runner_default_offline_writes_cache_paths_without_live_calls(tmp_path: Path, capsys) -> None:
    state = tmp_path / "state.json"
    report = tmp_path / "report.json"

    assert main(["--state-path", str(state), "--report-path", str(report), "--decision-session", "2026-01-02"]) == 0

    stdout = json.loads(capsys.readouterr().out)
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert stdout["status"] == "completed"
    assert payload["market_data_provenance"]["network_calls"] == 0
    assert payload["advisory_provenance"]["deepseek_live_call"] is False
    assert state.exists()


def test_runner_live_flag_requires_input_json_before_any_provider_path(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main([
            "--live-market-data",
            "--state-path",
            str(tmp_path / "state.json"),
            "--report-path",
            str(tmp_path / "report.json"),
        ])


def test_runner_input_json_is_deterministic(tmp_path: Path, capsys) -> None:
    input_path = tmp_path / "input.json"
    state_path = tmp_path / "state.json"
    report_path = tmp_path / "report.json"
    input_path.write_text(
        json.dumps(
            {
                "calendar": {"sessions": ["2026-01-02", "2026-01-05"], "provider": "baostock"},
                "strategy_id": "json-exec1",
                "aggregate_score": 0.2,
                "candidates": [
                    {
                        "symbol": "600000.SH",
                        "direction": "long",
                        "confidence": 0.8,
                        "expected_return": 0.08,
                        "risk_score": 0.2,
                        "liquidity_score": 0.9,
                        "timestamp": "2026-01-02T14:55:00+08:00",
                        "metadata": {"candidate_id": "json-candidate"},
                    }
                ],
                "market": {
                    "decision_rows_by_symbol": {
                        "600000.SH": {
                            "symbol": "600000.SH",
                            "date": "2026-01-02",
                            "open": 9.9,
                            "high": 10.2,
                            "low": 9.8,
                            "close": 10.0,
                            "volume": 120000,
                            "is_suspended": False,
                        }
                    },
                    "execution_rows_by_symbol": {
                        "600000.SH": {
                            "symbol": "600000.SH",
                            "date": "2026-01-05",
                            "open": 10.0,
                            "high": 10.1,
                            "low": 9.9,
                            "close": 10.1,
                            "volume": 100000,
                            "is_suspended": False,
                        }
                    },
                },
                "information_provenance": {"max_timestamp": "2026-01-02T15:00:00+08:00"},
                "quant_firm_context": {"requested_action": "buy"},
            }
        ),
        encoding="utf-8",
    )

    assert main(["--input-json", str(input_path), "--state-path", str(state_path), "--report-path", str(report_path)]) == 0
    first = json.loads(report_path.read_text(encoding="utf-8"))["state"]["hash_after"]
    capsys.readouterr()
    assert main(["--input-json", str(input_path), "--state-path", str(state_path), "--report-path", str(report_path)]) == 0
    second_report = json.loads(report_path.read_text(encoding="utf-8"))
    assert second_report["idempotency_status"] == "idempotent_replay"
    assert second_report["state"]["hash_after"] == first


def test_live_loader_uses_fake_providers_and_retains_d_and_d_plus_one(tmp_path: Path) -> None:
    input_path = tmp_path / "input.json"
    write_candidate_input(input_path)
    calendar_provider = FakeCalendarProvider()
    bar_provider = FakeBarProvider(reverse=True)

    loop_input = _build_live_market_input(
        input_path,
        "2026-01-02",
        state_path=tmp_path / "state.json",
        calendar_provider=calendar_provider,
        bar_provider=bar_provider,
    )

    assert tuple(loop_input.market.decision_rows_by_symbol) == ("600000.SH",)
    assert loop_input.market.decision_rows_by_symbol["600000.SH"]["date"] == "2026-01-02"
    assert loop_input.market.execution_rows_by_symbol["600000.SH"]["date"] == "2026-01-05"
    assert loop_input.market.market_data_provenance["bar_attempts"]["600000.SH"]["selected_provider"] == "tushare"
    assert len(calendar_provider.requests) == 1
    assert len(bar_provider.requests) == 1


def test_live_loader_records_fallback_and_suspension_zero(tmp_path: Path) -> None:
    input_path = tmp_path / "input.json"
    write_candidate_input(input_path)
    loop_input = _build_live_market_input(
        input_path,
        "2026-01-02",
        state_path=tmp_path / "state.json",
        calendar_provider=FakeCalendarProvider(),
        bar_provider=FakeBarProvider(fallback=True, trade_status="0"),
    )

    assert loop_input.market.market_data_provenance["bar_attempts"]["600000.SH"]["fallback_used"] is True
    assert loop_input.market.execution_rows_by_symbol["600000.SH"]["is_suspended"] is True


def test_live_loader_candidate_and_existing_holding_union_and_cap(tmp_path: Path) -> None:
    input_path = tmp_path / "input.json"
    write_candidate_input(input_path, symbols=("600000.SH",))
    state = initialize_daily_state(100_000.0)
    seeded = replace(
        state.execution_state,
        account=PaperAccount(cash=90_000.0, positions={"000001.SZ": 100}, average_costs={"000001.SZ": 10.0}),
        settlement_lots=(SettlementLot("000001.SZ", 100, "2026-01-01"),),
    )
    state_path = tmp_path / "state.json"
    save_daily_state_atomic(replace(state, execution_state=seeded), state_path)
    bar_provider = FakeBarProvider()

    loop_input = _build_live_market_input(
        input_path,
        "2026-01-02",
        state_path=state_path,
        initial_capital=100_000.0,
        calendar_provider=FakeCalendarProvider(),
        bar_provider=bar_provider,
    )
    assert set(loop_input.market.decision_rows_by_symbol) == {"600000.SH", "000001.SZ"}
    assert len(bar_provider.requests) == 2

    too_many = tmp_path / "too-many.json"
    write_candidate_input(too_many, symbols=tuple(f"60000{i}.SH" for i in range(6)))
    with pytest.raises(ValueError, match="at most 6"):
        _build_live_market_input(
            too_many,
            "2026-01-02",
            state_path=state_path,
            initial_capital=100_000.0,
            calendar_provider=FakeCalendarProvider(),
            bar_provider=FakeBarProvider(),
        )


def test_live_loader_validates_local_input_before_bar_requests(tmp_path: Path) -> None:
    input_path = tmp_path / "future.json"
    write_candidate_input(input_path)
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    payload["candidates"][0]["timestamp"] = "2026-01-02T15:01:00+08:00"
    input_path.write_text(json.dumps(payload), encoding="utf-8")
    bar_provider = FakeBarProvider()

    with pytest.raises(Exception, match="after decision cutoff"):
        _build_live_market_input(
            input_path,
            "2026-01-02",
            state_path=tmp_path / "state.json",
            calendar_provider=FakeCalendarProvider(),
            bar_provider=bar_provider,
        )
    assert bar_provider.requests == []


def test_live_loader_rejects_non_session_before_bar_requests(tmp_path: Path) -> None:
    input_path = tmp_path / "input.json"
    write_candidate_input(input_path)
    calendar_provider = FakeCalendarProvider(sessions=(date(2026, 1, 5), date(2026, 1, 6)))
    bar_provider = FakeBarProvider()

    with pytest.raises(ValueError, match="not a loaded trading session"):
        _build_live_market_input(
            input_path,
            "2026-01-02",
            state_path=tmp_path / "state.json",
            calendar_provider=calendar_provider,
            bar_provider=bar_provider,
        )
    assert len(calendar_provider.requests) == 1
    assert bar_provider.requests == []
