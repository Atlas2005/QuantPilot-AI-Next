"""Build real PIT factor candidates and pass them to the daily paper loop."""

from __future__ import annotations

import math
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timedelta
import re
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

import pandas as pd

from quantpilot_core.data_provider_normalization import canonicalize_a_share_symbol
from quantpilot_core.daily_paper_loop import (
    DailyPaperLoopConfig,
    DailyPaperLoopInput,
    DailyPaperLoopResult,
    DailyPaperLoopStatus,
    DailyPaperMarketBundle,
    load_daily_state,
    render_daily_paper_session_report,
    run_daily_paper_loop,
)
from quantpilot_core.daily_paper_loop.provider_market_input import load_provider_market_rows, validate_pit_safe_inputs
from quantpilot_core.daily_paper_loop.report import write_report_atomic
from quantpilot_core.daily_paper_loop.state import payload_digest
from quantpilot_core.evaluation import FactorRankingBaselineConfig, run_factor_ranking_baseline_v1
from quantpilot_core.execution_candidate import ExecutionCandidate, ExecutionCandidateReport
from quantpilot_core.real_candidate_pipeline.contracts import PipelineIdempotencyConflictError, RealCandidatePipelineConfig, RealCandidatePipelineResult
from quantpilot_core.real_data_provider import (
    ProviderName,
    TradingCalendar,
)

REAL_CANDIDATE_PIPELINE_SCHEMA_VERSION = 1
REAL_CANDIDATE_PIPELINE_VERSION = "real_candidate_daily_paper_v1"
REAL_CANDIDATE_STRATEGY_ID = "real-candidate-defensive-composite-v1"
EXPECTED_RETURN_SEMANTICS = "fixed_unscaled_sizing_prior_not_calibrated_return"
LONG_EXPECTED_RETURN_PRIOR = 0.03
EXIT_EXPECTED_RETURN_PRIOR = -0.03
EXECUTION_LIQUIDITY_NEUTRAL_FALLBACK = 0.5
EXECUTION_LIQUIDITY_SEMANTICS = "absolute_execution_suitability_neutral_fallback_for_factor_accepted_positive_volume"
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
DAILY_LOOP_VERSION = "daily_paper_loop_v1"


def build_real_candidate_daily_paper_input(
    config: RealCandidatePipelineConfig,
    *,
    calendar_provider: Any | None = None,
    bar_provider: Any | None = None,
) -> RealCandidatePipelineResult:
    decision = _validate_config(config)
    request_digest = _pipeline_request_digest(config, decision)
    state = load_daily_state(config.state_path, initial_capital=config.initial_capital)
    replay = _completed_pipeline_replay(state, config, decision, request_digest)
    if replay is not None:
        return replay
    holdings = tuple(symbol for symbol, quantity in sorted(state.execution_state.account.positions.items()) if int(quantity) > 0)
    normalized_holdings = _unique_symbols(holdings)
    if len(normalized_holdings) > int(config.max_execution_symbols):
        raise ValueError("holding symbols exceed max_execution_symbols")
    explicit_symbols = _unique_symbols(config.symbols)
    if config.live_market_data and not explicit_symbols:
        raise ValueError("--live-market-data requires an explicit bounded symbol universe")
    _validate_local_pit_inputs(config, decision)

    # Convert any NormalizedDailyBar objects in input_bars to canonical dicts
    # so downstream processing only deals with Mappings.
    input_bars = tuple(_canonical_bar_row(row) for row in config.input_bars) if config.input_bars else ()

    bars_universe = _unique_symbols(_bar_symbol(row) for row in input_bars)
    universe_origin = "explicit_symbols"
    raw_universe = _unique_symbols((*explicit_symbols, *normalized_holdings))
    if not raw_universe and bars_universe:
        raw_universe = bars_universe
        universe_origin = "input_bars"
    if not raw_universe:
        raw_universe = DEFAULT_OFFLINE_SYMBOLS
        universe_origin = "default_fixture"
    if config.live_market_data and len(raw_universe) > int(config.max_execution_symbols):
        raise ValueError("--live-market-data supports at most 6 explicit/holding symbols")

    if config.live_market_data:
        loaded_rows = load_provider_market_rows(
            decision_session=decision,
            calendar_start=decision - timedelta(days=140),
            calendar_end=decision + timedelta(days=10),
            symbols=raw_universe,
            bar_start_session=None,
            bar_start_session_offset=-60,
            calendar_provider=calendar_provider,
            bar_provider=bar_provider,
            max_symbol_cap=config.max_execution_symbols,
            cap_error_message="--live-market-data supports at most 6 explicit/holding symbols",
        )
        calendar = loaded_rows.calendar
        bars = loaded_rows.rows
        calendar_provenance = loaded_rows.calendar_provenance
        market_provenance = loaded_rows.market_data_provenance
    else:
        calendar = _input_calendar(config) if config.input_calendar_sessions else _offline_calendar(decision)
        bars = input_bars if input_bars else _offline_bars(calendar, raw_universe, decision)
        calendar_provenance = {
            "mode": "offline_fixture",
            "provider": calendar.provider.value,
            "sessions": calendar.to_iso_strings(),
        }
        market_provenance = {"mode": "offline_fixture", "network_calls": 0, "deepseek_live_call": False}

    if not calendar.is_session(decision):
        raise ValueError(f"decision_session is not in loaded trading calendar: {decision.isoformat()}")
    execution = calendar.next_session(decision)
    factor_start = calendar.shift_session(decision, -60)
    factor_sessions = calendar.sessions_between(factor_start, decision)
    if len(factor_sessions) != 61:
        raise ValueError("factor window must contain exactly 61 trading sessions through D")

    rows = _dedupe_price_rows(bars)
    _reject_rows_after_execution(rows, execution)
    excluded_bar_symbols = tuple(sorted({row["symbol"] for row in rows if row["symbol"] not in set(raw_universe)}))
    rows = tuple(row for row in rows if row["symbol"] in set(raw_universe))
    factor_rows = tuple(
        row
        for row in rows
        if factor_start <= date.fromisoformat(str(row["date"])) <= decision
    )
    factor_symbols = _unique_symbols(row["symbol"] for row in factor_rows)
    factor_frame = pd.DataFrame(factor_rows)
    factor_report = run_factor_ranking_baseline_v1(
        factor_frame,
        FactorRankingBaselineConfig(
            ranking_mode="defensive_composite_v1",
            target_symbol_count=max(1, int(config.target_symbol_count)),
            as_of_date=decision.isoformat(),
            artifact_path=None,
            metadata={
                "provider": market_provenance.get("provider_chain", market_provenance.get("mode", "in_memory")),
                "symbols_requested": raw_universe,
                "date_range": (factor_start.isoformat(), decision.isoformat()),
                "run_context": "manual_real_provider" if config.live_market_data else "fixture",
                "notes": ("pit_factor_window_61_sessions_through_decision",),
            },
        ),
    )

    decision_rows, execution_rows = _split_market_rows(rows, decision, execution)
    ranked_scores = _ranked_factor_scores(factor_report.factor_scores)
    score_by_symbol = {score.symbol: score for score in ranked_scores}
    rank_by_symbol = {score.symbol: index for index, score in enumerate(ranked_scores, start=1)}
    factor_selected_set = set(factor_report.selected_symbols)
    selected_symbols = tuple(score.symbol for score in ranked_scores if score.symbol in factor_selected_set)
    original_selected_symbols = selected_symbols
    rejected_by_symbol = _factor_rejections(factor_report.rejected_symbols_with_reasons)
    eligible_ranked_symbols = tuple(score.symbol for score in ranked_scores if not _hard_factor_rejection_reasons(rejected_by_symbol, score.symbol))
    forwarded_standby_symbols: tuple[str, ...] = ()
    if config.account_capabilities is not None:
        account_pool = _capacity_limited_account_pool(
            eligible_ranked_symbols=eligible_ranked_symbols,
            holdings=normalized_holdings,
            max_execution_symbols=int(config.max_execution_symbols),
        )
        forwarded_standby_symbols = tuple(symbol for symbol in account_pool if symbol not in factor_selected_set and symbol not in set(normalized_holdings))
        selected_symbols = account_pool
    candidates, candidate_events = _build_candidates(
        config=config,
        decision=decision,
        execution=execution,
        factor_start=factor_start,
        selected_symbols=selected_symbols,
        original_selected_symbols=original_selected_symbols,
        forwarded_standby_symbols=forwarded_standby_symbols,
        score_by_symbol=score_by_symbol,
        rank_by_symbol=rank_by_symbol,
        rejected_by_symbol=rejected_by_symbol,
        decision_rows=decision_rows,
        calendar=calendar,
        state_holdings=holdings,
        state=state,
    )
    candidate_events = _candidate_events_with_factor_rejections(candidate_events, rejected_by_symbol, score_by_symbol)
    execution_relevant_symbols = _unique_symbols((*holdings, *(candidate.symbol for candidate in candidates)))
    if len(execution_relevant_symbols) > int(config.max_execution_symbols):
        raise ValueError("candidate/holding symbols passed to daily paper loop exceed max_execution_symbols")

    loop_decision_rows = {symbol: decision_rows[symbol] for symbol in execution_relevant_symbols if symbol in decision_rows}
    loop_execution_rows = {symbol: execution_rows[symbol] for symbol in execution_relevant_symbols if symbol in execution_rows}
    report = ExecutionCandidateReport(
        candidates=candidates,
        aggregate_score=_aggregate_score(candidates),
        strategy_id=config.strategy_id or REAL_CANDIDATE_STRATEGY_ID,
    )
    loop_input = DailyPaperLoopInput(
        calendar=calendar,
        candidate_report=report,
        market=DailyPaperMarketBundle(
            decision_rows_by_symbol=loop_decision_rows,
            execution_rows_by_symbol=loop_execution_rows,
            market_data_provenance={
                **dict(market_provenance),
                "decision_session": decision.isoformat(),
                "execution_session": execution.isoformat(),
                "factor_rows_excluded_after_decision": sum(1 for row in rows if date.fromisoformat(str(row["date"])) > decision),
                "execution_relevant_symbol_count": len(execution_relevant_symbols),
                "max_execution_symbols": int(config.max_execution_symbols),
            },
        ),
        calendar_provenance=calendar_provenance,
        information_provenance=_information_provenance(config.information_provenance, decision),
        advisory_provenance={**dict(config.advisory_provenance), "deepseek_live_call": False},
        quant_firm_context={
            **dict(config.quant_firm_context),
            "requested_action": _requested_action(candidates),
            "requested_actions": _requested_actions(candidates),
            "information_signals": _information_signal_payloads(config.information_signals),
            "information_signal_provenance": {
                "source": "real_candidate_pipeline_input",
                "count": len(config.information_signals),
                "decision_cutoff": _decision_cutoff(decision),
            },
            "candidate_pipeline": {
                "pipeline_version": REAL_CANDIDATE_PIPELINE_VERSION,
                "strategy_id": config.strategy_id,
                "selected_symbols": original_selected_symbols,
                "original_selected_symbols": original_selected_symbols,
                "forwarded_standby_symbols": forwarded_standby_symbols,
                "forwarded_pool_count": len(selected_symbols),
                "target_symbol_count": int(config.target_symbol_count),
            },
        },
    )
    pipeline_report = _pipeline_report(
        config=config,
        request_digest=request_digest,
        decision=decision,
        execution=execution,
        factor_start=factor_start,
        factor_symbols=factor_symbols,
        raw_universe=raw_universe,
        holdings=normalized_holdings,
        supplied_symbols=config.symbols,
        universe_origin=universe_origin,
        excluded_bar_symbols=excluded_bar_symbols,
        selected_symbols=selected_symbols,
        original_selected_symbols=original_selected_symbols,
        forwarded_standby_symbols=forwarded_standby_symbols,
        factor_report=factor_report,
        score_by_symbol=score_by_symbol,
        rejected_by_symbol=rejected_by_symbol,
        candidate_events=candidate_events,
        candidates=candidates,
        execution_relevant_symbols=execution_relevant_symbols,
        calendar_provenance=calendar_provenance,
        market_provenance=loop_input.market.market_data_provenance,
        loop_input=loop_input,
    )
    loop_input = _with_pipeline_snapshot(loop_input, pipeline_report, request_digest)
    return RealCandidatePipelineResult(report, loop_input, pipeline_report)


def run_real_candidate_daily_paper(
    config: RealCandidatePipelineConfig,
    *,
    calendar_provider: Any | None = None,
    bar_provider: Any | None = None,
) -> RealCandidatePipelineResult:
    built = build_real_candidate_daily_paper_input(config, calendar_provider=calendar_provider, bar_provider=bar_provider)
    if built.daily_paper_loop_result is not None:
        if config.report_path is not None and built.combined_report is not None:
            write_report_atomic(built.combined_report, config.report_path)
        return built
    daily_config = _daily_loop_config(config, report_path=None)
    daily_result = run_daily_paper_loop(built.loop_input, daily_config)
    combined = {
        "schema_version": REAL_CANDIDATE_PIPELINE_SCHEMA_VERSION,
        "pipeline_version": REAL_CANDIDATE_PIPELINE_VERSION,
        "candidate_pipeline": built.candidate_pipeline_report,
        "daily_paper_loop": daily_result.report,
    }
    report_path = write_report_atomic(combined, config.report_path)
    if report_path is not None:
        daily_result = type(daily_result)(daily_result.status, daily_result.report, daily_result.state_path, report_path)
    return RealCandidatePipelineResult(
        built.candidate_report,
        built.loop_input,
        built.candidate_pipeline_report,
        daily_result,
        combined,
    )


DEFAULT_OFFLINE_SYMBOLS = ("600000.SH", "000001.SZ", "600519.SH")


def _offline_calendar(decision: date) -> TradingCalendar:
    sessions: list[date] = []
    cursor = decision - timedelta(days=100)
    while cursor <= decision + timedelta(days=10):
        if cursor.weekday() < 5:
            sessions.append(cursor)
        cursor += timedelta(days=1)
    if decision not in sessions:
        raise ValueError("offline fixture decision_session must be a weekday trading session")
    return TradingCalendar(tuple(sessions), ProviderName.BAOSTOCK)


def _input_calendar(config: RealCandidatePipelineConfig) -> TradingCalendar:
    """Build an offline calendar from immutable, caller-supplied sessions."""
    try:
        sessions = tuple(date.fromisoformat(value) for value in config.input_calendar_sessions)
    except (TypeError, ValueError) as exc:
        raise ValueError("input_calendar_sessions must contain ISO dates") from exc
    try:
        provider = ProviderName(config.input_calendar_provider)
    except ValueError as exc:
        raise ValueError("input_calendar_provider is required and must name a supported provider") from exc
    return TradingCalendar(sessions, provider)


def _offline_bars(calendar: TradingCalendar, symbols: tuple[str, ...], decision: date) -> tuple[Mapping[str, Any], ...]:
    factor_start = calendar.shift_session(decision, -60)
    execution = calendar.next_session(decision)
    sessions = calendar.sessions_between(factor_start, execution)
    rows: list[Mapping[str, Any]] = []
    for symbol_index, symbol in enumerate(symbols):
        base = 9.0 + symbol_index * 3.0
        for index, session in enumerate(sessions):
            drift = (len(symbols) - symbol_index) * 0.006
            wave = math.sin(index / 5.0 + symbol_index) * 0.03
            close = round(base * (1.0 + drift * index + wave), 4)
            previous = close if index == 0 else rows[-1]["close"] if rows and rows[-1]["symbol"] == symbol else close
            rows.append(
                {
                    "symbol": symbol,
                    "date": session.isoformat(),
                    "open": round(close * 0.995, 4),
                    "high": round(close * 1.015, 4),
                    "low": round(close * 0.985, 4),
                    "close": close,
                    "previous_close": previous,
                    "volume": float(120_000 + symbol_index * 25_000 + index * 100),
                    "amount": round(close * (120_000 + symbol_index * 25_000 + index * 100), 6),
                    "is_suspended": False,
                    "provider": "offline_fixture",
                }
            )
    return tuple(rows)


def _dedupe_price_rows(rows: Iterable[Mapping[str, Any]]) -> tuple[Mapping[str, Any], ...]:
    deduped: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in rows:
        payload = _canonical_bar_row(row)
        key = (str(payload["symbol"]), str(payload["date"]))
        if key in deduped and dict(deduped[key]) != dict(payload):
            raise ValueError(f"conflicting daily bar rows for {key[0]} on {key[1]}")
        deduped[key] = payload
    return tuple(deduped[key] for key in sorted(deduped, key=lambda item: (item[1], item[0])))


def _canonical_bar_row(row: Mapping[str, Any]) -> Mapping[str, Any]:
    # Support both Mapping (dict) and NormalizedDailyBar objects by converting
    # objects to a dict first. Only propagate executable_buy_price fields when
    # explicitly set (not default-unspecified).
    if not isinstance(row, Mapping):
        obj = row
        row_dict: dict[str, Any] = {
            "symbol": obj.symbol, "date": obj.trade_date, "trade_date": obj.trade_date,
            "open": obj.open, "high": obj.high, "low": obj.low, "close": obj.close,
            "previous_close": obj.previous_close, "volume": obj.volume, "amount": obj.amount,
            "is_suspended": getattr(obj, "is_suspended", False),
            "provider": _canonical_provider(obj),
        }
        ebp_avail = getattr(obj, "executable_buy_price_available", None)
        if ebp_avail is True:
            row_dict["executable_buy_price_available"] = True
            row_dict["executable_buy_price"] = float(getattr(obj, "executable_buy_price", 0.0))
        elif ebp_avail is False:
            row_dict["executable_buy_price_available"] = False
            row_dict["executable_buy_price"] = None
        # else unspecified → don't add the fields
        row = row_dict
    trade_date = row.get("date", row.get("trade_date"))
    if trade_date is None:
        raise ValueError("daily bar row missing date")
    trade_date = trade_date.isoformat() if isinstance(trade_date, date) else str(trade_date)
    result: dict[str, Any] = {
        "symbol": _normalize_symbol(row["symbol"]),
        "date": date.fromisoformat(trade_date).isoformat(),
        "open": _positive_float(row.get("open"), "open"),
        "high": _positive_float(row.get("high"), "high"),
        "low": _positive_float(row.get("low"), "low"),
        "close": _positive_float(row.get("close"), "close"),
        "previous_close": None if row.get("previous_close") is None else float(row["previous_close"]),
        "volume": float(row.get("volume", 0.0)),
        "amount": float(_bar_amount(row)),
        "is_suspended": bool(row.get("is_suspended", False)),
        "provider": str(row.get("provider", "input")),
    }
    if "executable_buy_price" in row:
        result["executable_buy_price"] = row["executable_buy_price"]
    if "executable_buy_price_available" in row:
        result["executable_buy_price_available"] = row["executable_buy_price_available"]
    return result


def _bar_amount(row: Mapping[str, Any]) -> float:
    amt = row.get("amount")
    if amt is not None:
        return float(amt)
    return float(float(row.get("close", 0.0)) * float(row.get("volume", 0.0)))


def _canonical_provider(obj: Any) -> str:
    """Extract provider string from a NormalizedDailyBar-like object."""
    from quantpilot_core.real_data_provider import ProviderName
    provider = getattr(obj, "provider", "input")
    if isinstance(provider, ProviderName):
        return provider.value
    return str(provider)


def _positive_float(value: Any, field_name: str) -> float:
    number = float(value)
    if number <= 0 or not math.isfinite(number):
        raise ValueError(f"{field_name} must be positive and finite")
    return number


def _reject_rows_after_execution(rows: tuple[Mapping[str, Any], ...], execution: date) -> None:
    future = tuple(row for row in rows if date.fromisoformat(str(row["date"])) > execution)
    if future:
        first = future[0]
        raise ValueError(f"daily bar row after execution session is not PIT-safe: {first['symbol']} {first['date']}")


def _split_market_rows(
    rows: tuple[Mapping[str, Any], ...],
    decision: date,
    execution: date,
) -> tuple[dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]]]:
    decision_rows: dict[str, Mapping[str, Any]] = {}
    execution_rows: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        trade_date = date.fromisoformat(str(row["date"]))
        if trade_date == decision:
            decision_rows[str(row["symbol"])] = row
        elif trade_date == execution:
            execution_rows[str(row["symbol"])] = row
    return decision_rows, execution_rows


def _build_candidates(
    *,
    config: RealCandidatePipelineConfig,
    decision: date,
    execution: date,
    factor_start: date,
    selected_symbols: tuple[str, ...],
    original_selected_symbols: tuple[str, ...],
    forwarded_standby_symbols: tuple[str, ...],
    score_by_symbol: Mapping[str, Any],
    rank_by_symbol: Mapping[str, int],
    rejected_by_symbol: Mapping[str, tuple[str, ...]],
    decision_rows: Mapping[str, Mapping[str, Any]],
    calendar: TradingCalendar,
    state_holdings: tuple[str, ...],
    state: Any,
) -> tuple[tuple[ExecutionCandidate, ...], Mapping[str, Any]]:
    original_selected_set = set(original_selected_symbols)
    forwarded_standby_set = set(forwarded_standby_symbols)
    selected_set = set(selected_symbols)
    holding_set = set(state_holdings)
    candidates: list[ExecutionCandidate] = []
    events: dict[str, Any] = {"entries": [], "exits": [], "holds": [], "rejected": []}
    timestamp = datetime(decision.year, decision.month, decision.day, 15, 0, tzinfo=SHANGHAI_TZ)

    account_aware = config.account_capabilities is not None
    available_entry_slots = max(0, int(config.max_execution_symbols) - len(holding_set))
    for symbol in selected_symbols:
        if symbol in holding_set:
            if account_aware:
                # existing selected holding — visible candidate, occupies its slot
                # but does NOT consume an entry slot
                score = score_by_symbol.get(symbol)
                pipeline_role = "original_selected_holding"
                candidates.append(
                    _candidate(
                        symbol=symbol,
                        direction="long",
                        timestamp=timestamp,
                        expected_return=LONG_EXPECTED_RETURN_PRIOR,
                        score=score,
                        metadata={
                            **_candidate_metadata(
                                config=config,
                                decision=decision,
                                execution=execution,
                                factor_start=factor_start,
                                symbol=symbol,
                                direction="long",
                                score=score,
                                factor_rank=rank_by_symbol.get(symbol),
                                decision_row=decision_rows.get(symbol, {}),
                                calendar=calendar,
                                state=state,
                            ),
                            "pipeline_role": pipeline_role,
                        },
                    )
                )
                events["holds"].append({"symbol": symbol, "reason": "holding_selected_no_duplicate_entry", "pipeline_role": pipeline_role})
            else:
                events["holds"].append({"symbol": symbol, "reason": "holding_selected_no_duplicate_entry"})
            continue
        # entry candidates count against available slots (holdings don't)
        entry_candidates_in_loop = [item for item in candidates if item.direction == "long" and dict(item.metadata).get("pipeline_role") != "original_selected_holding"]
        if len(entry_candidates_in_loop) >= available_entry_slots:
            events["rejected"].append({"symbol": symbol, "reason": "max_execution_symbol_cap"})
            continue
        score = score_by_symbol.get(symbol)
        valid, reason = _valid_factor_and_market_evidence(symbol, score, rejected_by_symbol, decision_rows)
        if not valid:
            events["rejected"].append({"symbol": symbol, "reason": reason})
            continue
        if symbol in forwarded_standby_set:
            pipeline_role = "forwarded_standby"
        elif symbol in original_selected_set:
            pipeline_role = "original_selected_entry"
        else:
            pipeline_role = "original_selected_entry"
        candidates.append(
            _candidate(
                symbol=symbol,
                direction="long",
                timestamp=timestamp,
                expected_return=LONG_EXPECTED_RETURN_PRIOR,
                score=score,
                metadata={
                    **_candidate_metadata(
                        config=config,
                        decision=decision,
                        execution=execution,
                        factor_start=factor_start,
                        symbol=symbol,
                        direction="long",
                        score=score,
                        factor_rank=rank_by_symbol.get(symbol),
                        decision_row=decision_rows[symbol],
                        calendar=calendar,
                        state=state,
                    ),
                    "pipeline_role": pipeline_role,
                },
            )
        )
        events["entries"].append({"symbol": symbol, "reason": "selected_factor_candidate", "pipeline_role": pipeline_role})

    for symbol in state_holdings:
        score = score_by_symbol.get(symbol)
        valid, reason = _valid_factor_and_market_evidence(symbol, score, rejected_by_symbol, decision_rows)
        if not valid:
            events["holds"].append({"symbol": symbol, "reason": f"hold_no_decision_{reason}"})
            continue
        if symbol in selected_set:
            if not any(item["symbol"] == symbol for item in events["holds"]):
                events["holds"].append({"symbol": symbol, "reason": "holding_selected_no_exit", "pipeline_role": "original_selected_holding"})
            continue
        candidates.append(
            _candidate(
                symbol=symbol,
                direction="short",
                timestamp=timestamp,
                expected_return=EXIT_EXPECTED_RETURN_PRIOR,
                score=score,
                metadata={
                    **_candidate_metadata(
                        config=config,
                        decision=decision,
                        execution=execution,
                        factor_start=factor_start,
                        symbol=symbol,
                        direction="short",
                        score=score,
                        factor_rank=rank_by_symbol.get(symbol),
                        decision_row=decision_rows[symbol],
                        calendar=calendar,
                        state=state,
                    ),
                    "action": "exit",
                    "exit_signal": True,
                    "exit_reason": "rank_dropout",
                    "pipeline_role": "sell_exit",
                },
            )
        )
        events["exits"].append({"symbol": symbol, "reason": "rank_dropout", "pipeline_role": "sell_exit"})
    return tuple(candidates), events


def _candidate(
    *,
    symbol: str,
    direction: str,
    timestamp: datetime,
    expected_return: float,
    score: Any,
    metadata: Mapping[str, Any],
) -> ExecutionCandidate:
    composite = _composite_score(score)
    return ExecutionCandidate(
        symbol=symbol,
        direction=direction,
        confidence=composite,
        expected_return=expected_return,
        risk_score=round(max(0.0, min(1.0, 1.0 - composite)), 6),
        liquidity_score=float(metadata["execution_liquidity_score"]),
        timestamp=timestamp,
        lot_size=100,
        metadata=metadata,
    )


def _candidate_metadata(
    *,
    config: RealCandidatePipelineConfig,
    decision: date,
    execution: date,
    factor_start: date,
    symbol: str,
    direction: str,
    score: Any,
    factor_rank: int | None,
    decision_row: Mapping[str, Any],
    calendar: TradingCalendar,
    state: Any,
) -> Mapping[str, Any]:
    acquisition_dates = tuple(
        lot.acquisition_date
        for lot in state.execution_state.settlement_lots
        if lot.symbol == symbol and int(lot.quantity) > 0
    )
    base = {
        "strategy_id": config.strategy_id,
        "source": REAL_CANDIDATE_PIPELINE_VERSION,
        "expected_return_semantics": EXPECTED_RETURN_SEMANTICS,
        "factor_model": "defensive_composite_v1",
        "factor_window_start": factor_start.isoformat(),
        "factor_window_end": decision.isoformat(),
        "pit_cutoff": f"{decision.isoformat()}T15:00:00+08:00",
        "execution_session": execution.isoformat(),
        "direction": direction,
        "factor_rank": factor_rank,
        "factor_composite_score": _composite_score(score),
        "factor_evidence": _json_ready(score.factor_evidence),
        **_execution_liquidity_metadata(score, decision_row),
        "d_close": float(decision_row["close"]),
        "d_volume": float(decision_row.get("volume", 0.0)),
        "provider": decision_row.get("provider"),
        "current_quantity": int(state.execution_state.account.positions.get(symbol, 0)),
        "average_cost": float(state.execution_state.account.average_costs.get(symbol, 0.0)),
        "acquisition_dates": acquisition_dates,
        **_holding_period_metadata(acquisition_dates, decision, calendar),
    }
    digest = payload_digest(base)
    return {
        **base,
        "candidate_id": f"{config.strategy_id}:{decision.isoformat()}:{symbol}:{direction}:{digest[:16]}",
        "input_digest": digest,
    }


def _valid_factor_and_market_evidence(
    symbol: str,
    score: Any | None,
    rejected_by_symbol: Mapping[str, tuple[str, ...]],
    decision_rows: Mapping[str, Mapping[str, Any]],
) -> tuple[bool, str]:
    if score is None:
        return False, "missing_factor_evidence"
    if score.factor_evidence.get("missing_factors"):
        return False, "insufficient_factor_evidence"
    if not _finite_factor_score(score):
        return False, "invalid_factor_evidence"
    canonical_rejections = tuple(reason for reason in rejected_by_symbol.get(symbol, ()) if reason != "not_selected_lower_rank")
    if canonical_rejections:
        return False, "factor_rejected"
    row = decision_rows.get(symbol)
    if row is None:
        return False, "missing_d_market_evidence"
    if bool(row.get("is_suspended", False)):
        return False, "invalid_d_market_evidence_suspended"
    _, volume_reason = _d_volume_evidence(row)
    if volume_reason is not None:
        return False, volume_reason
    if float(row.get("close", 0.0)) <= 0:
        return False, "invalid_d_market_evidence_close"
    return True, "valid"


def _factor_rejections(rows: Iterable[Mapping[str, Any]]) -> Mapping[str, tuple[str, ...]]:
    return {str(row["symbol"]): tuple(str(reason) for reason in row.get("reasons", ())) for row in rows}


def _hard_factor_rejection_reasons(rejected_by_symbol: Mapping[str, tuple[str, ...]], symbol: str) -> tuple[str, ...]:
    return tuple(reason for reason in rejected_by_symbol.get(symbol, ()) if reason != "not_selected_lower_rank")


def _capacity_limited_account_pool(
    *,
    eligible_ranked_symbols: tuple[str, ...],
    holdings: tuple[str, ...],
    max_execution_symbols: int,
) -> tuple[str, ...]:
    holding_set = set(holdings)
    if len(holding_set) > int(max_execution_symbols):
        raise ValueError("holding symbols exceed max_execution_symbols")
    remaining_new_slots = max(0, int(max_execution_symbols) - len(holding_set))
    pool: list[str] = []
    used: set[str] = set()
    admitted_new_symbols = 0
    for symbol in eligible_ranked_symbols:
        if symbol in used:
            continue
        if symbol not in holding_set:
            if admitted_new_symbols >= remaining_new_slots:
                continue
            admitted_new_symbols += 1
        pool.append(symbol)
        used.add(symbol)
    return tuple(pool)


def _candidate_events_with_factor_rejections(
    candidate_events: Mapping[str, Any],
    rejected_by_symbol: Mapping[str, tuple[str, ...]],
    score_by_symbol: Mapping[str, Any],
) -> Mapping[str, Any]:
    events = {key: list(value) for key, value in dict(candidate_events).items()}
    rejected_events = events.setdefault("rejected", [])
    already_reported = {str(event.get("symbol")) for event in rejected_events if isinstance(event, Mapping)}
    for symbol in score_by_symbol:
        if symbol in already_reported:
            continue
        hard_reasons = _hard_factor_rejection_reasons(rejected_by_symbol, symbol)
        if hard_reasons:
            rejected_events.append({"symbol": symbol, "reason": "factor_rejected", "factor_rejection_reasons": hard_reasons})
    return events


def _ranked_factor_scores(scores: Iterable[Any]) -> tuple[Any, ...]:
    return tuple(sorted(scores, key=lambda score: (-_composite_score(score), str(score.symbol))))


def _finite_factor_score(score: Any) -> bool:
    values = (
        score.composite_score,
        score.volatility_20d,
        score.volatility_60d,
        score.momentum_20d,
        score.momentum_60d,
        score.drawdown_20d,
        score.drawdown_60d,
    )
    for value in values:
        if value is None:
            return False
        try:
            if not math.isfinite(float(value)):
                return False
        except (TypeError, ValueError):
            return False
    return _finite_nested(score.factor_evidence)


def _finite_nested(value: Any) -> bool:
    if isinstance(value, Mapping):
        return all(_finite_nested(item) for item in value.values())
    if isinstance(value, (tuple, list)):
        return all(_finite_nested(item) for item in value)
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return True
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    return True


def _composite_score(score: Any) -> float:
    return round(max(0.0, min(1.0, float(score.composite_score))), 6)


def _factor_normalized_liquidity(score: Any) -> float | None:
    value = score.factor_evidence.get("normalized_factors", {}).get("liquidity_proxy")
    if value is None:
        return None
    return round(max(0.0, min(1.0, float(value))), 6)


def _raw_liquidity_proxy(score: Any) -> float | None:
    value = getattr(score, "liquidity_proxy", None)
    if value is None:
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return number


def _d_volume_evidence(row: Mapping[str, Any]) -> tuple[float, str | None]:
    volume = float(row.get("volume", 0.0))
    if not math.isfinite(volume):
        return volume, "invalid_d_market_evidence_nonfinite_volume"
    if volume <= 0:
        return volume, "invalid_d_market_evidence_zero_volume"
    return volume, None


def _execution_liquidity_metadata(score: Any, decision_row: Mapping[str, Any]) -> Mapping[str, Any]:
    _, volume_reason = _d_volume_evidence(decision_row)
    if bool(decision_row.get("is_suspended", False)) or volume_reason is not None or float(decision_row.get("close", 0.0)) <= 0:
        execution_score = 0.0
        neutral_fallback_used = False
    else:
        execution_score = EXECUTION_LIQUIDITY_NEUTRAL_FALLBACK
        neutral_fallback_used = True
    return {
        "factor_normalized_liquidity": _factor_normalized_liquidity(score),
        "raw_liquidity_proxy": _raw_liquidity_proxy(score),
        "execution_liquidity_score": execution_score,
        "execution_liquidity_semantics": EXECUTION_LIQUIDITY_SEMANTICS,
        "execution_liquidity_neutral_fallback_used": neutral_fallback_used,
    }


def _holding_period_metadata(acquisition_dates: tuple[str, ...], decision: date, calendar: TradingCalendar) -> Mapping[str, Any]:
    if not acquisition_dates:
        return {"holding_period_sessions": None, "holding_period_status": "not_applicable_no_holding"}
    starts = []
    for value in acquisition_dates:
        try:
            starts.append(date.fromisoformat(value))
        except ValueError:
            return {"holding_period_sessions": None, "holding_period_status": "unavailable_invalid_acquisition_date"}
    earliest = min(starts)
    if not calendar.is_session(earliest):
        return {"holding_period_sessions": None, "holding_period_status": "unavailable_acquisition_date_not_loaded_session"}
    if not calendar.is_session(decision):
        return {"holding_period_sessions": None, "holding_period_status": "unavailable_decision_date_not_loaded_session"}
    return {
        "holding_period_sessions": len(calendar.sessions_between(earliest, decision)),
        "holding_period_status": "available",
    }


def _aggregate_score(candidates: tuple[ExecutionCandidate, ...]) -> float:
    if not candidates:
        return 0.0
    return round(sum(float(candidate.confidence) for candidate in candidates) / len(candidates), 6)


def _requested_action(candidates: tuple[ExecutionCandidate, ...]) -> str:
    directions = {candidate.direction for candidate in candidates}
    if {"long", "short"}.issubset(directions):
        return "mixed"
    if "short" in directions:
        return "exit"
    if "long" in directions:
        return "buy"
    return "hold"


def _requested_actions(candidates: tuple[ExecutionCandidate, ...]) -> tuple[str, ...]:
    actions: list[str] = []
    if any(candidate.direction == "long" for candidate in candidates):
        actions.append("buy")
    if any(candidate.direction == "short" for candidate in candidates):
        actions.append("exit")
    return tuple(actions or ["hold"])


def _pipeline_report(
    *,
    config: RealCandidatePipelineConfig,
    request_digest: str,
    decision: date,
    execution: date,
    factor_start: date,
    factor_symbols: tuple[str, ...],
    raw_universe: tuple[str, ...],
    holdings: tuple[str, ...],
    supplied_symbols: tuple[str, ...],
    universe_origin: str,
    excluded_bar_symbols: tuple[str, ...],
    selected_symbols: tuple[str, ...],
    original_selected_symbols: tuple[str, ...],
    forwarded_standby_symbols: tuple[str, ...],
    factor_report: Any,
    score_by_symbol: Mapping[str, Any],
    rejected_by_symbol: Mapping[str, tuple[str, ...]],
    candidate_events: Mapping[str, Any],
    candidates: tuple[ExecutionCandidate, ...],
    execution_relevant_symbols: tuple[str, ...],
    calendar_provenance: Mapping[str, Any],
    market_provenance: Mapping[str, Any],
    loop_input: DailyPaperLoopInput,
) -> Mapping[str, Any]:
    return {
        "schema_version": REAL_CANDIDATE_PIPELINE_SCHEMA_VERSION,
        "pipeline_version": REAL_CANDIDATE_PIPELINE_VERSION,
        "pipeline_request_digest": request_digest,
        "strategy_id": config.strategy_id,
        "sessions": {"decision": decision.isoformat(), "execution": execution.isoformat()},
        "cutoff": f"{decision.isoformat()}T15:00:00+08:00",
        "factor_window": {
            "start": factor_start.isoformat(),
            "end": decision.isoformat(),
            "trading_session_count": 61,
            "d_plus_1_excluded_from_factor_calculation": True,
        },
        "universe": {
            "origin": universe_origin,
            "supplied": supplied_symbols,
            "normalized_explicit": _unique_symbols(supplied_symbols),
            "holding": holdings,
            "resolved": raw_universe,
            "excluded": excluded_bar_symbols,
            "factor_symbols": factor_symbols,
        },
        "holdings": holdings,
        "eligible_symbols": tuple(score_by_symbol),
        "rejected": rejected_by_symbol,
        "selected_symbols": original_selected_symbols,
        "original_selected_symbols": original_selected_symbols,
        "forwarded_standby_symbols": forwarded_standby_symbols,
        "forwarded_pool_count": len(selected_symbols),
        "account_candidate_pool_symbols": selected_symbols,
        "evidence": {
            symbol: {
                "factor_rank": index,
                "composite_score": _composite_score(score),
                "factor_evidence": _json_ready(score.factor_evidence),
            }
            for index, (symbol, score) in enumerate(score_by_symbol.items(), start=1)
        },
        "candidates": _candidate_report_payload(ExecutionCandidateReport(candidates, _aggregate_score(candidates), config.strategy_id)),
        "candidate_events": _json_ready(candidate_events),
        "no_candidate": {"active": not candidates, "reason": "no_entry_or_exit_after_pit_filters" if not candidates else None},
        "execution_relevant_symbols": execution_relevant_symbols,
        "provenance": {"calendar": calendar_provenance, "market": market_provenance},
        "digests": {
            "pipeline_request": request_digest,
            "loop_input": payload_digest(_loop_input_payload(loop_input)),
            "factor_report": payload_digest(_json_ready(factor_report)),
        },
        "limitations": (
            "expected_return_is_fixed_unscaled_sizing_prior_not_calibrated_return",
            "deepseek_live_disabled",
            "broker_live_disabled",
            "no_event_study_labels",
        ),
    }


def _candidate_report_payload(report: ExecutionCandidateReport) -> Mapping[str, Any]:
    return {
        "strategy_id": report.strategy_id,
        "aggregate_score": report.aggregate_score,
        "candidates": tuple(
            {
                "symbol": candidate.symbol,
                "direction": candidate.direction,
                "confidence": candidate.confidence,
                "expected_return": candidate.expected_return,
                "risk_score": candidate.risk_score,
                "liquidity_score": candidate.liquidity_score,
                "timestamp": candidate.timestamp.isoformat(),
                "lot_size": candidate.lot_size,
                "metadata": _json_ready(candidate.metadata),
            }
            for candidate in report.candidates
        ),
    }


def _loop_input_payload(loop_input: DailyPaperLoopInput) -> Mapping[str, Any]:
    return {
        "calendar": loop_input.calendar.to_iso_strings(),
        "candidate_report": _candidate_report_payload(loop_input.candidate_report),
        "market": {
            "decision_rows_by_symbol": _json_ready(loop_input.market.decision_rows_by_symbol),
            "execution_rows_by_symbol": _json_ready(loop_input.market.execution_rows_by_symbol),
            "market_data_provenance": _json_ready(loop_input.market.market_data_provenance),
        },
        "calendar_provenance": _json_ready(loop_input.calendar_provenance),
        "information_provenance": _json_ready(loop_input.information_provenance),
        "advisory_provenance": _json_ready(loop_input.advisory_provenance),
        "quant_firm_context": _json_ready(loop_input.quant_firm_context),
    }


def _information_provenance(provenance: Mapping[str, Any], decision: date) -> Mapping[str, Any]:
    cutoff = _decision_cutoff(decision)
    payload = dict(provenance)
    return {"mode": "none" if not provenance else "input_json", **payload, "decision_cutoff": cutoff}


def _with_pipeline_snapshot(
    loop_input: DailyPaperLoopInput,
    pipeline_report: Mapping[str, Any],
    request_digest: str,
) -> DailyPaperLoopInput:
    snapshot = {
        "schema_version": REAL_CANDIDATE_PIPELINE_SCHEMA_VERSION,
        "pipeline_version": REAL_CANDIDATE_PIPELINE_VERSION,
        "pipeline_request_digest": request_digest,
        "candidate_pipeline_report": pipeline_report,
    }
    return DailyPaperLoopInput(
        calendar=loop_input.calendar,
        candidate_report=loop_input.candidate_report,
        market=loop_input.market,
        calendar_provenance=loop_input.calendar_provenance,
        information_provenance={**dict(loop_input.information_provenance), "candidate_pipeline_snapshot": snapshot},
        advisory_provenance=loop_input.advisory_provenance,
        quant_firm_context=loop_input.quant_firm_context,
    )


def _completed_pipeline_replay(
    state: Any,
    config: RealCandidatePipelineConfig,
    decision: date,
    request_digest: str,
) -> RealCandidatePipelineResult | None:
    prefix = f"{DAILY_LOOP_VERSION}:{config.strategy_id}:{decision.isoformat()}:"
    matches = [
        dict(record)
        for session_id, record in state.applied_sessions.items()
        if str(session_id).startswith(prefix)
        and str(record.get("decision_session")) == decision.isoformat()
    ]
    if not matches:
        return None
    record = sorted(matches, key=lambda row: str(row.get("execution_session", "")))[0]
    snapshot = dict(dict(record.get("information_provenance", {})).get("candidate_pipeline_snapshot", {}) or {})
    stored_digest = snapshot.get("pipeline_request_digest")
    if stored_digest != request_digest:
        raise PipelineIdempotencyConflictError(f"pipeline session already applied with different request digest: {record.get('session_id')}")
    pipeline_report = _tuple_ready(dict(snapshot.get("candidate_pipeline_report", {}) or {}))
    candidate_report = _candidate_report_from_payload(record.get("candidate_report", {}))
    loop_input = DailyPaperLoopInput(
        calendar=TradingCalendar(tuple(date.fromisoformat(value) for value in record.get("calendar_provenance", {}).get("sessions", (decision.isoformat(), record["execution_session"]))), ProviderName.BAOSTOCK),
        candidate_report=candidate_report,
        market=DailyPaperMarketBundle(decision_rows_by_symbol={}, execution_rows_by_symbol={}, market_data_provenance=dict(record.get("market_data_provenance", {}))),
        calendar_provenance=dict(record.get("calendar_provenance", {})),
        information_provenance=dict(record.get("information_provenance", {})),
        advisory_provenance=dict(record.get("advisory_provenance", {})),
        quant_firm_context={},
    )
    daily_report = render_daily_paper_session_report(
        session_record=record,
        state=state,
        config=_daily_loop_config(config, report_path=config.report_path),
        status=DailyPaperLoopStatus.IDEMPOTENT_REPLAY.value,
    )
    combined = {
        "schema_version": REAL_CANDIDATE_PIPELINE_SCHEMA_VERSION,
        "pipeline_version": REAL_CANDIDATE_PIPELINE_VERSION,
        "candidate_pipeline": pipeline_report,
        "daily_paper_loop": daily_report,
    }
    daily_result = DailyPaperLoopResult(DailyPaperLoopStatus.IDEMPOTENT_REPLAY, daily_report, str(config.state_path), str(config.report_path) if config.report_path is not None else None)
    return RealCandidatePipelineResult(candidate_report, loop_input, pipeline_report, daily_result, combined)


def _candidate_report_from_payload(payload: Any) -> ExecutionCandidateReport:
    row = dict(payload or {})
    return ExecutionCandidateReport(
        candidates=tuple(_candidate_from_payload(item) for item in row.get("candidates", ())),
        aggregate_score=float(row.get("aggregate_score", 0.0)),
        strategy_id=str(row.get("strategy_id", REAL_CANDIDATE_STRATEGY_ID)),
    )


def _tuple_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _tuple_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return tuple(_tuple_ready(item) for item in value)
    return value


def _candidate_from_payload(row: Mapping[str, Any]) -> ExecutionCandidate:
    return ExecutionCandidate(
        symbol=str(row["symbol"]),
        direction=str(row["direction"]),
        confidence=float(row["confidence"]),
        expected_return=float(row["expected_return"]),
        risk_score=float(row["risk_score"]),
        liquidity_score=float(row["liquidity_score"]),
        timestamp=datetime.fromisoformat(str(row["timestamp"])),
        lot_size=int(row.get("lot_size", 100)),
        metadata=dict(row.get("metadata", {})),
    )


def _pipeline_request_digest(config: RealCandidatePipelineConfig, decision: date) -> str:
    return payload_digest(_canonical_request_payload(config, decision))


def _canonical_request_payload(config: RealCandidatePipelineConfig, decision: date) -> Mapping[str, Any]:
    payload = {
        "pipeline_version": REAL_CANDIDATE_PIPELINE_VERSION,
        "decision_session": decision.isoformat(),
        "strategy_id": config.strategy_id.strip(),
        "initial_capital": round(float(config.initial_capital), 6),
        "symbols": tuple(sorted(_unique_symbols(config.symbols))),
        "max_execution_symbols": int(config.max_execution_symbols),
        "target_symbol_count": int(config.target_symbol_count),
        "live_market_data": bool(config.live_market_data),
        "input_bars": _canonical_request_bars(config.input_bars),
        "input_calendar_sessions": tuple(config.input_calendar_sessions),
        "input_calendar_provider": config.input_calendar_provider,
        "information_signals": _canonical_information_signals(config.information_signals),
        "information_provenance": _json_ready(config.information_provenance),
        "advisory_provenance": _json_ready(config.advisory_provenance),
        "quant_firm_context": _json_ready(config.quant_firm_context),
    }
    if config.account_capabilities is not None:
        payload["account_capabilities"] = _json_ready(config.account_capabilities)
    return payload


def _canonical_request_bars(rows: Iterable[Mapping[str, Any]]) -> tuple[Mapping[str, Any], ...]:
    return tuple(_request_bar_payload(row) for row in _dedupe_price_rows(rows))


def _request_bar_payload(row: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "symbol": row["symbol"],
        "date": row["date"],
        "open": row["open"],
        "high": row["high"],
        "low": row["low"],
        "close": row["close"],
        "previous_close": row.get("previous_close"),
        "volume": row["volume"],
        "amount": row["amount"],
        "is_suspended": row["is_suspended"],
    }


def _canonical_information_signals(signals: tuple[Any, ...]) -> tuple[Any, ...]:
    ready = tuple(_json_ready(signal) for signal in signals)
    identities: list[str] = []
    for signal in ready:
        if not isinstance(signal, Mapping):
            return ready
        identity = signal.get("source_event_id") or signal.get("signal_id") or signal.get("id")
        if not identity:
            return ready
        identities.append(str(identity))
    return tuple(row for _, row in sorted(zip(identities, ready), key=lambda item: item[0]))


def _daily_loop_config(config: RealCandidatePipelineConfig, *, report_path: str | Path | None) -> DailyPaperLoopConfig:
    return DailyPaperLoopConfig(
        decision_session=config.decision_session,
        initial_capital=config.initial_capital,
        strategy_id=config.strategy_id,
        state_path=config.state_path,
        report_path=report_path,
        live_market_data=config.live_market_data,
        live_symbol_cap=config.max_execution_symbols,
        target_position_count=int(config.target_symbol_count),
        account_capabilities=config.account_capabilities,
    )


def _validate_config(config: RealCandidatePipelineConfig) -> date:
    try:
        decision = date.fromisoformat(str(config.decision_session))
    except ValueError as exc:
        raise ValueError("decision_session must use YYYY-MM-DD") from exc
    if not math.isfinite(float(config.initial_capital)) or float(config.initial_capital) <= 0:
        raise ValueError("initial_capital must be positive and finite")
    if not 1 <= int(config.max_execution_symbols) <= 6:
        raise ValueError("max_execution_symbols must be between 1 and 6")
    if not 1 <= int(config.target_symbol_count) <= int(config.max_execution_symbols):
        raise ValueError("target_symbol_count must be between 1 and max_execution_symbols")
    if not str(config.strategy_id).strip():
        raise ValueError("strategy_id must be non-empty")
    _unique_symbols(config.symbols)
    if config.input_calendar_sessions:
        _input_calendar(config)
    if config.live_market_data and not config.symbols:
        raise ValueError("live mode requires an explicit symbol universe")
    return decision


def _validate_local_pit_inputs(config: RealCandidatePipelineConfig, decision: date) -> None:
    _validate_information_signal_envelopes(config.information_signals)
    validate_pit_safe_inputs(
        {
            "information_provenance": config.information_provenance,
            "advisory_provenance": config.advisory_provenance,
            "quant_firm_context": config.quant_firm_context,
            "information_signals": config.information_signals,
        },
        decision,
    )


def _decision_cutoff(decision: date) -> str:
    return f"{decision.isoformat()}T15:00:00+08:00"


def _information_signal_payloads(signals: tuple[Any, ...]) -> tuple[Any, ...]:
    return tuple(_json_ready(signal) for signal in signals)


def _unique_symbols(symbols: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(_normalize_symbol(symbol) for symbol in symbols if str(symbol).strip()))


def _normalize_symbol(symbol: Any) -> str:
    normalized = canonicalize_a_share_symbol(symbol)
    if not re.fullmatch(r"\d{6}\.(SH|SZ)", normalized):
        raise ValueError(f"invalid A-share symbol: {symbol}")
    return normalized


def _bar_symbol(row: Mapping[str, Any]) -> str:
    return _normalize_symbol(row["symbol"])


def _validate_information_signal_envelopes(signals: tuple[Any, ...]) -> None:
    for index, signal in enumerate(signals):
        if not isinstance(signal, Mapping):
            raise ValueError(f"information_signals[{index}] must use a structured PIT envelope")
        if "signal" not in signal or "available_at" not in signal:
            raise ValueError(f"information_signals[{index}] must include signal and available_at")


def _json_ready(value: Any) -> Any:
    if is_dataclass(value):
        return _json_ready(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, tuple):
        return tuple(_json_ready(item) for item in value)
    if isinstance(value, list):
        return tuple(_json_ready(item) for item in value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    if hasattr(value, "__dict__"):
        return _json_ready(vars(value))
    return value
