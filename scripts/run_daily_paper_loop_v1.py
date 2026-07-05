"""Run one durable daily multi-agent paper-loop session."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

from quantpilot_core.daily_paper_loop import (
    DailyPaperLoopConfig,
    DailyPaperLoopInput,
    DailyPaperMarketBundle,
    build_offline_fixture_input,
    load_daily_state,
    run_daily_paper_loop,
)
from quantpilot_core.daily_paper_loop.runner import _validate_time_inputs
from quantpilot_core.execution_candidate import ExecutionCandidate, ExecutionCandidateReport
from quantpilot_core.real_data_provider import (
    DailyBarRequest,
    NormalizedDailyBar,
    ProviderName,
    TradingCalendar,
    TusharePrimaryBaoStockCalendarProvider,
    TusharePrimaryBaoStockFallbackProvider,
    is_suspended_trade_status,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one offline daily paper-loop lifecycle.")
    parser.add_argument("--state-path", default=".cache/daily_paper_loop/state.json")
    parser.add_argument("--report-path", default=".cache/daily_paper_loop/latest_report.json")
    parser.add_argument("--decision-session", default=None)
    parser.add_argument("--initial-capital", type=float, default=100_000.0)
    parser.add_argument("--input-json", default=None)
    parser.add_argument("--live-market-data", action="store_true")
    args = parser.parse_args(argv)

    if args.live_market_data and not args.decision_session:
        parser.error("--live-market-data requires --decision-session")
    if args.live_market_data and args.input_json is None:
        parser.error("--live-market-data requires --input-json with local/injected candidates")

    decision_session = args.decision_session or "2026-01-02"
    loop_input = (
        _build_live_market_input(
            args.input_json,
            decision_session,
            state_path=args.state_path,
            initial_capital=args.initial_capital,
        )
        if args.live_market_data
        else (_load_input_json(args.input_json) if args.input_json else build_offline_fixture_input(decision_session))
    )
    config = DailyPaperLoopConfig(
        decision_session=decision_session,
        initial_capital=args.initial_capital,
        state_path=args.state_path,
        report_path=args.report_path,
        live_market_data=args.live_market_data,
    )
    result = run_daily_paper_loop(loop_input, config)
    print(json.dumps({"status": result.status.value, "report_path": result.report_path, "state_path": result.state_path}, sort_keys=True))
    return 0


def _load_input_json(path: str | Path) -> DailyPaperLoopInput:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    sessions = tuple(date.fromisoformat(value) for value in payload["calendar"]["sessions"])
    provider = ProviderName(payload.get("calendar", {}).get("provider", ProviderName.BAOSTOCK.value))
    calendar = TradingCalendar(sessions, provider)
    candidates = tuple(_candidate(row) for row in payload.get("candidates", ()))
    report = ExecutionCandidateReport(
        candidates=candidates,
        aggregate_score=float(payload.get("aggregate_score", 0.0)),
        strategy_id=str(payload.get("strategy_id", "input-json-exec1")),
    )
    market = payload["market"]
    return DailyPaperLoopInput(
        calendar=calendar,
        candidate_report=report,
        market=DailyPaperMarketBundle(
            decision_rows_by_symbol=dict(market.get("decision_rows_by_symbol", market.get("decision_rows", {}))),
            execution_rows_by_symbol=dict(market.get("execution_rows_by_symbol", {})),
            market_data_provenance=dict(market.get("market_data_provenance", {"mode": "input_json"})),
        ),
        calendar_provenance=dict(payload.get("calendar_provenance", {"mode": "input_json"})),
        information_provenance=dict(payload.get("information_provenance", {"mode": "input_json"})),
        advisory_provenance=dict(payload.get("advisory_provenance", {"deepseek_live_call": False})),
        quant_firm_context=dict(payload.get("quant_firm_context", {})),
    )


def _candidate(row: Mapping[str, Any]) -> ExecutionCandidate:
    timestamp = datetime.fromisoformat(str(row["timestamp"]))
    return ExecutionCandidate(
        symbol=str(row["symbol"]),
        direction=str(row.get("direction", "long")),
        confidence=float(row.get("confidence", 1.0)),
        expected_return=float(row.get("expected_return", 0.0)),
        risk_score=float(row.get("risk_score", 0.0)),
        liquidity_score=float(row.get("liquidity_score", 1.0)),
        timestamp=timestamp,
        lot_size=int(row.get("lot_size", 100)),
        metadata=dict(row.get("metadata", {})),
    )


def _build_live_market_input(
    path: str | Path,
    decision_session: str,
    *,
    state_path: str | Path | None = None,
    initial_capital: float = 100_000.0,
    calendar_provider: Any | None = None,
    bar_provider: Any | None = None,
) -> DailyPaperLoopInput:
    loaded = _load_input_json(path)
    decision = date.fromisoformat(decision_session)
    _validate_time_inputs(loaded, decision)
    existing_symbols: tuple[str, ...] = ()
    if state_path is not None:
        state = load_daily_state(state_path, initial_capital=initial_capital)
        existing_symbols = tuple(symbol for symbol, quantity in state.execution_state.account.positions.items() if int(quantity) > 0)
    symbols = tuple(dict.fromkeys([*(candidate.symbol for candidate in loaded.candidate_report.candidates), *existing_symbols]))
    if len(symbols) > 6:
        raise ValueError("--live-market-data supports at most 6 candidate symbols")
    calendar_provider = calendar_provider or TusharePrimaryBaoStockCalendarProvider()
    calendar_result = calendar_provider.fetch_calendar_with_provenance(decision, decision + timedelta(days=10))
    calendar = calendar_result.calendar
    if not calendar.is_session(decision):
        raise ValueError(f"--decision-session is not a loaded trading session: {decision.isoformat()}")
    execution = calendar.next_session(decision)
    bar_provider = bar_provider or TusharePrimaryBaoStockFallbackProvider()
    decision_rows: dict[str, Mapping[str, Any]] = {}
    execution_rows: dict[str, Mapping[str, Any]] = {}
    bar_attempts: dict[str, Any] = {}
    for symbol in symbols:
        result = bar_provider.fetch_daily_bars_with_provenance(DailyBarRequest(symbol=symbol, start_date=decision, end_date=execution))
        by_date = _bars_by_trade_date(result.bars)
        if decision in by_date:
            decision_rows[symbol] = {**by_date[decision], "symbol": symbol}
        if execution in by_date:
            execution_rows[symbol] = {**by_date[execution], "symbol": symbol}
        bar_attempts[symbol] = {
            "selected_provider": result.selected_provider.value,
            "fallback_used": result.fallback_used,
            "attempts": [_attempt_payload(attempt) for attempt in result.attempts],
            "date_range": [result.date_range[0].isoformat(), result.date_range[1].isoformat()],
        }
    return DailyPaperLoopInput(
        calendar=calendar,
        candidate_report=loaded.candidate_report,
        market=DailyPaperMarketBundle(
            decision_rows_by_symbol=decision_rows,
            execution_rows_by_symbol=execution_rows,
            market_data_provenance={
                "mode": "live_market_data",
                "provider_chain": "tushare_primary_baostock_fallback",
                "symbol_count": len(symbols),
                "max_symbol_cap": 6,
                "calendar_attempts": [_attempt_payload(attempt) for attempt in calendar_result.attempts],
                "bar_attempts": bar_attempts,
                "network_calls_bounded": True,
            },
        ),
        calendar_provenance={
            "mode": "live_market_data",
            "selected_provider": calendar_result.selected_provider.value,
            "fallback_used": calendar_result.fallback_used,
            "sessions": calendar.to_iso_strings(),
        },
        information_provenance=loaded.information_provenance,
        advisory_provenance={**dict(loaded.advisory_provenance), "deepseek_live_call": False},
        quant_firm_context=loaded.quant_firm_context,
    )


def _bars_by_trade_date(bars: tuple[NormalizedDailyBar, ...] | list[NormalizedDailyBar]) -> Mapping[date, Mapping[str, Any]]:
    rows: dict[date, Mapping[str, Any]] = {}
    for bar in bars:
        payload = _bar_payload(bar)
        trade_date = date.fromisoformat(str(payload["date"]))
        if trade_date in rows and rows[trade_date] != payload:
            raise ValueError(f"conflicting provider daily bar rows for {bar.symbol} on {trade_date.isoformat()}")
        rows[trade_date] = payload
    return dict(sorted(rows.items()))


def _attempt_payload(attempt: Any) -> Mapping[str, Any]:
    if hasattr(attempt, "__dataclass_fields__"):
        payload = asdict(attempt)
    else:
        payload = dict(vars(attempt))
    provider = payload.get("provider")
    if hasattr(provider, "value"):
        payload["provider"] = provider.value
    return payload


def _bar_payload(bar: NormalizedDailyBar) -> Mapping[str, Any]:
    return {
        "symbol": bar.symbol,
        "date": bar.trade_date.isoformat(),
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "previous_close": bar.previous_close,
        "volume": bar.volume,
        "amount": bar.amount,
        "is_suspended": is_suspended_trade_status(bar.trade_status),
        "provider": bar.provider.value,
    }


if __name__ == "__main__":
    raise SystemExit(main())
