from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

import quantpilot_core.daily_evaluation.evaluator as evaluator
from quantpilot_core.daily_evaluation import RealDailyEvaluationConfig, evaluation_request_digest, run_real_daily_evaluation
from quantpilot_core.daily_evaluation.evaluator import (
    FUNNEL_COUNT_FIELDS,
    EvaluationReportIntegrityError,
    _aggregate_funnel,
    _daily_execution_shortfall,
    _daily_no_trade,
    _outcomes_by_order,
    _performance,
)
from quantpilot_core.daily_paper_loop.report import report_digest
from quantpilot_core.real_data_provider import NormalizedDailyBar, ProviderName, TradingCalendar
from scripts.run_real_daily_evaluation_v1 import main as runner_main


def config(tmp_path: Path, **kwargs) -> RealDailyEvaluationConfig:
    symbols = kwargs.pop("symbols", ("600000.SH", "000001.SZ", "600519.SH"))
    start = kwargs.pop("start_decision_session", "2026-04-01")
    end = kwargs.pop("end_decision_session", "2026-04-03")
    return RealDailyEvaluationConfig(
        strategy_id="real-candidate-defensive-composite-v1",
        start_decision_session=start,
        end_decision_session=end,
        symbols=symbols,
        output_dir=tmp_path,
        **kwargs,
    )


class FakeCalendarProvider:
    def __init__(self) -> None:
        self.requests = []

    def fetch_calendar_with_provenance(self, start_date, end_date):
        self.requests.append((start_date, end_date))
        sessions = []
        cursor = start_date
        while cursor <= end_date:
            if cursor.weekday() < 5:
                sessions.append(cursor)
            cursor += timedelta(days=1)
        return SimpleNamespace(
            selected_provider=ProviderName.TUSHARE,
            fallback_used=False,
            calendar=TradingCalendar(tuple(sessions), ProviderName.TUSHARE),
            attempts=(SimpleNamespace(provider=ProviderName.TUSHARE, status="success", reason=f"sessions:{len(sessions)}"),),
        )


class FakeBarProvider:
    def __init__(self, *, fallback: bool = False) -> None:
        self.requests = []
        self.fallback = fallback

    def fetch_daily_bars_with_provenance(self, request):
        self.requests.append(request)
        bars = []
        cursor = request.start_date
        index = 0
        while cursor <= request.end_date:
            if cursor.weekday() < 5:
                close = 10.0 + index * 0.05 + (0.1 if request.symbol == "000001.SZ" else 0.0)
                bars.append(
                    NormalizedDailyBar(
                        request.symbol,
                        cursor,
                        close,
                        close,
                        close + 0.2,
                        close - 0.2,
                        200_000 + index,
                        amount=(200_000 + index) * close,
                        previous_close=close - 0.01,
                        provider=ProviderName.BAOSTOCK if self.fallback else ProviderName.TUSHARE,
                    )
                )
                index += 1
            cursor += timedelta(days=1)
        return SimpleNamespace(
            selected_provider=ProviderName.BAOSTOCK if self.fallback else ProviderName.TUSHARE,
            bars=tuple(bars),
            fallback_used=self.fallback,
            attempts=(
                SimpleNamespace(provider=ProviderName.TUSHARE, status="empty" if self.fallback else "success", reason="fixture"),
                *((SimpleNamespace(provider=ProviderName.BAOSTOCK, status="success", reason="fixture"),) if self.fallback else ()),
            ),
            date_range=(request.start_date, request.end_date),
        )


def test_evaluation_request_digest_canonicalizes_ordering(tmp_path: Path) -> None:
    first = config(tmp_path / "a", symbols=("600000.SH", "000001.SZ"), capital_values=(100000, 1000, 10000))
    second = config(tmp_path / "b", symbols=("sz.000001", "sh.600000"), capital_values=(1000, 10000, 100000))

    assert evaluation_request_digest(first) == evaluation_request_digest(second)
    assert evaluation_request_digest(first) != evaluation_request_digest(config(tmp_path / "c", symbols=("600000.SH",)))


def test_conflicting_information_signal_identity_rejects(tmp_path: Path) -> None:
    first = {"signal": {"target": "600000.SH", "score": 0.1}, "available_at": "2026-04-01T14:00:00+08:00", "source_event_id": "same"}
    duplicate = dict(first)
    changed = {"signal": {"target": "600000.SH", "score": 0.2}, "available_at": "2026-04-01T14:00:00+08:00", "source_event_id": "same"}

    assert evaluation_request_digest(config(tmp_path / "a", information_signals=(first, duplicate))) == evaluation_request_digest(config(tmp_path / "b", information_signals=(duplicate, first)))
    with pytest.raises(ValueError, match="conflicting information signal payload"):
        evaluation_request_digest(config(tmp_path / "c", information_signals=(first, changed)))


def test_digest_canonicalizes_duplicate_bars_and_rejects_conflicts(tmp_path: Path) -> None:
    calendar_sessions = weekday_sessions(date(2026, 1, 1), date(2026, 4, 6))
    bars = simple_bars(("600000.SH",), calendar_sessions)
    first = config(tmp_path / "a", symbols=("600000.SH",), input_bars=bars, offline_calendar_sessions=calendar_sessions)
    second = config(tmp_path / "b", symbols=("600000.SH",), input_bars=tuple(reversed((*bars, bars[0]))), offline_calendar_sessions=tuple(reversed(calendar_sessions)))
    changed = tuple({**row, "close": row["close"] + 0.01} if index == 0 else row for index, row in enumerate(bars))
    conflict = (*bars, {**bars[0], "close": bars[0]["close"] + 1.0})

    assert evaluation_request_digest(first) == evaluation_request_digest(second)
    assert evaluation_request_digest(first) != evaluation_request_digest(config(tmp_path / "c", symbols=("600000.SH",), input_bars=changed, offline_calendar_sessions=calendar_sessions))
    with pytest.raises(ValueError, match="conflicting offline bar rows"):
        evaluation_request_digest(config(tmp_path / "d", symbols=("600000.SH",), input_bars=conflict, offline_calendar_sessions=calendar_sessions))


def test_supplied_bars_require_explicit_holiday_aware_calendar(tmp_path: Path) -> None:
    calendar_sessions = tuple(session for session in weekday_sessions(date(2026, 1, 1), date(2026, 4, 6)) if session != "2026-02-17")
    bars = simple_bars(("600000.SH", "000001.SZ", "600519.SH"), calendar_sessions)

    with pytest.raises(ValueError, match="input_bars require explicit offline_calendar_sessions"):
        run_real_daily_evaluation(config(tmp_path / "missing-calendar", input_bars=bars))

    result = run_real_daily_evaluation(
        config(
            tmp_path / "holiday",
            start_decision_session="2026-04-01",
            end_decision_session="2026-04-01",
            input_bars=bars,
            offline_calendar_sessions=calendar_sessions,
            capital_values=(100000.0,),
        )
    )
    assert "2026-02-17" not in result.report["acquisition_provenance"]["calendar_sessions"]
    assert result.report["acquisition_provenance"]["mode"] == "offline_input_bars"
    assert result.report["acquisition_provenance"]["earliest_decision_factor_session_count"] == 61
    assert result.report["run_config"]["provider_mode"] == "offline_input_bars"
    daily = json.loads((tmp_path / "holiday" / "capital_100000" / "daily_reports" / "2026-04-01.json").read_text(encoding="utf-8"))
    assert daily["daily_paper_loop"]["information_provenance"]["bounded_acquisition_mode"] == "offline_input_bars"

    synthetic = run_real_daily_evaluation(config(tmp_path / "synthetic", capital_values=(100000.0,), offline_calendar_sessions=calendar_sessions))
    assert synthetic.report["acquisition_provenance"]["mode"] == "synthetic_engineering_fixture"
    assert synthetic.report["run_config"]["provider_mode"] == "synthetic_engineering_fixture"

    with pytest.raises(ValueError, match="provider_mode must be auto or the derived"):
        run_real_daily_evaluation(config(tmp_path / "bad-label", provider_mode="offline_fixture"))


def test_supplied_bars_reject_off_calendar_rows_before_manifest_or_state(tmp_path: Path) -> None:
    calendar_sessions = tuple(session for session in weekday_sessions(date(2026, 1, 1), date(2026, 4, 6)) if session != "2026-02-17")
    bars = (*simple_bars(("600000.SH", "000001.SZ", "600519.SH"), calendar_sessions), {
        "symbol": "600000.SH",
        "date": "2026-02-17",
        "open": 10.0,
        "high": 10.1,
        "low": 9.9,
        "close": 10.0,
        "previous_close": 9.9,
        "volume": 100000,
        "amount": 1000000.0,
        "is_suspended": False,
        "provider": "offline_test",
    })

    with pytest.raises(ValueError, match="off-calendar bar"):
        run_real_daily_evaluation(config(tmp_path, input_bars=bars, offline_calendar_sessions=calendar_sessions, capital_values=(100000.0,)))

    assert not (tmp_path / "evaluation_manifest.json").exists()
    assert not (tmp_path / "capital_100000" / "state.json").exists()


def test_pit_information_signals_are_sliced_by_decision_session(tmp_path: Path) -> None:
    early = {"signal": {"target": "600000.SH", "score": 0.1}, "available_at": "2026-04-01T14:00:00+08:00", "source_event_id": "early"}
    later = {"signal": {"target": "600519.SH", "score": 0.9}, "available_at": "2026-04-03T14:00:00+08:00", "source_event_id": "later"}

    result = run_real_daily_evaluation(config(tmp_path, capital_values=(100000.0,), information_signals=(later, early)))
    first_report = json.loads((tmp_path / "capital_100000" / "daily_reports" / "2026-04-01.json").read_text(encoding="utf-8"))
    last_report = json.loads((tmp_path / "capital_100000" / "daily_reports" / "2026-04-03.json").read_text(encoding="utf-8"))

    assert result.report["capital_runs"][0]["daily_summaries"][0]["decision_session"] == "2026-04-01"
    assert first_report["daily_paper_loop"]["information_provenance"]["available_information_signal_ids"] == ["early"]
    assert last_report["daily_paper_loop"]["information_provenance"]["available_information_signal_ids"] == ["early", "later"]

    naive = {"signal": {"target": "600000.SH"}, "available_at": "2026-04-01T14:00:00", "source_event_id": "naive"}
    with pytest.raises(ValueError, match="timezone-aware"):
        evaluation_request_digest(config(tmp_path / "bad", information_signals=(naive,)))


def test_multi_session_evaluation_capital_tiers_resume_and_report_shape(tmp_path: Path) -> None:
    result = run_real_daily_evaluation(config(tmp_path))
    replay = run_real_daily_evaluation(config(tmp_path))
    report = result.report

    assert result.evaluation_request_digest == replay.evaluation_request_digest
    assert result.report["capital_runs"][0]["state"]["starting_state_hash"] == replay.report["capital_runs"][0]["state"]["starting_state_hash"]
    assert result.report["capital_runs"][2]["daily_summaries"][0]["canonical_report_digest"] == replay.report["capital_runs"][2]["daily_summaries"][0]["canonical_report_digest"]
    assert result.report["capital_comparison"]["candidate_identity_rank_consistent"] is True
    assert replay.report["capital_runs"][0]["daily_summaries"][0]["idempotency_status"] == "completed"
    assert replay.report["capital_runs"][0]["daily_summaries"][0]["replay_execution_status"] == "idempotent_replay"
    rows = {row["initial_capital"]: row for row in report["capital_comparison"]["rows"]}
    assert rows[1000.0]["below_one_lot_skips"] >= 1
    assert rows[100000.0]["fill_count"] >= 1
    assert rows[100000.0]["final_equity"] > 0
    assert report["data_quality"]["all_reconciliations_passed"] is True
    assert report["data_quality"]["unexpected_unclassified_reasons"] == ()
    example = report["capital_runs"][2]["sizing_compression"]["largest_compression_examples"][0]
    assert example["optimizer_target_shares"] > example["final_order_quantity"]
    assert example["optimizer_to_order"]["reason_codes"] == ("max_position_cap_reduction",)
    assert example["order_to_fill"]["shortfall_reason_code"] is None
    assert replay.report["capital_runs"][0]["no_trade_attribution"]["total_count"] == report["capital_runs"][0]["no_trade_attribution"]["total_count"]
    encoded = json.dumps(report, sort_keys=True)
    assert str(tmp_path) not in encoded
    assert "previous_close" not in encoded

    report_ref = tmp_path / report["capital_runs"][2]["daily_summaries"][0]["canonical_report_ref"]
    disk_payload = json.loads(report_ref.read_text(encoding="utf-8"))
    assert report_digest(disk_payload) == report["capital_runs"][2]["daily_summaries"][0]["canonical_report_digest"]
    perf = report["capital_runs"][2]["performance"]
    assert perf["net_pnl"] == pytest.approx(perf["final_equity"] - perf["initial_capital"])
    assert perf["fill_rate"] <= 1.0
    assert perf["average_holding_period"]["value"] is None
    assert perf["win_rate_closed_realized_trades"]["value"] is None
    assert perf["maximum_drawdown"] <= 0
    snapshots = report["capital_runs"][2]["daily_summaries"]
    expected_exposure = sum(item["performance_snapshot"]["market_value"] / item["performance_snapshot"]["equity"] for item in snapshots) / len(snapshots)
    assert perf["average_exposure"] == pytest.approx(expected_exposure, rel=1e-4)


def test_daily_report_recovery_missing_malformed_and_stale(tmp_path: Path) -> None:
    cfg = config(tmp_path, start_decision_session="2026-04-01", end_decision_session="2026-04-01", capital_values=(100000.0,))
    first = run_real_daily_evaluation(cfg)
    report_path = tmp_path / first.report["capital_runs"][0]["daily_summaries"][0]["canonical_report_ref"]
    state_path = tmp_path / "capital_100000" / "state.json"
    state_after_first = json.loads(state_path.read_text(encoding="utf-8"))

    report_path.unlink()
    missing_recovery = run_real_daily_evaluation(cfg)
    assert report_path.exists()
    assert missing_recovery.report["capital_runs"][0]["daily_summaries"][0]["replay_execution_status"] == "idempotent_replay"
    assert json.loads(state_path.read_text(encoding="utf-8"))["execution_state"]["account"]["trade_log"] == state_after_first["execution_state"]["account"]["trade_log"]

    report_path.write_text("{", encoding="utf-8")
    malformed_recovery = run_real_daily_evaluation(cfg)
    assert malformed_recovery.report["capital_runs"][0]["daily_summaries"][0]["replay_execution_status"] == "idempotent_replay"

    clean = json.loads(report_path.read_text(encoding="utf-8"))
    mutations = (
        ("decision_session", lambda payload: payload["daily_paper_loop"].__setitem__("decision_session", "2026-04-02")),
        ("fills", lambda payload: payload["daily_paper_loop"]["fills"].append({**payload["daily_paper_loop"]["fills"][0], "filled_quantity": 1}) if payload["daily_paper_loop"]["fills"] else payload["daily_paper_loop"].__setitem__("fills", [{"order_id": "fake", "status": "filled", "filled_quantity": 1}])),
        ("fees", lambda payload: payload["daily_paper_loop"]["fee_breakdown"].__setitem__("total_cost", 999.0)),
        ("ledger", lambda payload: payload["daily_paper_loop"]["ledger_after"].__setitem__("cash", 1.0)),
        ("sizing", lambda payload: payload["daily_paper_loop"]["sizing_decisions"][0].__setitem__("final_order_quantity", 123456)),
        ("orders", lambda payload: payload["daily_paper_loop"]["order_intents"].__setitem__("intents", [])),
        ("run_config", lambda payload: payload["daily_paper_loop"]["run_config"].__setitem__("strategy_id", "mutated")),
        ("next_session_state", lambda payload: payload["daily_paper_loop"]["next_session_state"].__setitem__("last_completed_session", "2099-01-01")),
        ("unknown_substantive", lambda payload: payload["daily_paper_loop"].__setitem__("new_future_substantive_field", {"value": 1})),
    )
    for name, mutate in mutations:
        payload = json.loads(json.dumps(clean))
        mutate(payload)
        report_path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(EvaluationReportIntegrityError, match="failed replay parity"):
            run_real_daily_evaluation(cfg), name
        report_path.write_text(json.dumps(clean), encoding="utf-8")


def test_aggregate_report_atomic_write_failure_recovers_without_duplicate_fills(tmp_path: Path, monkeypatch) -> None:
    cfg = config(tmp_path, start_decision_session="2026-04-01", end_decision_session="2026-04-01", capital_values=(100000.0,))
    original_write = evaluator.write_report_atomic
    failures = {"remaining": 1}

    def fail_final_once(payload, path):
        if path.name == cfg.report_filename and failures["remaining"]:
            failures["remaining"] -= 1
            raise OSError("injected aggregate report write failure")
        return original_write(payload, path)

    monkeypatch.setattr(evaluator, "write_report_atomic", fail_final_once)
    with pytest.raises(OSError, match="injected aggregate report write failure"):
        run_real_daily_evaluation(cfg)

    manifest_path = tmp_path / "evaluation_manifest.json"
    state_path = tmp_path / "capital_100000" / "state.json"
    daily_path = tmp_path / "capital_100000" / "daily_reports" / "2026-04-01.json"
    manifest_before = json.loads(manifest_path.read_text(encoding="utf-8"))
    state_before = json.loads(state_path.read_text(encoding="utf-8"))
    daily_before = json.loads(daily_path.read_text(encoding="utf-8"))
    daily_digest_before = report_digest(daily_before)
    trade_log_before = state_before["execution_state"]["account"]["trade_log"]

    recovered = run_real_daily_evaluation(cfg)
    manifest_after = json.loads(manifest_path.read_text(encoding="utf-8"))
    state_after = json.loads(state_path.read_text(encoding="utf-8"))
    daily_after = json.loads(daily_path.read_text(encoding="utf-8"))

    assert (tmp_path / cfg.report_filename).exists()
    assert recovered.report["capital_runs"][0]["daily_summaries"][0]["replay_execution_status"] == "idempotent_replay"
    assert report_digest(daily_after) == daily_digest_before
    assert state_after["execution_state"]["account"]["trade_log"] == trade_log_before
    assert manifest_after["capital_starting_state_hashes"] == manifest_before["capital_starting_state_hashes"]


def test_partial_session_interruption_and_resume_preserves_completed_daily_reports(tmp_path: Path, monkeypatch) -> None:
    cfg = config(tmp_path / "resume", capital_values=(100000.0,))
    control_cfg = config(tmp_path / "control", capital_values=(100000.0,))
    original_run = evaluator.run_real_candidate_daily_paper
    failures = {"remaining": 1}

    def fail_second_session_once(pipeline_config):
        if str(pipeline_config.decision_session) == "2026-04-02" and failures["remaining"]:
            failures["remaining"] -= 1
            raise RuntimeError("injected partial evaluation interruption")
        return original_run(pipeline_config)

    monkeypatch.setattr(evaluator, "run_real_candidate_daily_paper", fail_second_session_once)
    with pytest.raises(RuntimeError, match="injected partial evaluation interruption"):
        run_real_daily_evaluation(cfg)

    manifest_path = tmp_path / "resume" / "evaluation_manifest.json"
    state_path = tmp_path / "resume" / "capital_100000" / "state.json"
    first_daily_path = tmp_path / "resume" / "capital_100000" / "daily_reports" / "2026-04-01.json"
    manifest_before = json.loads(manifest_path.read_text(encoding="utf-8"))
    state_after_interrupt = json.loads(state_path.read_text(encoding="utf-8"))
    first_daily_digest_before = report_digest(json.loads(first_daily_path.read_text(encoding="utf-8")))
    first_trade_log = tuple(state_after_interrupt["execution_state"]["account"]["trade_log"])

    resumed = run_real_daily_evaluation(cfg)
    monkeypatch.setattr(evaluator, "run_real_candidate_daily_paper", original_run)
    control = run_real_daily_evaluation(control_cfg)
    state_after_resume = json.loads(state_path.read_text(encoding="utf-8"))
    control_state = json.loads((tmp_path / "control" / "capital_100000" / "state.json").read_text(encoding="utf-8"))
    manifest_after = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert resumed.report["capital_runs"][0]["daily_summaries"][0]["replay_execution_status"] == "idempotent_replay"
    assert len(resumed.report["capital_runs"][0]["daily_summaries"]) == 3
    assert report_digest(json.loads(first_daily_path.read_text(encoding="utf-8"))) == first_daily_digest_before
    assert state_after_resume["execution_state"]["account"]["trade_log"][: len(first_trade_log)] == list(first_trade_log)
    assert len(state_after_resume["execution_state"]["account"]["trade_log"]) == len(control_state["execution_state"]["account"]["trade_log"])
    assert state_after_resume["state_hash"] == control_state["state_hash"]
    assert resumed.report["capital_runs"][0]["state"]["ending_state_hash"] == control.report["capital_runs"][0]["state"]["ending_state_hash"]
    assert manifest_after["capital_starting_state_hashes"] == manifest_before["capital_starting_state_hashes"]


def test_sizing_decisions_include_buy_skip_and_created_source_stages(tmp_path: Path) -> None:
    result = run_real_daily_evaluation(config(tmp_path, start_decision_session="2026-04-01", end_decision_session="2026-04-01"))
    all_examples = tuple(example for run in result.report["capital_runs"] for example in run["sizing_compression"]["examples"])
    small = next(example for example in all_examples if example["result_status"] == "skipped" and "current_position_at_or_above_target" in example["compression_reason_codes"])
    large = result.report["capital_runs"][2]["sizing_compression"]["largest_compression_examples"][0]

    assert small["result_status"] == "skipped"
    assert small["candidate_id"]
    assert small["final_order_quantity"] == 0
    assert small["optimizer_to_order"]["compression_ratio"] == 1.0
    assert large["result_status"] == "order_created"
    assert large["candidate_id"]
    assert large["optimizer_to_order"]["retention_ratio"] < 1.0
    assert large["optimizer_to_order"]["compression_ratio"] > 0.0


def test_no_trade_sizing_skips_preserve_candidate_identity_without_collapsing() -> None:
    daily = {
        "decision_session": "2026-04-01",
        "execution_session": "2026-04-02",
        "sizing_decisions": (
            {"symbol": "600000.SH", "side": "buy", "candidate_id": "held-1", "result_status": "skipped", "reason_codes": ("current_position_at_or_above_target",), "final_order_quantity": 0},
            {"symbol": "600001.SH", "side": "buy", "candidate_id": "cash-1", "result_status": "skipped", "reason_codes": ("insufficient_cash_for_one_board_lot_after_reserve",), "final_order_quantity": 0},
            {"symbol": "600001.SH", "side": "buy", "candidate_id": "cash-2", "result_status": "skipped", "reason_codes": ("insufficient_cash_for_one_board_lot_after_reserve",), "final_order_quantity": 0},
        ),
        "skipped_orders": (
            {"symbol": "600001.SH", "side": "buy", "candidate_id": "cash-1", "reason": "insufficient_cash_for_one_board_lot_after_reserve"},
        ),
    }
    report = _daily_no_trade({"candidate_events": {}, "rejected": {}, "no_candidate": {}}, daily)
    candidate_ids = {event["candidate_id"] for event in report["events"]}

    assert {"held-1", "cash-1", "cash-2"} <= candidate_ids
    assert report["by_reason_code"]["insufficient_cash_for_one_board_lot_after_reserve"]["count"] == 2


def test_live_evaluation_uses_one_bounded_provider_load_per_symbol(tmp_path: Path) -> None:
    calendar = FakeCalendarProvider()
    bars = FakeBarProvider(fallback=True)
    result = run_real_daily_evaluation(
        config(
            tmp_path,
            live_market_data=True,
            provider_mode="live_market_data",
            symbols=("600000.SH", "000001.SZ"),
            capital_values=(100000.0,),
        ),
        calendar_provider=calendar,
        bar_provider=bars,
    )

    assert len(calendar.requests) == 1
    assert len(bars.requests) == 2
    assert all(request.start_date <= date(2026, 1, 7) for request in bars.requests)
    assert all(request.end_date == date(2026, 4, 6) for request in bars.requests)
    acquisition = result.report["acquisition_provenance"]
    assert acquisition["bounded_once_per_evaluation"] is True
    assert acquisition["earliest_decision_factor_session_count"] == 61
    assert acquisition["market"]["bar_attempts"]["600000.SH"]["selected_provider"] == "baostock"
    assert result.report["capital_runs"][0]["daily_summaries"][0]["leakage_audit"]["decision_market_rows_exact_d"] is True
    assert result.report["capital_runs"][0]["daily_summaries"][0]["leakage_audit"]["fill_uses_d_plus_1_open_execution_price"] is True


def test_cli_runner_writes_compact_json_result(tmp_path: Path, capsys) -> None:
    exit_code = runner_main(
        [
            "--output-dir",
            str(tmp_path),
            "--start-decision-session",
            "2026-04-01",
            "--end-decision-session",
            "2026-04-01",
            "--symbol",
            "600000.SH",
            "--symbol",
            "000001.SZ",
            "--symbol",
            "600519.SH",
            "--capital",
            "100000",
        ]
    )
    printed = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert printed["status"] == "completed"
    assert Path(printed["report_path"]).exists()
    report = json.loads(Path(printed["report_path"]).read_text(encoding="utf-8"))
    assert report["run_config"]["provider_mode"] == "synthetic_engineering_fixture"


def test_cli_runner_labels_supplied_bars_as_offline_input_bars(tmp_path: Path, capsys) -> None:
    sessions = weekday_sessions(date(2026, 1, 1), date(2026, 4, 6))
    payload_path = tmp_path / "input.json"
    payload_path.write_text(
        json.dumps(
            {
                "symbols": ["600000.SH", "000001.SZ", "600519.SH"],
                "calendar": {"sessions": sessions},
                "bars": simple_bars(("600000.SH", "000001.SZ", "600519.SH"), sessions),
            }
        ),
        encoding="utf-8",
    )
    exit_code = runner_main(
        [
            "--output-dir",
            str(tmp_path / "run"),
            "--start-decision-session",
            "2026-04-01",
            "--end-decision-session",
            "2026-04-01",
            "--input-json",
            str(payload_path),
            "--capital",
            "100000",
        ]
    )
    printed = json.loads(capsys.readouterr().out)
    report = json.loads(Path(printed["report_path"]).read_text(encoding="utf-8"))

    assert exit_code == 0
    assert report["evaluation_request_digest"]
    assert report["run_config"]["provider_mode"] == "offline_input_bars"
    assert report["acquisition_provenance"]["mode"] == "offline_input_bars"


def test_funnel_schema_rates_and_outcome_precedence() -> None:
    first = {"factor_accepted_count": 2, "factor_selected_long_count": 1, "quant_firm_approved_entry_count": 1, "buy_order_intent_count": 1, "unique_order_intent_count": 1, "unique_order_with_any_fill_count": 1}
    second = {"factor_accepted_count": 3, "factor_selected_long_count": 2, "quant_firm_approved_exit_count": 2, "sell_order_intent_count": 2, "unique_order_intent_count": 2, "unique_order_with_any_fill_count": 2}
    aggregate = _aggregate_funnel((first, second))

    assert set(FUNNEL_COUNT_FIELDS) <= set(aggregate["totals"])
    assert aggregate["rates"]["factor_selection_rate"] == 0.6
    assert aggregate["rates"]["entry_order_rate"] == 1.0
    assert aggregate["rates"]["exit_order_rate"] == 1.0
    assert aggregate["rates"]["filled_order_rate"] == 1.0
    assert "order_intent_rate" not in aggregate["rates"]
    assert aggregate["data_gaps"]["quant_firm_candidate_action_gap_session_count"] == 0

    with pytest.raises(ValueError, match="factor_selection_rate invariant violation"):
        _aggregate_funnel(({"factor_accepted_count": 1, "factor_selected_long_count": 2},))

    no_candidate_then_entry = _aggregate_funnel((
        {"actionable_candidate_count": 0, "quant_firm_approved_entry_count": 0, "buy_order_intent_count": 0},
        {"actionable_candidate_count": 1, "quant_firm_approved_entry_count": 1, "buy_order_intent_count": 1},
    ))
    assert no_candidate_then_entry["data_gaps"]["quant_firm_candidate_action_gap_session_count"] == 0
    assert no_candidate_then_entry["availability"]["quant_firm_approved_entry_count"]["available_session_count"] == 2
    assert no_candidate_then_entry["rates"]["entry_order_rate"] == 1.0

    gap = _aggregate_funnel(({"actionable_candidate_count": 1, "buy_order_intent_count": 1, "positive_allocation_count": 1, "quant_firm_candidate_action_gap": "per_candidate_quant_firm_evidence_unavailable"},))
    assert gap["rates"]["entry_order_rate"] is None
    assert gap["rate_data_gap_reasons"]["entry_order_rate"] == "per_candidate_quant_firm_evidence_unavailable"
    assert gap["data_gaps"]["quant_firm_candidate_action_gap_session_count"] == 1

    mixed_entry_exit = _aggregate_funnel((
        {
            "positive_allocation_count": 1,
            "quant_firm_approved_entry_count": 1,
            "quant_firm_approved_exit_count": 1,
            "buy_order_intent_count": 1,
            "sell_order_intent_count": 1,
            "unique_order_intent_count": 2,
            "unique_order_with_any_fill_count": 2,
        },
    ))
    assert mixed_entry_exit["rates"]["entry_order_rate"] == 1.0
    assert mixed_entry_exit["rates"]["exit_order_rate"] == 1.0
    assert all(value is None or value <= 1.0 for value in mixed_entry_exit["rates"].values())

    daily = {
        "sizing_decisions": ({"order_id": "o1", "final_order_quantity": 100}, {"order_id": "o2", "final_order_quantity": 100}),
        "fills": ({"order_id": "o1", "status": "filled", "filled_quantity": 100, "gross_value": 1000.0},),
        "partial_fills": (
            {"order_id": "o1", "status": "partial", "filled_quantity": 30, "gross_value": 300.0},
            {"order_id": "o2", "status": "partial", "filled_quantity": 40, "gross_value": 400.0},
            {"order_id": "o2", "status": "partial", "filled_quantity": 20, "gross_value": 200.0},
        ),
        "rejections": ({"order_id": "o3", "status": "rejected", "rejection_or_deferral_reason": "insufficient_position"},),
    }
    outcomes = _outcomes_by_order(daily)
    assert outcomes["o1"]["filled_quantity"] == 100
    assert outcomes["o1"]["gross_value"] == 1000.0
    assert outcomes["o2"]["filled_quantity"] == 60
    assert outcomes["o3"]["status"] == "rejected"

    inconsistent = {"sizing_decisions": ({"order_id": "bad", "final_order_quantity": 50},), "partial_fills": ({"order_id": "bad", "status": "partial", "filled_quantity": 60, "gross_value": 600.0},)}
    with pytest.raises(EvaluationReportIntegrityError, match="filled quantity exceeds final order quantity"):
        _outcomes_by_order(inconsistent)


def test_execution_shortfall_is_separate_from_no_trade_and_holding_metrics_are_null() -> None:
    daily = {
        "decision_session": "2026-04-01",
        "execution_session": "2026-04-02",
        "sizing_decisions": ({"order_id": "o1", "final_order_quantity": 100}, {"order_id": "o2", "final_order_quantity": 100}),
        "order_intents": {"intents": ({"side": "buy", "target_shares": 100, "metadata": {"order_id": "o1"}}, {"side": "sell", "target_shares": 100, "metadata": {"order_id": "o2"}},)},
        "partial_fills": ({"order_id": "o1", "symbol": "600000.SH", "status": "partial", "filled_quantity": 40, "gross_value": 400.0, "rejection_or_deferral_reason": "partial_fill_volume_participation_limit", "candidate_id": "c1"},),
        "rejections": ({"order_id": "o2", "symbol": "600001.SH", "status": "rejected", "rejection_or_deferral_reason": "insufficient_position", "candidate_id": "c2"},),
        "no_fills": ({"order_id": "o2", "symbol": "600001.SH", "status": "rejected", "rejection_or_deferral_reason": "insufficient_position", "candidate_id": "c2"},),
        "ledger_after": {"total_equity": 100000.0, "market_value": 0.0, "cash": 100000.0, "realized_pnl": 0.0, "unrealized_pnl": 0.0},
        "fee_breakdown": {"commission": 0.0, "transaction_tax": 0.0, "transfer_or_exchange_fee": 0.0, "slippage_cost": 0.0, "total_cost": 0.0},
        "fills": (),
        "candidate_report": {"candidates": ({"symbol": "600001.SH", "metadata": {"holding_period_status": "available", "holding_period_sessions": 5}},)},
    }
    pipeline = {"candidate_events": {}, "rejected": {}, "no_candidate": {}}

    no_trade = _daily_no_trade(pipeline, daily)
    shortfall = _daily_execution_shortfall(daily)
    perf = _performance(100000.0, (daily,))

    assert no_trade["total_count"] == 1
    assert no_trade["events"][0]["category"] == "insufficient_position"
    assert no_trade["events"][0]["candidate_id"] == "c2"
    assert no_trade["events"][0]["evidence"]["candidate_id"] == "c2"
    assert shortfall["total_count"] == 1
    no_trade_order_ids = {event["order_id"] for event in no_trade["events"]}
    shortfall_order_ids = {event["order_id"] for event in shortfall["events"]}
    assert no_trade_order_ids == {"o2"}
    assert shortfall_order_ids == {"o1"}
    assert no_trade_order_ids.isdisjoint(shortfall_order_ids)
    assert perf["average_holding_period"] == {"value": None, "data_gap_reason": "exact entry/exit round-trip identity unavailable"}
    assert perf["completed_buy_sell_trade_count"]["data_gap_reason"] == "exact entry/exit round-trip identity unavailable"
    assert perf["win_rate_closed_realized_trades"]["data_gap_reason"] == "exact entry/exit round-trip identity unavailable"
    assert perf["profit_factor_closed_realized_trades"]["data_gap_reason"] == "exact entry/exit round-trip identity unavailable"


def weekday_sessions(start: date, end: date) -> tuple[str, ...]:
    sessions = []
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5:
            sessions.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return tuple(sessions)


def simple_bars(symbols: tuple[str, ...], sessions: tuple[str, ...]) -> tuple[dict, ...]:
    rows = []
    for symbol_index, symbol in enumerate(symbols):
        previous = 10.0 + symbol_index
        for index, session in enumerate(sessions):
            close = round(previous + 0.02 + index * 0.001, 4)
            rows.append(
                {
                    "symbol": symbol,
                    "date": session,
                    "open": close,
                    "high": close + 0.2,
                    "low": close - 0.2,
                    "close": close,
                    "previous_close": previous,
                    "volume": 200000 + index,
                    "amount": close * (200000 + index),
                    "is_suspended": False,
                    "provider": "offline_test",
                }
            )
            previous = close
    return tuple(rows)
