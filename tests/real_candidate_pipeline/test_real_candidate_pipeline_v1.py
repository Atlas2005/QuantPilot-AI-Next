from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

import quantpilot_core.real_candidate_pipeline.pipeline as pipeline_module
from quantpilot_core.a_share_market_reality_execution import SettlementLot
from quantpilot_core.daily_paper_loop import initialize_daily_state, save_daily_state_atomic
from quantpilot_core.daily_paper_loop.state import payload_digest
from quantpilot_core.evaluation import FactorScore
from quantpilot_core.information_agents import InformationAgentRole, InformationAgentSignal, InformationDirection, InformationHorizon
from quantpilot_core.paper_trading import PaperAccount
from quantpilot_core.production_candidate import build_production_candidate_manifest
from quantpilot_core.real_candidate_pipeline import (
    RealCandidatePipelineConfig,
    build_real_candidate_daily_paper_input,
    run_real_candidate_daily_paper,
)
from quantpilot_core.real_candidate_pipeline.contracts import PipelineIdempotencyConflictError
from quantpilot_core.real_candidate_pipeline.pipeline import _offline_bars, _offline_calendar
from quantpilot_core.real_data_provider import NormalizedDailyBar, ProviderName, TradingCalendar
from quantpilot_core.runtime_account import AccountCapabilities


DECISION = "2026-04-03"


def config(tmp_path: Path, **kwargs) -> RealCandidatePipelineConfig:
    decision_session = kwargs.pop("decision_session", DECISION)
    return RealCandidatePipelineConfig(
        decision_session=decision_session,
        state_path=tmp_path / "state.json",
        report_path=tmp_path / "report.json",
        **kwargs,
    )


def seed_holding(tmp_path: Path, symbol: str, quantity: int = 100) -> None:
    state = initialize_daily_state(100_000.0)
    seeded = replace(
        state.execution_state,
        account=PaperAccount(cash=90_000.0, positions={symbol: quantity}, average_costs={symbol: 10.0}),
        settlement_lots=(SettlementLot(symbol, quantity, "2026-01-05"),),
    )
    save_daily_state_atomic(replace(state, execution_state=seeded), tmp_path / "state.json")


class FakeCalendarProvider:
    def __init__(self, decision: date = date.fromisoformat(DECISION)) -> None:
        sessions = []
        cursor = decision - timedelta(days=140)
        while cursor <= decision + timedelta(days=10):
            if cursor.weekday() < 5:
                sessions.append(cursor)
            cursor += timedelta(days=1)
        self.sessions = tuple(sessions)
        self.requests = []

    def fetch_calendar_with_provenance(self, start_date, end_date):
        self.requests.append((start_date, end_date))
        return SimpleNamespace(
            selected_provider=ProviderName.TUSHARE,
            fallback_used=False,
            calendar=TradingCalendar(self.sessions, ProviderName.TUSHARE),
            attempts=(SimpleNamespace(provider=ProviderName.TUSHARE, status="success", reason=f"sessions:{len(self.sessions)}"),),
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
                close = 10.0 + index * 0.04
                bars.append(
                    NormalizedDailyBar(
                        request.symbol,
                        cursor,
                        close,
                        close,
                        close + 0.2,
                        close - 0.2,
                        100_000 + index,
                        amount=(100_000 + index) * close,
                        previous_close=close - 0.01,
                        provider=ProviderName.TUSHARE,
                    )
                )
                index += 1
            cursor += timedelta(days=1)
        return SimpleNamespace(
            selected_provider=ProviderName.BAOSTOCK if self.fallback else ProviderName.TUSHARE,
            bars=tuple(bars),
            fallback_used=self.fallback,
            attempts=(
                SimpleNamespace(provider=ProviderName.TUSHARE, status="empty" if self.fallback else "success", reason="bars:0" if self.fallback else f"bars:{len(bars)}"),
                *((SimpleNamespace(provider=ProviderName.BAOSTOCK, status="success", reason=f"bars:{len(bars)}"),) if self.fallback else ()),
            ),
            date_range=(request.start_date, request.end_date),
        )


def fixture_bars(symbols=("600000.SH", "000001.SZ", "600519.SH")):
    decision = date.fromisoformat(DECISION)
    return _offline_bars(_offline_calendar(decision), tuple(symbols), decision)


def single_symbol_bars(
    symbol: str = "000001.SZ",
    *,
    close: float = 11.5,
    volume: float = 87_549_118.0,
    is_suspended: bool = False,
) -> tuple[dict, ...]:
    decision = date.fromisoformat(DECISION)
    calendar = _offline_calendar(decision)
    factor_start = calendar.shift_session(decision, -60)
    execution = calendar.next_session(decision)
    rows = []
    for index, session in enumerate(calendar.sessions_between(factor_start, execution)):
        session_close = close if session in (decision, execution) else round(close * (1.0 + index * 0.0001), 4)
        session_volume = volume if session == decision else 500_000.0 + index
        rows.append(
            {
                "symbol": symbol,
                "date": session.isoformat(),
                "open": session_close,
                "high": round(session_close * 1.01, 4),
                "low": round(session_close * 0.99, 4),
                "close": session_close,
                "previous_close": session_close,
                "volume": session_volume,
                "amount": round(session_close * session_volume, 6),
                "is_suspended": is_suspended if session == decision else False,
                "provider": "tushare_fixture",
            }
        )
    return tuple(rows)


def test_builds_pit_long_candidate_with_fixed_prior_and_d_plus_one_excluded(tmp_path: Path) -> None:
    result = build_real_candidate_daily_paper_input(config(tmp_path, symbols=("600000.SH", "000001.SZ", "600519.SH")))
    candidate = result.candidate_report.candidates[0]

    assert candidate.timestamp.isoformat() == "2026-04-03T15:00:00+08:00"
    assert candidate.expected_return == 0.03
    assert candidate.metadata["expected_return_semantics"] == "fixed_unscaled_sizing_prior_not_calibrated_return"
    assert candidate.metadata["factor_rank"] == 1
    assert result.candidate_pipeline_report["factor_window"] == {
        "start": "2026-01-09",
        "end": "2026-04-03",
        "trading_session_count": 61,
        "d_plus_1_excluded_from_factor_calculation": True,
    }
    assert result.loop_input.market.market_data_provenance["factor_rows_excluded_after_decision"] > 0
    assert set(result.loop_input.market.execution_rows_by_symbol) == {candidate.symbol}


def test_candidate_ids_are_deterministic_for_reversed_fixture_rows(tmp_path: Path) -> None:
    bars = fixture_bars()
    first = build_real_candidate_daily_paper_input(config(tmp_path / "a", input_bars=bars))
    second = build_real_candidate_daily_paper_input(config(tmp_path / "b", input_bars=tuple(reversed(bars))))

    assert first.candidate_report.candidates[0].metadata["candidate_id"] == second.candidate_report.candidates[0].metadata["candidate_id"]
    assert first.candidate_pipeline_report["digests"]["loop_input"] == second.candidate_pipeline_report["digests"]["loop_input"]


def test_current_holding_rank_dropout_becomes_exit_candidate_without_t_plus_one_override(tmp_path: Path) -> None:
    seed_holding(tmp_path, "600000.SH")
    result = build_real_candidate_daily_paper_input(config(tmp_path, symbols=("600000.SH", "000001.SZ", "600519.SH")))
    exits = [candidate for candidate in result.candidate_report.candidates if candidate.direction == "short"]

    assert [candidate.symbol for candidate in exits] == ["600000.SH"]
    assert exits[0].expected_return == -0.03
    assert exits[0].metadata["action"] == "exit"
    assert exits[0].metadata["exit_signal"] is True
    assert exits[0].metadata["exit_reason"] == "rank_dropout"
    assert exits[0].metadata["current_quantity"] == 100
    assert exits[0].metadata["acquisition_dates"] == ("2026-01-05",)
    assert exits[0].metadata["holding_period_sessions"] == 65
    assert exits[0].metadata["holding_period_status"] == "available"


def test_selected_current_holding_is_hold_not_duplicate_buy(tmp_path: Path) -> None:
    # without account_capabilities: backward compatible — holding is event only, not a candidate
    seed_holding(tmp_path / "no-caps", "600519.SH")
    no_caps = build_real_candidate_daily_paper_input(config(tmp_path / "no-caps"))
    assert no_caps.candidate_report.candidates == ()
    assert no_caps.candidate_report.aggregate_score == 0.0
    assert no_caps.candidate_pipeline_report["candidate_events"]["holds"][0]["reason"] == "holding_selected_no_duplicate_entry"

    # with account_capabilities: holding is a visible candidate with pipeline_role "original_selected_holding"
    seed_holding(tmp_path / "caps", "600519.SH")
    with_caps = build_real_candidate_daily_paper_input(replace(config(tmp_path / "caps"), account_capabilities=AccountCapabilities()))
    holding_candidates = [c for c in with_caps.candidate_report.candidates if c.symbol == "600519.SH"]
    assert len(holding_candidates) == 1
    assert holding_candidates[0].direction == "long"
    assert holding_candidates[0].metadata.get("pipeline_role") == "original_selected_holding"
    assert with_caps.candidate_pipeline_report["candidate_events"]["holds"][0]["reason"] == "holding_selected_no_duplicate_entry"
    assert with_caps.candidate_pipeline_report["candidate_events"]["holds"][0]["pipeline_role"] == "original_selected_holding"


def test_insufficient_holding_factor_evidence_is_hold_not_forced_exit(tmp_path: Path) -> None:
    seed_holding(tmp_path, "000001.SZ")
    rows = tuple(row for row in fixture_bars() if row["symbol"] != "000001.SZ")
    calendar = _offline_calendar(date.fromisoformat(DECISION))
    decision = date.fromisoformat(DECISION)
    execution = calendar.next_session(decision)
    for session in (decision, execution):
        rows += (
            {
                "symbol": "000001.SZ",
                "date": session.isoformat(),
                "open": 10.0,
                "high": 10.2,
                "low": 9.8,
                "close": 10.0,
                "volume": 100_000,
                "amount": 1_000_000,
                "is_suspended": False,
            },
        )

    result = build_real_candidate_daily_paper_input(config(tmp_path, input_bars=rows))

    assert all(candidate.symbol != "000001.SZ" or candidate.direction != "short" for candidate in result.candidate_report.candidates)
    assert result.candidate_pipeline_report["candidate_events"]["holds"][-1]["reason"] == "hold_no_decision_insufficient_factor_evidence"


def test_duplicate_conflict_and_future_rows_are_rejected(tmp_path: Path) -> None:
    bars = list(fixture_bars())
    conflict = {**bars[0], "close": bars[0]["close"] + 1.0}
    with pytest.raises(ValueError, match="conflicting daily bar rows"):
        build_real_candidate_daily_paper_input(config(tmp_path / "conflict", input_bars=tuple([*bars, conflict])))

    future = {**bars[0], "date": (date.fromisoformat(DECISION) + timedelta(days=10)).isoformat()}
    with pytest.raises(ValueError, match="after execution session"):
        build_real_candidate_daily_paper_input(config(tmp_path / "future", input_bars=tuple([*bars, future])))


def test_pipeline_runner_delegates_to_daily_paper_loop_and_writes_combined_report(tmp_path: Path) -> None:
    result = run_real_candidate_daily_paper(config(tmp_path))

    assert result.daily_paper_loop_result is not None
    assert result.daily_paper_loop_result.report["execution_session"] == "2026-04-06"
    assert result.combined_report["candidate_pipeline"]["pipeline_version"] == "real_candidate_daily_paper_v1"
    assert (tmp_path / "report.json").exists()


def test_live_pipeline_uses_public_provider_window_and_validates_pit_before_bars(tmp_path: Path) -> None:
    calendar_provider = FakeCalendarProvider()
    bar_provider = FakeBarProvider()
    result = build_real_candidate_daily_paper_input(
        config(tmp_path / "ok", symbols=("600000.SH",), live_market_data=True),
        calendar_provider=calendar_provider,
        bar_provider=bar_provider,
    )
    assert bar_provider.requests[0].start_date == date(2026, 1, 9)
    assert bar_provider.requests[0].end_date == date(2026, 4, 6)
    assert result.loop_input.market.market_data_provenance["bar_start_session"] == "2026-01-09"

    fallback = build_real_candidate_daily_paper_input(
        config(tmp_path / "fallback", symbols=("600000.SH",), live_market_data=True),
        calendar_provider=FakeCalendarProvider(),
        bar_provider=FakeBarProvider(fallback=True),
    )
    assert fallback.candidate_pipeline_report["provenance"]["market"]["bar_attempts"]["600000.SH"]["selected_provider"] == "baostock"
    assert fallback.candidate_pipeline_report["provenance"]["market"]["bar_attempts"]["600000.SH"]["fallback_used"] is True

    bad_bar_provider = FakeBarProvider()
    with pytest.raises(ValueError, match="timezone-aware|after decision cutoff"):
        build_real_candidate_daily_paper_input(
            config(
                tmp_path / "bad",
                symbols=("600000.SH",),
                live_market_data=True,
                quant_firm_context={"nested": {"signal_timestamp": "2026-04-03T14:59:00"}},
            ),
            calendar_provider=FakeCalendarProvider(),
            bar_provider=bad_bar_provider,
        )
    assert bad_bar_provider.requests == []


def test_any_factor_rejection_or_nonfinite_holding_evidence_is_hold_not_exit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seed_holding(tmp_path, "600000.SH")

    def fake_report(*args, **kwargs):
        score = factor_score("600000.SH", composite=0.7)
        return SimpleNamespace(
            factor_scores=(score,),
            selected_symbols=(),
            rejected_symbols_with_reasons=({"symbol": "600000.SH", "reasons": ("liquidity_filter_failed", "drawdown_guard_failed")},),
            ranking_mode="defensive_composite_v1",
        )

    monkeypatch.setattr("quantpilot_core.real_candidate_pipeline.pipeline.run_factor_ranking_baseline_v1", fake_report)
    result = build_real_candidate_daily_paper_input(config(tmp_path, symbols=("600000.SH",)))
    assert result.candidate_report.candidates == ()
    assert result.candidate_pipeline_report["candidate_events"]["holds"][0]["reason"] == "hold_no_decision_factor_rejected"


def test_equal_score_rank_tie_break_candidate_metadata_and_selected_order_agree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_report(*args, **kwargs):
        return SimpleNamespace(
            factor_scores=(factor_score("600000.SH", composite=0.5), factor_score("000001.SZ", composite=0.5)),
            selected_symbols=("600000.SH", "000001.SZ"),
            rejected_symbols_with_reasons=(),
            ranking_mode="defensive_composite_v1",
        )

    monkeypatch.setattr("quantpilot_core.real_candidate_pipeline.pipeline.run_factor_ranking_baseline_v1", fake_report)
    result = build_real_candidate_daily_paper_input(config(tmp_path, symbols=("600000.SH", "000001.SZ"), target_symbol_count=2))

    assert result.candidate_pipeline_report["selected_symbols"] == ("000001.SZ", "600000.SH")
    assert [candidate.symbol for candidate in result.candidate_report.candidates] == ["000001.SZ", "600000.SH"]
    assert [candidate.metadata["factor_rank"] for candidate in result.candidate_report.candidates] == [1, 2]


def test_account_backfill_forwards_ranked_pool_when_top_candidate_permission_denied(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_report(*args, **kwargs):
        return SimpleNamespace(
            factor_scores=(factor_score("688001.SH", composite=0.9), factor_score("600000.SH", composite=0.8)),
            selected_symbols=("688001.SH",),
            rejected_symbols_with_reasons=(),
            ranking_mode="defensive_composite_v1",
        )

    monkeypatch.setattr("quantpilot_core.real_candidate_pipeline.pipeline.run_factor_ranking_baseline_v1", fake_report)
    cfg = config(
        tmp_path,
        symbols=("688001.SH", "600000.SH"),
        target_symbol_count=1,
        max_execution_symbols=2,
        account_capabilities=AccountCapabilities(star_market=False),
    )
    result = run_real_candidate_daily_paper(cfg)

    assert [candidate.symbol for candidate in result.candidate_report.candidates] == ["688001.SH", "600000.SH"]
    daily = result.combined_report["daily_paper_loop"]
    assert daily["account_executable_universe"]["account_executable_symbols"] == ["600000.SH"]
    assert daily["account_executable_universe"]["exclusions"][0]["symbol"] == "688001.SH"
    assert daily["fills"][0]["symbol"] == "600000.SH"


def test_no_account_capabilities_preserves_original_selected_candidate_behavior(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_report(*args, **kwargs):
        return SimpleNamespace(
            factor_scores=(factor_score("688001.SH", composite=0.9), factor_score("600000.SH", composite=0.8)),
            selected_symbols=("688001.SH",),
            rejected_symbols_with_reasons=(),
            ranking_mode="defensive_composite_v1",
        )

    monkeypatch.setattr("quantpilot_core.real_candidate_pipeline.pipeline.run_factor_ranking_baseline_v1", fake_report)
    result = build_real_candidate_daily_paper_input(
        config(tmp_path, symbols=("688001.SH", "600000.SH"), target_symbol_count=1, max_execution_symbols=2)
    )

    assert [candidate.symbol for candidate in result.candidate_report.candidates] == ["688001.SH"]
    assert result.loop_input.quant_firm_context["candidate_pipeline"]["selected_symbols"] == ("688001.SH",)


def test_account_backfill_pool_excludes_hard_rejected_ranked_candidates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_report(*args, **kwargs):
        return SimpleNamespace(
            factor_scores=(
                factor_score("688001.SH", composite=0.9),
                factor_score("600000.SH", composite=0.8),
                factor_score("000001.SZ", composite=0.7),
            ),
            selected_symbols=("688001.SH",),
            rejected_symbols_with_reasons=({"symbol": "000001.SZ", "reasons": ("missing_factor_data",)},),
            ranking_mode="defensive_composite_v1",
        )

    monkeypatch.setattr("quantpilot_core.real_candidate_pipeline.pipeline.run_factor_ranking_baseline_v1", fake_report)
    cfg = config(
        tmp_path,
        symbols=("688001.SH", "600000.SH", "000001.SZ"),
        target_symbol_count=1,
        max_execution_symbols=3,
        account_capabilities=AccountCapabilities(star_market=False),
    )
    result = run_real_candidate_daily_paper(cfg)

    assert [candidate.symbol for candidate in result.candidate_report.candidates] == ["688001.SH", "600000.SH"]
    assert any(
        event["symbol"] == "000001.SZ"
        and event["reason"] == "factor_rejected"
        and event["factor_rejection_reasons"] == ("missing_factor_data",)
        for event in result.candidate_pipeline_report["candidate_events"]["rejected"]
    )
    assert "000001.SZ" not in result.candidate_pipeline_report["forwarded_standby_symbols"]
    assert "000001.SZ" not in result.candidate_pipeline_report["account_candidate_pool_symbols"]
    daily = result.combined_report["daily_paper_loop"]
    assert daily["account_executable_universe"]["account_executable_symbols"] == ["600000.SH"]
    assert daily["fills"][0]["symbol"] == "600000.SH"


def test_account_backfill_keeps_cutoff_only_candidates_but_excludes_hard_rejections(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_report(*args, **kwargs):
        return SimpleNamespace(
            factor_scores=(
                factor_score("688001.SH", composite=0.9),
                factor_score("600000.SH", composite=0.8),
                factor_score("000001.SZ", composite=0.7),
            ),
            selected_symbols=("688001.SH",),
            rejected_symbols_with_reasons=(
                {"symbol": "600000.SH", "reasons": ("not_selected_lower_rank",)},
                {"symbol": "000001.SZ", "reasons": ("not_selected_lower_rank", "missing_factor_data")},
            ),
            ranking_mode="defensive_composite_v1",
        )

    monkeypatch.setattr("quantpilot_core.real_candidate_pipeline.pipeline.run_factor_ranking_baseline_v1", fake_report)
    cfg = config(
        tmp_path,
        symbols=("688001.SH", "600000.SH", "000001.SZ"),
        target_symbol_count=1,
        max_execution_symbols=3,
        account_capabilities=AccountCapabilities(star_market=False),
    )
    result = run_real_candidate_daily_paper(cfg)

    assert [candidate.symbol for candidate in result.candidate_report.candidates] == ["688001.SH", "600000.SH"]
    assert result.candidate_pipeline_report["account_candidate_pool_symbols"] == ("688001.SH", "600000.SH")
    assert result.candidate_pipeline_report["forwarded_standby_symbols"] == ("600000.SH",)
    assert "000001.SZ" not in result.candidate_pipeline_report["account_candidate_pool_symbols"]
    assert any(
        event["symbol"] == "000001.SZ"
        and event["reason"] == "factor_rejected"
        and event["factor_rejection_reasons"] == ("missing_factor_data",)
        for event in result.candidate_pipeline_report["candidate_events"]["rejected"]
    )
    daily = result.combined_report["daily_paper_loop"]
    assert daily["account_executable_universe"]["account_executable_symbols"] == ["600000.SH"]
    assert daily["fills"][0]["symbol"] == "600000.SH"


def test_account_backfill_capacity_counts_existing_holdings_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seed_holding(tmp_path, "600000.SH")

    def fake_report(*args, **kwargs):
        return SimpleNamespace(
            factor_scores=(factor_score("000001.SZ", composite=0.9), factor_score("600519.SH", composite=0.8)),
            selected_symbols=("000001.SZ",),
            rejected_symbols_with_reasons=({"symbol": "600519.SH", "reasons": ("not_selected_lower_rank",)},),
            ranking_mode="defensive_composite_v1",
        )

    monkeypatch.setattr("quantpilot_core.real_candidate_pipeline.pipeline.run_factor_ranking_baseline_v1", fake_report)
    result = build_real_candidate_daily_paper_input(
        config(
            tmp_path,
            symbols=("600000.SH", "000001.SZ", "600519.SH"),
            input_bars=fixture_bars(("600000.SH", "000001.SZ", "600519.SH")),
            target_symbol_count=1,
            max_execution_symbols=2,
            account_capabilities=AccountCapabilities(),
        )
    )

    assert result.candidate_pipeline_report["holdings"] == ("600000.SH",)
    assert result.candidate_pipeline_report["account_candidate_pool_symbols"] == ("000001.SZ",)
    assert result.candidate_pipeline_report["forwarded_standby_symbols"] == ()
    assert "600519.SH" not in result.candidate_pipeline_report["forwarded_standby_symbols"]
    assert set(result.loop_input.market.decision_rows_by_symbol) == {"600000.SH", "000001.SZ"}


def test_account_backfill_ranked_holding_does_not_consume_capacity_twice(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seed_holding(tmp_path, "600000.SH")

    def fake_report(*args, **kwargs):
        return SimpleNamespace(
            factor_scores=(factor_score("600000.SH", composite=0.9), factor_score("000001.SZ", composite=0.8)),
            selected_symbols=("600000.SH",),
            rejected_symbols_with_reasons=({"symbol": "000001.SZ", "reasons": ("not_selected_lower_rank",)},),
            ranking_mode="defensive_composite_v1",
        )

    monkeypatch.setattr("quantpilot_core.real_candidate_pipeline.pipeline.run_factor_ranking_baseline_v1", fake_report)
    result = build_real_candidate_daily_paper_input(
        config(
            tmp_path,
            symbols=("600000.SH", "000001.SZ"),
            input_bars=fixture_bars(("600000.SH", "000001.SZ")),
            target_symbol_count=1,
            max_execution_symbols=2,
            account_capabilities=AccountCapabilities(),
        )
    )

    assert result.candidate_pipeline_report["account_candidate_pool_symbols"] == ("600000.SH", "000001.SZ")
    assert result.candidate_pipeline_report["forwarded_standby_symbols"] == ("000001.SZ",)
    # holding 600000.SH is now a visible candidate (pipeline_role: original_selected_holding)
    candidate_symbols = [candidate.symbol for candidate in result.candidate_report.candidates]
    assert "600000.SH" in candidate_symbols
    assert "000001.SZ" in candidate_symbols
    # holding is registered in events as a hold
    assert result.candidate_pipeline_report["candidate_events"]["holds"][0]["symbol"] == "600000.SH"
    assert result.candidate_pipeline_report["candidate_events"]["holds"][0]["pipeline_role"] == "original_selected_holding"


def test_holdings_alone_exceeding_execution_cap_has_deterministic_error(tmp_path: Path) -> None:
    state = initialize_daily_state(100_000.0)
    seeded = replace(
        state.execution_state,
        account=PaperAccount(
            cash=80_000.0,
            positions={"600000.SH": 100, "000001.SZ": 100},
            average_costs={"600000.SH": 10.0, "000001.SZ": 10.0},
        ),
        settlement_lots=(SettlementLot("600000.SH", 100, "2026-01-05"), SettlementLot("000001.SZ", 100, "2026-01-05")),
    )
    save_daily_state_atomic(replace(state, execution_state=seeded), tmp_path / "state.json")

    with pytest.raises(ValueError, match="holding symbols exceed max_execution_symbols"):
        build_real_candidate_daily_paper_input(
            config(
                tmp_path,
                symbols=("600000.SH", "000001.SZ"),
                input_bars=fixture_bars(("600000.SH", "000001.SZ")),
                target_symbol_count=1,
                max_execution_symbols=1,
                account_capabilities=AccountCapabilities(),
            )
        )


def test_unloaded_acquisition_session_reports_unavailable_holding_period(tmp_path: Path) -> None:
    state = initialize_daily_state(100_000.0)
    seeded = replace(
        state.execution_state,
        account=PaperAccount(cash=90_000.0, positions={"600000.SH": 100}, average_costs={"600000.SH": 10.0}),
        settlement_lots=(SettlementLot("600000.SH", 100, "2026-01-04"),),
    )
    save_daily_state_atomic(replace(state, execution_state=seeded), tmp_path / "state.json")

    result = build_real_candidate_daily_paper_input(config(tmp_path, symbols=("600000.SH", "000001.SZ", "600519.SH")))
    exit_candidate = next(candidate for candidate in result.candidate_report.candidates if candidate.symbol == "600000.SH")
    assert exit_candidate.metadata["holding_period_sessions"] is None
    assert exit_candidate.metadata["holding_period_status"] == "unavailable_acquisition_date_not_loaded_session"


def test_factor_evidence_change_changes_candidate_id_even_when_composite_same(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    evidence_value = {"value": 0.2}

    def fake_report(*args, **kwargs):
        return SimpleNamespace(
            factor_scores=(factor_score("600000.SH", composite=0.5, liquidity=evidence_value["value"]),),
            selected_symbols=("600000.SH",),
            rejected_symbols_with_reasons=(),
            ranking_mode="defensive_composite_v1",
        )

    monkeypatch.setattr("quantpilot_core.real_candidate_pipeline.pipeline.run_factor_ranking_baseline_v1", fake_report)
    first = build_real_candidate_daily_paper_input(config(tmp_path / "first", symbols=("600000.SH",)))
    evidence_value["value"] = 0.8
    second = build_real_candidate_daily_paper_input(config(tmp_path / "second", symbols=("600000.SH",)))

    assert first.candidate_report.candidates[0].confidence == second.candidate_report.candidates[0].confidence
    assert first.candidate_report.candidates[0].metadata["candidate_id"] != second.candidate_report.candidates[0].metadata["candidate_id"]


def test_mixed_entry_and_exit_preserves_requested_actions_in_quant_context(tmp_path: Path) -> None:
    seed_holding(tmp_path, "600000.SH")
    result = build_real_candidate_daily_paper_input(config(tmp_path, symbols=("600000.SH", "000001.SZ", "600519.SH")))

    assert {candidate.direction for candidate in result.candidate_report.candidates} == {"long", "short"}
    assert result.loop_input.quant_firm_context["requested_action"] == "mixed"
    assert result.loop_input.quant_firm_context["requested_actions"] == ("buy", "exit")


def test_information_signals_are_pit_safe_context_not_factor_features(tmp_path: Path) -> None:
    signal = InformationAgentSignal(
        agent_role=InformationAgentRole.NEWS_IMPACT,
        target="600000.SH",
        direction=InformationDirection.POSITIVE,
        score=0.4,
        confidence=0.7,
        horizon=InformationHorizon.SHORT_TERM,
        regime="announcement_title_fallback",
        evidence=("published_at:2026-04-03T14:00:00+08:00",),
        limitations=("deterministic_fallback_no_live_deepseek",),
    )
    envelope = {"signal": signal, "available_at": "2026-04-03T14:00:00+08:00", "source_event_id": "evt-1", "provenance": {"source": "fixture"}}
    result = build_real_candidate_daily_paper_input(config(tmp_path, information_signals=(envelope,)))
    assert result.loop_input.quant_firm_context["information_signals"][0]["signal"]["target"] == "600000.SH"
    assert result.loop_input.advisory_provenance["deepseek_live_call"] is False
    assert result.candidate_report.candidates

    with pytest.raises(ValueError, match="not a PIT-safe candidate feature"):
        build_real_candidate_daily_paper_input(
            config(
                tmp_path / "bad-label",
                information_signals=({"signal": {"target": "600000.SH", "event_study_label_forward_return": 0.1}, "available_at": "2026-04-03T14:00:00+08:00"},),
            )
        )

    with pytest.raises(ValueError, match="structured PIT envelope"):
        build_real_candidate_daily_paper_input(config(tmp_path / "raw", information_signals=(signal,)))

    with pytest.raises(ValueError, match="after decision cutoff"):
        build_real_candidate_daily_paper_input(
            config(tmp_path / "future", information_signals=({"signal": signal, "available_at": "2026-04-03T15:01:00+08:00"},))
        )

    with pytest.raises(ValueError, match="timezone-aware"):
        build_real_candidate_daily_paper_input(
            config(tmp_path / "naive", information_signals=({"signal": signal, "available_at": "2026-04-03T14:00:00"},))
        )

    with pytest.raises(ValueError, match="not a PIT-safe candidate feature"):
        build_real_candidate_daily_paper_input(
            config(
                tmp_path / "leaky-string",
                information_signals=({"signal": {"evidence": ("stock_forward_return_5d:0.1",)}, "available_at": "2026-04-03T14:00:00+08:00"},),
            )
        )


def test_pipeline_idempotent_replay_and_conflict_do_not_regenerate_from_mutated_state(tmp_path: Path) -> None:
    cfg = config(tmp_path, symbols=("600000.SH", "000001.SZ", "600519.SH"))
    first = run_real_candidate_daily_paper(cfg)
    state_after_first = load_state_payload(tmp_path)

    second = run_real_candidate_daily_paper(cfg)
    state_after_second = load_state_payload(tmp_path)

    assert first.daily_paper_loop_result.report["idempotency_status"] == "completed"
    assert second.daily_paper_loop_result.report["idempotency_status"] == "idempotent_replay"
    assert first.candidate_report.candidates[0].metadata["candidate_id"] == second.candidate_report.candidates[0].metadata["candidate_id"]
    assert state_after_first["state_hash"] == state_after_second["state_hash"]

    with pytest.raises(PipelineIdempotencyConflictError):
        run_real_candidate_daily_paper(config(tmp_path, symbols=("000001.SZ", "600519.SH")))
    assert load_state_payload(tmp_path)["state_hash"] == state_after_first["state_hash"]


def test_shadow_evidence_isolated_from_manifest_bound_production_identities(tmp_path: Path) -> None:
    pr121 = tmp_path / "pr121.json"; pr121.write_text("{}")
    pr122 = tmp_path / "pr122.json"; pr122.write_text("{}")
    manifest = build_production_candidate_manifest(
        created_at="2026-07-12T00:00:00+00:00",
        code_revision="revision",
        snapshot_digest="a" * 64,
        benchmark={"symbol": "000300.SH"},
        source_artifacts={"pr121": pr121, "pr122": pr122},
        frozen_strategy_parameters={"initial_capital": 100000.0, "target_symbol_count": 2, "max_execution_symbols": 6, "strategy_id": "equal_weight_baseline"},
        frozen_portfolio_parameters={"target_position_count": 2, "max_position_weight": .1, "reserve_cash_weight": .02},
        frozen_execution_parameters={"min_order_lot": 100},
        fee_profile_policy={"profile_id": "engineering-fallback-from-paper-fill-cost-assumptions", "required_provenance": "engineering_fallback"},
        account_capability_policy={"capability_digest": payload_digest(None)},
    )
    common = dict(symbols=("600000.SH", "000001.SZ"), strategy_id="equal_weight_baseline", target_symbol_count=2, target_position_count=2, production_manifest=manifest)
    first_evidence = {"packet": "one"}
    second_evidence = {"packet": "two"}
    first = run_real_candidate_daily_paper(config(tmp_path / "first", quant_firm_context={"shadow_desk_evidence": first_evidence}, shadow_desk_evidence=first_evidence, **common))
    second = run_real_candidate_daily_paper(config(tmp_path / "second", quant_firm_context={"shadow_desk_evidence": second_evidence}, shadow_desk_evidence=second_evidence, **common))

    first_pipeline = first.candidate_pipeline_report
    second_pipeline = second.candidate_pipeline_report
    first_daily = first.daily_paper_loop_result.report
    second_daily = second.daily_paper_loop_result.report
    assert first_pipeline["pipeline_request_digest"] == second_pipeline["pipeline_request_digest"]
    assert first_pipeline["digests"]["loop_input"] == second_pipeline["digests"]["loop_input"]
    assert first_daily["input_digest"] == second_daily["input_digest"]
    assert first_daily["session_id"] == second_daily["session_id"]
    for key in ("candidate_report", "allocation_sizing", "order_intents", "fills", "ledger_after", "reconciliation_audit"):
        assert first_daily[key] == second_daily[key]
    assert first_daily["order_intents"]["intents"] == second_daily["order_intents"]["intents"]
    assert load_state_payload(tmp_path / "first")["state_hash"] == load_state_payload(tmp_path / "second")["state_hash"]
    assert first_daily["ai_shadow_report"]["ai_shadow_evidence_digest"] != second_daily["ai_shadow_report"]["ai_shadow_evidence_digest"]


def test_reordered_symbols_replay_without_digest_conflict_or_duplicate_fill(tmp_path: Path) -> None:
    first = run_real_candidate_daily_paper(config(tmp_path, symbols=("600000.SH", "000001.SZ", "600519.SH")))
    state_after_first = load_state_payload(tmp_path)
    replay = run_real_candidate_daily_paper(config(tmp_path, symbols=("600519.SH", "000001.SZ", "600000.SH")))

    assert replay.daily_paper_loop_result.report["idempotency_status"] == "idempotent_replay"
    assert replay.candidate_pipeline_report["pipeline_request_digest"] == first.candidate_pipeline_report["pipeline_request_digest"]
    assert replay.candidate_report.candidates[0].metadata["candidate_id"] == first.candidate_report.candidates[0].metadata["candidate_id"]
    assert load_state_payload(tmp_path)["state_hash"] == state_after_first["state_hash"]


def test_reversed_and_duplicate_bars_replay_but_real_bar_change_conflicts(tmp_path: Path) -> None:
    bars = fixture_bars(("600000.SH", "000001.SZ", "600519.SH"))
    first = run_real_candidate_daily_paper(config(tmp_path / "reverse", input_bars=bars))
    state_after_first = load_state_payload(tmp_path / "reverse")
    replay = run_real_candidate_daily_paper(config(tmp_path / "reverse", input_bars=tuple(reversed(bars))))
    duplicate_replay = run_real_candidate_daily_paper(config(tmp_path / "reverse", input_bars=(*bars, bars[0])))

    assert replay.daily_paper_loop_result.report["idempotency_status"] == "idempotent_replay"
    assert duplicate_replay.daily_paper_loop_result.report["idempotency_status"] == "idempotent_replay"
    assert replay.candidate_pipeline_report["pipeline_request_digest"] == first.candidate_pipeline_report["pipeline_request_digest"]
    assert duplicate_replay.candidate_pipeline_report["pipeline_request_digest"] == first.candidate_pipeline_report["pipeline_request_digest"]
    assert load_state_payload(tmp_path / "reverse")["state_hash"] == state_after_first["state_hash"]

    changed = tuple({**row, "close": row["close"] + 0.01} if index == 0 else row for index, row in enumerate(bars))
    with pytest.raises(PipelineIdempotencyConflictError):
        run_real_candidate_daily_paper(config(tmp_path / "reverse", input_bars=changed))
    assert load_state_payload(tmp_path / "reverse")["state_hash"] == state_after_first["state_hash"]


def test_immediate_replay_uses_canonical_daily_report_schema_and_preserves_fields(tmp_path: Path) -> None:
    first = run_real_candidate_daily_paper(config(tmp_path))
    second = run_real_candidate_daily_paper(config(tmp_path))

    assert first.daily_paper_loop_result.report["idempotency_status"] == "completed"
    assert second.daily_paper_loop_result.report["idempotency_status"] == "idempotent_replay"
    for key in canonical_report_parity_keys():
        assert second.daily_paper_loop_result.report[key] == first.daily_paper_loop_result.report[key]
    assert second.combined_report["candidate_pipeline"] == first.combined_report["candidate_pipeline"]
    assert "quant_firm_report" in second.combined_report["daily_paper_loop"]
    assert "metadata_availability" in second.combined_report["daily_paper_loop"]


def test_live_completed_session_replay_makes_no_provider_calls(tmp_path: Path) -> None:
    cfg = config(tmp_path, symbols=("600000.SH",), live_market_data=True)
    first_calendar = FakeCalendarProvider()
    first_bars = FakeBarProvider()
    run_real_candidate_daily_paper(cfg, calendar_provider=first_calendar, bar_provider=first_bars)

    replay_calendar = FakeCalendarProvider()
    replay_bars = FakeBarProvider()
    replay = run_real_candidate_daily_paper(cfg, calendar_provider=replay_calendar, bar_provider=replay_bars)

    assert replay.daily_paper_loop_result.report["idempotency_status"] == "idempotent_replay"
    assert replay_calendar.requests == []
    assert replay_bars.requests == []


def test_offline_universe_filters_extra_bar_symbol_and_derives_from_bars(tmp_path: Path) -> None:
    bars = fixture_bars(("600000.SH", "000001.SZ"))
    extra = fixture_bars(("600519.SH",))
    result = build_real_candidate_daily_paper_input(config(tmp_path / "explicit", symbols=("600000.sh", "600000.SH"), input_bars=(*bars, *extra)))
    assert result.candidate_pipeline_report["universe"]["resolved"] == ("600000.SH",)
    assert result.candidate_pipeline_report["universe"]["excluded"] == ("000001.SZ", "600519.SH")
    assert result.candidate_pipeline_report["universe"]["factor_symbols"] == ("600000.SH",)

    derived = build_real_candidate_daily_paper_input(config(tmp_path / "derived", input_bars=bars))
    assert derived.candidate_pipeline_report["universe"]["origin"] == "input_bars"
    assert set(derived.candidate_pipeline_report["universe"]["resolved"]) == {"600000.SH", "000001.SZ"}


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"initial_capital": float("nan")}, "initial_capital"),
        ({"initial_capital": float("inf")}, "initial_capital"),
        ({"initial_capital": 0.0}, "initial_capital"),
        ({"max_execution_symbols": 0}, "max_execution_symbols"),
        ({"max_execution_symbols": 7}, "max_execution_symbols"),
        ({"target_symbol_count": 0}, "target_symbol_count"),
        ({"max_execution_symbols": 1, "target_symbol_count": 2}, "target_symbol_count"),
        ({"strategy_id": " "}, "strategy_id"),
        ({"symbols": ("bad-symbol",)}, "invalid A-share symbol"),
        ({"decision_session": "2026/04/03"}, "decision_session"),
    ],
)
def test_pipeline_config_validation(tmp_path: Path, kwargs, match) -> None:
    with pytest.raises(ValueError, match=match):
        build_real_candidate_daily_paper_input(config(tmp_path, **kwargs))


def test_real_entry_end_to_end_order_fill_and_persisted_state(tmp_path: Path) -> None:
    result = run_real_candidate_daily_paper(config(tmp_path / "entry", symbols=("600000.SH", "000001.SZ", "600519.SH"), initial_capital=100_000.0))
    report = result.daily_paper_loop_result.report
    state = load_state_payload(tmp_path / "entry")

    assert result.candidate_report.candidates[0].direction == "long"
    assert report["order_intents"]["intents"]
    assert report["fills"]
    assert report["ledger_after"]["cash"] < report["ledger_before"]["cash"]
    assert report["ledger_after"]["positions"]
    assert state["execution_state"]["settlement_lots"]
    assert report["fee_breakdown"]["total_cost"] >= 0
    assert report["reconciliation_audit"]["status"] == "passed"
    assert state["state_hash"] == report["state"]["hash_after"]


def test_zero_factor_liquidity_keeps_affordable_real_candidate_actionable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_report(*args, **kwargs):
        return SimpleNamespace(
            factor_scores=(factor_score("000001.SZ", composite=0.9, liquidity=0.0),),
            selected_symbols=("000001.SZ",),
            rejected_symbols_with_reasons=(),
            ranking_mode="defensive_composite_v1",
        )

    monkeypatch.setattr("quantpilot_core.real_candidate_pipeline.pipeline.run_factor_ranking_baseline_v1", fake_report)
    result = run_real_candidate_daily_paper(
        config(
            tmp_path,
            symbols=("000001.SZ",),
            input_bars=single_symbol_bars(),
            initial_capital=100_000.0,
        )
    )

    candidate = result.candidate_report.candidates[0]
    metadata = candidate.metadata
    report = result.daily_paper_loop_result.report
    allocation = report["allocation_sizing"]["allocations"][0]
    order = report["order_intents"]["intents"][0]

    assert candidate.symbol == "000001.SZ"
    assert candidate.confidence == 0.9
    assert candidate.expected_return == 0.03
    assert candidate.risk_score == 0.1
    assert metadata["factor_normalized_liquidity"] == 0.0
    assert metadata["raw_liquidity_proxy"] == 1_000_000.0
    assert candidate.liquidity_score == 0.5
    assert metadata["execution_liquidity_score"] == 0.5
    assert metadata["execution_liquidity_neutral_fallback_used"] is True
    assert metadata["d_volume"] == 87_549_118.0
    assert metadata["d_close"] == 11.5
    assert result.candidate_pipeline_report["selected_symbols"] == ("000001.SZ",)
    assert result.candidate_pipeline_report["evidence"]["000001.SZ"]["factor_evidence"]["normalized_factors"]["liquidity_proxy"] == 0.0
    assert allocation["raw_score"] > 0
    assert allocation["target_weight"] > 0
    assert allocation["target_shares"] >= 100
    assert order["target_shares"] >= 100
    assert order["target_shares"] % 100 == 0
    assert report["quant_firm_report"]["final_recommendation"] == "approve_offline_shadow_cycle"
    assert report["fills"]
    assert report["reconciliation_audit"]["status"] == "passed"


def test_no_candidate_end_to_end_still_persists_and_replays(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_report(*args, **kwargs):
        return SimpleNamespace(
            factor_scores=(factor_score("600000.SH", composite=0.5),),
            selected_symbols=(),
            rejected_symbols_with_reasons=({"symbol": "600000.SH", "reasons": ("missing_factor_data",)},),
            ranking_mode="defensive_composite_v1",
        )

    monkeypatch.setattr("quantpilot_core.real_candidate_pipeline.pipeline.run_factor_ranking_baseline_v1", fake_report)
    cfg = config(tmp_path, symbols=("600000.SH",))
    first = run_real_candidate_daily_paper(cfg)
    second = run_real_candidate_daily_paper(cfg)

    assert first.candidate_report.candidates == ()
    assert first.daily_paper_loop_result.report["order_intents"]["intents"] == []
    assert first.daily_paper_loop_result.report["fills"] == []
    assert first.daily_paper_loop_result.report["reconciliation_audit"]["status"] == "passed"
    assert second.daily_paper_loop_result.report["idempotency_status"] == "idempotent_replay"


def test_capital_changes_do_not_change_candidate_identity_or_rank(tmp_path: Path) -> None:
    low = build_real_candidate_daily_paper_input(config(tmp_path / "low", initial_capital=1_000.0))
    mid = build_real_candidate_daily_paper_input(config(tmp_path / "mid", initial_capital=10_000.0))
    high = build_real_candidate_daily_paper_input(config(tmp_path / "high", initial_capital=100_000.0))

    assert low.candidate_report.candidates[0].metadata["candidate_id"] == mid.candidate_report.candidates[0].metadata["candidate_id"]
    assert mid.candidate_report.candidates[0].metadata["candidate_id"] == high.candidate_report.candidates[0].metadata["candidate_id"]
    assert low.candidate_report.candidates[0].metadata["factor_rank"] == high.candidate_report.candidates[0].metadata["factor_rank"]

    low_run = run_real_candidate_daily_paper(config(tmp_path / "low-run", initial_capital=1_000.0))
    assert low_run.candidate_report.candidates
    assert low_run.daily_paper_loop_result.report["fills"] == []
    assert low_run.daily_paper_loop_result.report["skipped_orders"]


def test_affordable_capital_allocates_without_changing_candidate_rank(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_report(*args, **kwargs):
        return SimpleNamespace(
            factor_scores=(factor_score("000001.SZ", composite=0.9, liquidity=0.0),),
            selected_symbols=("000001.SZ",),
            rejected_symbols_with_reasons=(),
            ranking_mode="defensive_composite_v1",
        )

    monkeypatch.setattr("quantpilot_core.real_candidate_pipeline.pipeline.run_factor_ranking_baseline_v1", fake_report)
    cheap_bars = single_symbol_bars(close=5.0)
    mid = run_real_candidate_daily_paper(config(tmp_path / "mid-affordable", symbols=("000001.SZ",), input_bars=cheap_bars, initial_capital=10_000.0))
    high = run_real_candidate_daily_paper(config(tmp_path / "high-affordable", symbols=("000001.SZ",), input_bars=cheap_bars, initial_capital=100_000.0))

    assert mid.candidate_report.candidates[0].metadata["candidate_id"] == high.candidate_report.candidates[0].metadata["candidate_id"]
    assert mid.candidate_report.candidates[0].metadata["factor_rank"] == high.candidate_report.candidates[0].metadata["factor_rank"]
    assert mid.daily_paper_loop_result.report["allocation_sizing"]["allocations"][0]["target_shares"] >= 100
    assert high.daily_paper_loop_result.report["allocation_sizing"]["allocations"][0]["target_shares"] >= 100
    assert mid.daily_paper_loop_result.report["ledger_after"]["cash"] >= 0
    assert high.daily_paper_loop_result.report["ledger_after"]["cash"] >= 0


@pytest.mark.parametrize(
    "bars, reason",
    [
        (single_symbol_bars(volume=0.0), "invalid_d_market_evidence_zero_volume"),
        (single_symbol_bars(is_suspended=True), "invalid_d_market_evidence_suspended"),
    ],
)
def test_invalid_d_liquidity_evidence_rejects_candidate_before_sizing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bars, reason: str) -> None:
    def fake_report(*args, **kwargs):
        return SimpleNamespace(
            factor_scores=(factor_score("000001.SZ", composite=0.9, liquidity=0.0),),
            selected_symbols=("000001.SZ",),
            rejected_symbols_with_reasons=(),
            ranking_mode="defensive_composite_v1",
        )

    monkeypatch.setattr("quantpilot_core.real_candidate_pipeline.pipeline.run_factor_ranking_baseline_v1", fake_report)
    result = build_real_candidate_daily_paper_input(config(tmp_path, symbols=("000001.SZ",), input_bars=bars))

    assert result.candidate_report.candidates == ()
    assert result.candidate_pipeline_report["candidate_events"]["rejected"] == ({"symbol": "000001.SZ", "reason": reason},)


@pytest.mark.parametrize("volume", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_d_volume_rejects_without_execution_fallback_or_orders(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, volume: float) -> None:
    def fake_report(*args, **kwargs):
        return SimpleNamespace(
            factor_scores=(factor_score("000001.SZ", composite=0.9, liquidity=0.0),),
            selected_symbols=("000001.SZ",),
            rejected_symbols_with_reasons=(),
            ranking_mode="defensive_composite_v1",
        )

    monkeypatch.setattr("quantpilot_core.real_candidate_pipeline.pipeline.run_factor_ranking_baseline_v1", fake_report)
    result = run_real_candidate_daily_paper(config(tmp_path, symbols=("000001.SZ",), input_bars=single_symbol_bars(volume=volume)))

    assert result.candidate_report.candidates == ()
    assert result.candidate_pipeline_report["candidate_events"]["rejected"] == (
        {"symbol": "000001.SZ", "reason": "invalid_d_market_evidence_nonfinite_volume"},
    )
    assert result.candidate_pipeline_report["candidates"]["candidates"] == ()
    assert result.daily_paper_loop_result.report["order_intents"]["intents"] == []
    assert result.daily_paper_loop_result.report["fills"] == []


def test_missing_factor_liquidity_uses_neutral_execution_fallback_with_valid_market_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    score = factor_score("000001.SZ", composite=0.9, liquidity=0.0)
    evidence = {
        **score.factor_evidence,
        "normalized_factors": {**score.factor_evidence["normalized_factors"], "liquidity_proxy": None},
        "factor_contributions": {},
    }
    missing_liquidity_score = replace(score, liquidity_proxy=None, factor_evidence=evidence)

    def fake_report(*args, **kwargs):
        return SimpleNamespace(
            factor_scores=(missing_liquidity_score,),
            selected_symbols=("000001.SZ",),
            rejected_symbols_with_reasons=(),
            ranking_mode="defensive_composite_v1",
        )

    monkeypatch.setattr("quantpilot_core.real_candidate_pipeline.pipeline.run_factor_ranking_baseline_v1", fake_report)
    result = build_real_candidate_daily_paper_input(config(tmp_path, symbols=("000001.SZ",), input_bars=single_symbol_bars()))
    candidate = result.candidate_report.candidates[0]

    assert candidate.metadata["factor_normalized_liquidity"] is None
    assert candidate.metadata["raw_liquidity_proxy"] is None
    assert candidate.liquidity_score == 0.5
    assert candidate.metadata["execution_liquidity_neutral_fallback_used"] is True


def test_restart_entry_hold_exit_and_historical_replay_restore_original_session(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    cfg1 = RealCandidatePipelineConfig(decision_session="2026-04-03", state_path=state_path, report_path=tmp_path / "s1.json", initial_capital=100_000.0)
    s1 = run_real_candidate_daily_paper(cfg1)
    s1_hash = load_state_payload(tmp_path)["state_hash"]
    s1_candidate_id = s1.candidate_report.candidates[0].metadata["candidate_id"]

    cfg2 = RealCandidatePipelineConfig(decision_session="2026-04-07", state_path=state_path, report_path=tmp_path / "s2.json", initial_capital=100_000.0)
    s2 = run_real_candidate_daily_paper(cfg2)

    cfg3 = RealCandidatePipelineConfig(
        decision_session="2026-04-09",
        state_path=state_path,
        report_path=tmp_path / "s3.json",
        initial_capital=100_000.0,
        symbols=("600519.SH", "000001.SZ"),
    )
    s3 = run_real_candidate_daily_paper(cfg3)
    state_after_s3 = load_state_payload(tmp_path)

    assert s1.daily_paper_loop_result.report["fills"][0]["side"] == "buy"
    assert s2.candidate_report.candidates == ()
    assert s2.daily_paper_loop_result.report["fills"] == []
    assert {candidate.direction for candidate in s3.candidate_report.candidates} == {"long", "short"}
    assert any(fill["side"] == "sell" and fill["symbol"] == "600519.SH" for fill in s3.daily_paper_loop_result.report["fills"])
    assert state_after_s3["execution_state"]["account"]["positions"] == {"000001.SZ": 100}
    assert state_after_s3["execution_state"]["account"]["realized_pnl_by_symbol"]

    replay = run_real_candidate_daily_paper(cfg1)
    assert replay.daily_paper_loop_result.report["idempotency_status"] == "idempotent_replay"
    assert replay.candidate_report.candidates[0].metadata["candidate_id"] == s1_candidate_id
    assert replay.candidate_report.candidates[0].lot_size == 100
    assert replay.combined_report["candidate_pipeline"]["candidates"]["candidates"][0]["lot_size"] == 100
    assert replay.combined_report["daily_paper_loop"]["candidate_report"]["candidates"][0]["lot_size"] == 100
    assert replay.daily_paper_loop_result.report["ledger_after"]["positions"] == s1.daily_paper_loop_result.report["ledger_after"]["positions"]
    assert load_state_payload(tmp_path)["state_hash"] == state_after_s3["state_hash"]
    assert replay.daily_paper_loop_result.report["state"]["hash_after"] == s1_hash
    for key in (
        "candidate_report",
        "quant_firm_report",
        "allocation_sizing",
        "order_provenance",
        "fills",
        "fee_breakdown",
        "ledger_before",
        "ledger_after",
        "realized_pnl",
        "unrealized_pnl",
        "equity",
        "reconciliation_audit",
        "leakage_audit",
    ):
        assert replay.daily_paper_loop_result.report[key] == s1.daily_paper_loop_result.report[key]
    assert replay.combined_report["candidate_pipeline"] == s1.combined_report["candidate_pipeline"]
    assert "quant_firm_report" in replay.combined_report["daily_paper_loop"]


def test_combined_report_write_failure_recovers_with_complete_replay_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original = pipeline_module.write_report_atomic
    calls = {"count": 0}

    def flaky_write(report, path):
        calls["count"] += 1
        if calls["count"] == 1:
            raise OSError("fixture write failure")
        return original(report, path)

    monkeypatch.setattr(pipeline_module, "write_report_atomic", flaky_write)
    cfg = config(tmp_path)
    with pytest.raises(OSError, match="fixture write failure"):
        run_real_candidate_daily_paper(cfg)
    state_after_failed_write = load_state_payload(tmp_path)

    recovered = run_real_candidate_daily_paper(cfg)
    assert recovered.daily_paper_loop_result.report["idempotency_status"] == "idempotent_replay"
    assert recovered.combined_report["daily_paper_loop"]["schema_version"]
    assert recovered.combined_report["daily_paper_loop"]["quant_firm_report"]
    assert recovered.combined_report["candidate_pipeline"]["pipeline_request_digest"]
    assert load_state_payload(tmp_path)["state_hash"] == state_after_failed_write["state_hash"]


def load_state_payload(tmp_path: Path) -> dict:
    import json

    return json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))


def canonical_report_parity_keys() -> tuple[str, ...]:
    return (
        "schema_version",
        "loop_version",
        "run_config",
        "session_id",
        "decision_session",
        "execution_session",
        "input_digest",
        "state",
        "calendar_provenance",
        "market_data_provenance",
        "information_provenance",
        "advisory_provenance",
        "candidate_report",
        "quant_firm_report",
        "allocation_sizing",
        "order_intents",
        "order_provenance",
        "skipped_orders",
        "fills",
        "partial_fills",
        "no_fills",
        "rejections",
        "fee_breakdown",
        "ledger_before",
        "ledger_after",
        "realized_pnl",
        "unrealized_pnl",
        "equity",
        "execution_summary",
        "metadata_availability",
        "reconciliation_audit",
        "next_session_state",
        "leakage_audit",
        "limitations",
    )


def factor_score(symbol: str, *, composite: float = 0.7, liquidity: float = 0.5) -> FactorScore:
    evidence = {
        "normalized_factors": {
            "volatility_20d": 0.5,
            "volatility_60d": 0.5,
            "momentum_20d": 0.5,
            "momentum_60d": 0.5,
            "drawdown_20d": 0.5,
            "drawdown_60d": 0.5,
            "liquidity_proxy": liquidity,
            "trend_filter": 1.0,
        },
        "factor_contributions": {"liquidity_proxy": liquidity},
        "missing_factors": (),
        "rejection_reasons": (),
    }
    return FactorScore(
        symbol=symbol,
        as_of_date=DECISION,
        volatility_20d=0.01,
        volatility_60d=0.02,
        momentum_20d=0.03,
        momentum_60d=0.04,
        drawdown_20d=-0.01,
        drawdown_60d=-0.02,
        liquidity_proxy=1_000_000.0,
        trend_filter=True,
        composite_score=composite,
        ranking_mode="defensive_composite_v1",
        factor_evidence=evidence,
    )


def test_normalized_daily_bar_old_positional_provider_still_works() -> None:
    """Construct NormalizedDailyBar with TUSHARE as 16th positional arg → provider field correct,
    new fields default to None."""
    bar = NormalizedDailyBar(
        "600000.SH", date(2026, 1, 2), 10.0, 10.0, 10.2, 9.8, 100_000.0,
        None, None, None, None, None, None, None,  # amount through is_st (7 optional fields)
        ProviderName.TUSHARE,
    )
    assert bar.provider == ProviderName.TUSHARE
    assert bar.executable_buy_price is None
    assert bar.executable_buy_price_available is None


def test_normalized_daily_bar_default_state_fallback_d_close() -> None:
    """NormalizedDailyBar defaults → executable_buy_price_available=None, price=None → fallback D close."""
    bar = NormalizedDailyBar("600000.SH", date(2026, 1, 2), 10.0, 10.0, 10.2, 9.8, 100_000.0)
    assert bar.executable_buy_price_available is None
    assert bar.executable_buy_price is None


def test_normalized_daily_bar_available_false_buy_unavailable() -> None:
    """available=False → buy reference explicitly unavailable."""
    bar = NormalizedDailyBar("600000.SH", date(2026, 1, 2), 10.0, 10.0, 10.2, 9.8, 100_000.0,
                              executable_buy_price_available=False, executable_buy_price=None)
    assert bar.executable_buy_price_available is False
    assert bar.executable_buy_price is None


def test_normalized_daily_bar_available_true_price_12() -> None:
    """available=True, price=12 → valid buy reference."""
    bar = NormalizedDailyBar("600000.SH", date(2026, 1, 2), 10.0, 10.0, 10.2, 9.8, 100_000.0,
                              executable_buy_price_available=True, executable_buy_price=12.0)
    assert bar.executable_buy_price_available is True
    assert bar.executable_buy_price == 12.0


def test_normalized_daily_bar_available_true_zero_price_raises() -> None:
    """available=True with non-positive price → validation error."""
    with pytest.raises(ValueError, match="conflict"):
        NormalizedDailyBar("600000.SH", date(2026, 1, 2), 10.0, 10.0, 10.2, 9.8, 100_000.0,
                            executable_buy_price_available=True, executable_buy_price=0.0)


def test_normalized_daily_bar_available_false_with_price_raises() -> None:
    """available=False with a price → validation error."""
    with pytest.raises(ValueError, match="conflict"):
        NormalizedDailyBar("600000.SH", date(2026, 1, 2), 10.0, 10.0, 10.2, 9.8, 100_000.0,
                            executable_buy_price_available=False, executable_buy_price=12.0)


def test_buy_reference_dict_keys_absent_fallback_d_close() -> None:
    """Both keys absent → unspecified, fallback D close."""
    from quantpilot_core.daily_paper_loop.runner import _resolve_buy_reference_state
    state, price = _resolve_buy_reference_state({"close": 10.0})
    assert state == "unspecified"
    assert price is None


def test_buy_reference_dict_price_none_key_present_unavailable() -> None:
    """executable_buy_price=None key present → explicitly unavailable."""
    from quantpilot_core.daily_paper_loop.runner import _resolve_buy_reference_state
    state, price = _resolve_buy_reference_state({"close": 10.0, "executable_buy_price": None})
    assert state == "unavailable"
    assert price is None


def test_buy_reference_dict_positive_price_without_available_flag() -> None:
    """Positive price without available flag → available."""
    from quantpilot_core.daily_paper_loop.runner import _resolve_buy_reference_state
    state, price = _resolve_buy_reference_state({"close": 10.0, "executable_buy_price": 12.0})
    assert state == "available"
    assert price == 12.0


def test_buy_reference_dict_true_with_valid_price() -> None:
    """available=True + valid price → available."""
    from quantpilot_core.daily_paper_loop.runner import _resolve_buy_reference_state
    state, price = _resolve_buy_reference_state({"close": 10.0, "executable_buy_price_available": True, "executable_buy_price": 12.0})
    assert state == "available"
    assert price == 12.0


def test_buy_reference_dict_false_with_none() -> None:
    """available=False + None → explicitly unavailable."""
    from quantpilot_core.daily_paper_loop.runner import _resolve_buy_reference_state
    state, price = _resolve_buy_reference_state({"close": 10.0, "executable_buy_price_available": False, "executable_buy_price": None})
    assert state == "unavailable"
    assert price is None


def test_buy_reference_dict_true_with_none_raises() -> None:
    """available=True + None → ValueError."""
    from quantpilot_core.daily_paper_loop.runner import _resolve_buy_reference_state
    with pytest.raises(ValueError, match="True requires"):
        _resolve_buy_reference_state({"close": 10.0, "executable_buy_price_available": True, "executable_buy_price": None})


def test_buy_reference_dict_false_with_price_raises() -> None:
    """available=False + price → ValueError."""
    from quantpilot_core.daily_paper_loop.runner import _resolve_buy_reference_state
    with pytest.raises(ValueError, match="cannot have a price"):
        _resolve_buy_reference_state({"close": 10.0, "executable_buy_price_available": False, "executable_buy_price": 12.0})


def test_buy_reference_dict_invalid_available_type_raises() -> None:
    """Non-bool available → ValueError."""
    from quantpilot_core.daily_paper_loop.runner import _resolve_buy_reference_state
    with pytest.raises(ValueError, match="must be bool"):
        _resolve_buy_reference_state({"close": 10.0, "executable_buy_price_available": "yes", "executable_buy_price": 12.0})


def test_buy_reference_dict_non_positive_price_raises() -> None:
    """NaN/inf/non-positive price → ValueError."""
    from quantpilot_core.daily_paper_loop.runner import _resolve_buy_reference_state
    with pytest.raises(ValueError, match="positive"):
        _resolve_buy_reference_state({"close": 10.0, "executable_buy_price": 0.0})
    with pytest.raises(ValueError, match="positive"):
        _resolve_buy_reference_state({"close": 10.0, "executable_buy_price": -1.0})


def test_canonical_bar_row_uses_provider_value_not_str_enum() -> None:
    """NormalizedDailyBar(provider=ProviderName.TUSHARE) → canonical provider is 'tushare'."""
    bar = NormalizedDailyBar("600000.SH", date(2026, 1, 2), 10.0, 10.0, 10.2, 9.8, 100_000.0,
                              provider=ProviderName.TUSHARE)
    result = pipeline_module._canonical_bar_row(bar)
    assert result["provider"] == ProviderName.TUSHARE.value
    assert result["provider"] == "tushare"
    assert "ProviderName" not in result["provider"]


def test_normalized_daily_bar_object_flows_through_canonical_bar_row() -> None:
    """NormalizedDailyBar with available=False flows through _canonical_bar_row correctly."""
    bar = NormalizedDailyBar("600000.SH", date(2026, 1, 2), 10.0, 10.0, 10.2, 9.8, 100_000.0,
                              executable_buy_price_available=False, executable_buy_price=None)
    result = pipeline_module._canonical_bar_row(bar)
    assert result["symbol"] == "600000.SH"
    assert result["executable_buy_price_available"] is False
    assert result["executable_buy_price"] is None


def test_holding_missing_buy_reference_pipeline_e2e(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Real-pipeline E2E: holding A has D close (valuation) but executable_buy_price=None on
    NormalizedDailyBar, optimizer target > current → buy_increment_missing_price, standby B unused."""
    seed_holding(tmp_path, "600000.SH")

    def fake_report(*args, **kwargs):
        return SimpleNamespace(
            factor_scores=(factor_score("600000.SH", composite=0.9), factor_score("000001.SZ", composite=0.8)),
            selected_symbols=("600000.SH",),
            rejected_symbols_with_reasons=({"symbol": "000001.SZ", "reasons": ("not_selected_lower_rank",)},),
            ranking_mode="defensive_composite_v1",
        )

    monkeypatch.setattr("quantpilot_core.real_candidate_pipeline.pipeline.run_factor_ranking_baseline_v1", fake_report)

    # Use real NormalizedDailyBar objects with three-state contract: available=False → BUY prohibited.
    decision_date = date.fromisoformat("2026-04-03")
    raw_bars = []
    for bar in fixture_bars(("600000.SH", "000001.SZ")):
        bar_date = date.fromisoformat(str(bar["date"]))
        if bar["symbol"] == "600000.SH" and bar_date == decision_date:
            raw_bars.append(NormalizedDailyBar(
                symbol=bar["symbol"], trade_date=bar_date,
                open=bar["open"], high=bar["high"], low=bar["low"], close=bar["close"],
                volume=bar["volume"], amount=bar.get("amount"),
                previous_close=bar.get("previous_close"),
                is_st=bar.get("is_st"), provider=ProviderName.TUSHARE,
                executable_buy_price_available=False, executable_buy_price=None,
            ))
        else:
            raw_bars.append(NormalizedDailyBar(
                symbol=bar["symbol"], trade_date=bar_date,
                open=bar["open"], high=bar["high"], low=bar["low"], close=bar["close"],
                volume=bar["volume"], amount=bar.get("amount"),
                previous_close=bar.get("previous_close"),
                is_st=bar.get("is_st"), provider=ProviderName.TUSHARE,
            ))

    cfg = config(
        tmp_path,
        symbols=("600000.SH", "000001.SZ"),
        input_bars=tuple(raw_bars),
        target_symbol_count=1,
        max_execution_symbols=2,
        account_capabilities=AccountCapabilities(),
    )
    result = run_real_candidate_daily_paper(cfg)

    daily = result.combined_report["daily_paper_loop"]
    fd = daily["account_final_decision"]
    assert "600000.SH" in fd["final_account_decision_symbols"]
    assert list(fd["used_account_backfill_symbols"]) == []
    assert "000001.SZ" in fd["unused_standby_symbols"]
    assert "600000.SH" not in fd["account_excluded_original_symbols"]
    assert daily["fills"] == []
    sizing_a = next((row for row in daily["sizing_decisions"] if row["symbol"] == "600000.SH"), None)
    assert sizing_a is not None
    assert list(sizing_a["reason_codes"]) == ["buy_increment_missing_price"]
    assert sizing_a["optimizer_target_position_shares"] > sizing_a["current_position_shares"]


def test_target_symbol_count_becomes_daily_loop_target_position_count(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """target_symbol_count=1 → DailyPaperLoopConfig.target_position_count=1 (not default 10)."""
    def fake_report(*args, **kwargs):
        return SimpleNamespace(
            factor_scores=(factor_score("600000.SH", composite=0.9), factor_score("000001.SZ", composite=0.8)),
            selected_symbols=("600000.SH",),
            rejected_symbols_with_reasons=({"symbol": "000001.SZ", "reasons": ("not_selected_lower_rank",)},),
            ranking_mode="defensive_composite_v1",
        )

    monkeypatch.setattr("quantpilot_core.real_candidate_pipeline.pipeline.run_factor_ranking_baseline_v1", fake_report)
    result = run_real_candidate_daily_paper(
        config(tmp_path, symbols=("600000.SH", "000001.SZ"), target_symbol_count=1, max_execution_symbols=2)
    )

    daily = result.combined_report["daily_paper_loop"]
    sizing = daily["sizing_decisions"][0]
    policy = sizing["allocation_policy"]
    assert policy["configured_target_position_count"] == 1
    assert policy["effective_target_position_count"] == 1
    assert policy["configured_target_position_count"] != 10
