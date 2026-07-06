"""Provider-backed market input builders for the durable daily paper loop."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

from quantpilot_core.daily_paper_loop.contracts import DailyPaperLoopInput, DailyPaperMarketBundle
from quantpilot_core.daily_paper_loop.state import load_daily_state
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

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
TIME_FIELD_NAMES = {
    "published_at",
    "discovered_at",
    "available_at",
    "first_available_time",
    "pit_availability_time",
    "pit_availability_timestamp",
    "information_timestamp",
    "signal_timestamp",
    "as_of_timestamp",
}
LEAKAGE_LABEL_PATTERNS = (
    "event_study_label",
    "forward_return",
    "stock_forward_return",
    "benchmark_forward_return",
    "excess_return",
)


@dataclass(frozen=True)
class ProviderMarketRows:
    """Provider-loaded rows and provenance for exact decision/execution sessions."""

    calendar: TradingCalendar
    decision_session: date
    execution_session: date
    rows: tuple[Mapping[str, Any], ...]
    decision_rows_by_symbol: Mapping[str, Mapping[str, Any]]
    execution_rows_by_symbol: Mapping[str, Mapping[str, Any]]
    calendar_provenance: Mapping[str, Any]
    market_data_provenance: Mapping[str, Any]


def load_daily_loop_input_json(path: str | Path) -> DailyPaperLoopInput:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    sessions = tuple(date.fromisoformat(value) for value in payload["calendar"]["sessions"])
    provider = ProviderName(payload.get("calendar", {}).get("provider", "baostock"))
    calendar = TradingCalendar(sessions, provider)
    candidates = tuple(candidate_from_payload(row) for row in payload.get("candidates", ()))
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


def candidate_from_payload(row: Mapping[str, Any]) -> ExecutionCandidate:
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


def build_provider_market_input(
    path: str | Path,
    decision_session: str,
    *,
    state_path: str | Path | None = None,
    initial_capital: float = 100_000.0,
    calendar_provider: Any | None = None,
    bar_provider: Any | None = None,
) -> DailyPaperLoopInput:
    loaded = load_daily_loop_input_json(path)
    decision = date.fromisoformat(decision_session)
    validate_pit_safe_inputs(loaded, decision)
    existing_symbols: tuple[str, ...] = ()
    if state_path is not None:
        state = load_daily_state(state_path, initial_capital=initial_capital)
        existing_symbols = tuple(symbol for symbol, quantity in state.execution_state.account.positions.items() if int(quantity) > 0)
    symbols = tuple(dict.fromkeys([*(candidate.symbol for candidate in loaded.candidate_report.candidates), *existing_symbols]))
    loaded_rows = load_provider_market_rows(
        decision_session=decision,
        calendar_start=decision,
        calendar_end=decision + timedelta(days=10),
        symbols=symbols,
        bar_start_session=decision,
        calendar_provider=calendar_provider,
        bar_provider=bar_provider,
        max_symbol_cap=6,
        cap_error_message="--live-market-data supports at most 6 candidate symbols",
    )
    return DailyPaperLoopInput(
        calendar=loaded_rows.calendar,
        candidate_report=loaded.candidate_report,
        market=DailyPaperMarketBundle(
            decision_rows_by_symbol=loaded_rows.decision_rows_by_symbol,
            execution_rows_by_symbol=loaded_rows.execution_rows_by_symbol,
            market_data_provenance=loaded_rows.market_data_provenance,
        ),
        calendar_provenance=loaded_rows.calendar_provenance,
        information_provenance=loaded.information_provenance,
        advisory_provenance={**dict(loaded.advisory_provenance), "deepseek_live_call": False},
        quant_firm_context=loaded.quant_firm_context,
    )


def load_provider_market_rows(
    *,
    decision_session: date,
    calendar_start: date,
    calendar_end: date,
    symbols: Iterable[str],
    bar_start_session: date | None,
    bar_start_session_offset: int | None = None,
    bar_end_session: date | None = None,
    execution_session: date | None = None,
    calendar_provider: Any | None = None,
    bar_provider: Any | None = None,
    max_symbol_cap: int = 6,
    cap_error_message: str = "--live-market-data supports at most 6 symbols",
) -> ProviderMarketRows:
    symbol_tuple = tuple(dict.fromkeys(str(symbol).strip() for symbol in symbols if str(symbol).strip()))
    if len(symbol_tuple) > int(max_symbol_cap):
        raise ValueError(cap_error_message)
    calendar_provider = calendar_provider or TusharePrimaryBaoStockCalendarProvider()
    calendar_result = calendar_provider.fetch_calendar_with_provenance(calendar_start, calendar_end)
    calendar = calendar_result.calendar
    if not calendar.is_session(decision_session):
        raise ValueError(f"decision_session is not a loaded trading session: {decision_session.isoformat()}")
    resolved_execution = execution_session or calendar.next_session(decision_session)
    if not calendar.is_session(resolved_execution):
        raise ValueError(f"execution_session is not a loaded trading session: {resolved_execution.isoformat()}")
    if calendar.next_session(decision_session) != resolved_execution:
        raise ValueError("execution_session must be the next loaded trading session after decision_session")
    if bar_start_session is None:
        if bar_start_session_offset is None:
            raise ValueError("bar_start_session or bar_start_session_offset is required")
        resolved_bar_start = calendar.shift_session(decision_session, int(bar_start_session_offset))
    else:
        resolved_bar_start = bar_start_session
    resolved_bar_end = bar_end_session or resolved_execution
    bar_provider = bar_provider or TusharePrimaryBaoStockFallbackProvider()
    rows: list[Mapping[str, Any]] = []
    decision_rows: dict[str, Mapping[str, Any]] = {}
    execution_rows: dict[str, Mapping[str, Any]] = {}
    bar_attempts: dict[str, Any] = {}
    for symbol in symbol_tuple:
        result = bar_provider.fetch_daily_bars_with_provenance(
            DailyBarRequest(symbol=symbol, start_date=resolved_bar_start, end_date=resolved_bar_end)
        )
        by_date = bars_by_trade_date(result.bars)
        rows.extend(by_date.values())
        if decision_session in by_date:
            decision_rows[symbol] = {**by_date[decision_session], "symbol": symbol}
        if resolved_execution in by_date:
            execution_rows[symbol] = {**by_date[resolved_execution], "symbol": symbol}
        bar_attempts[symbol] = {
            "selected_provider": result.selected_provider.value,
            "fallback_used": result.fallback_used,
            "attempts": [attempt_payload(attempt) for attempt in result.attempts],
            "date_range": [result.date_range[0].isoformat(), result.date_range[1].isoformat()],
        }
    return ProviderMarketRows(
        calendar=calendar,
        decision_session=decision_session,
        execution_session=resolved_execution,
        rows=tuple(rows),
        decision_rows_by_symbol=decision_rows,
        execution_rows_by_symbol=execution_rows,
        calendar_provenance={
            "mode": "live_market_data",
            "selected_provider": calendar_result.selected_provider.value,
            "fallback_used": calendar_result.fallback_used,
            "sessions": calendar.to_iso_strings(),
            "calendar_attempts": [attempt_payload(attempt) for attempt in calendar_result.attempts],
        },
        market_data_provenance={
            "mode": "live_market_data",
            "provider_chain": "tushare_primary_baostock_fallback",
            "symbol_count": len(symbol_tuple),
            "max_symbol_cap": int(max_symbol_cap),
            "calendar_attempts": [attempt_payload(attempt) for attempt in calendar_result.attempts],
            "bar_attempts": bar_attempts,
            "network_calls_bounded": True,
            "bar_start_session": resolved_bar_start.isoformat(),
            "bar_end_session": resolved_bar_end.isoformat(),
        },
    )


def validate_pit_safe_inputs(value: Any, decision_session: date) -> None:
    cutoff = datetime(decision_session.year, decision_session.month, decision_session.day, 15, 0, tzinfo=SHANGHAI_TZ)
    for path, timestamp in _time_values(value):
        normalized = _aware_timestamp(timestamp, path)
        if normalized > cutoff:
            raise ValueError(f"{path} is after decision cutoff")
    _reject_forward_labels(value)


def bars_by_trade_date(bars: tuple[NormalizedDailyBar, ...] | list[NormalizedDailyBar]) -> Mapping[date, Mapping[str, Any]]:
    rows: dict[date, Mapping[str, Any]] = {}
    for bar in bars:
        payload = bar_payload(bar)
        trade_date = date.fromisoformat(str(payload["date"]))
        if trade_date in rows and rows[trade_date] != payload:
            raise ValueError(f"conflicting provider daily bar rows for {bar.symbol} on {trade_date.isoformat()}")
        rows[trade_date] = payload
    return dict(sorted(rows.items()))


def attempt_payload(attempt: Any) -> Mapping[str, Any]:
    if hasattr(attempt, "__dataclass_fields__"):
        payload = asdict(attempt)
    else:
        payload = dict(vars(attempt))
    provider = payload.get("provider")
    if hasattr(provider, "value"):
        payload["provider"] = provider.value
    return payload


def bar_payload(bar: NormalizedDailyBar) -> Mapping[str, Any]:
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


def _time_values(value: Any, path: str = "input", depth: int = 0) -> Iterable[tuple[str, Any]]:
    if depth > 12:
        return
    if is_dataclass(value) and not isinstance(value, type):
        yield from _time_values(asdict(value), path, depth + 1)
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}"
            if _is_time_key(key_text):
                yield child_path, item
            else:
                yield from _time_values(item, child_path, depth + 1)
        return
    if isinstance(value, (tuple, list)):
        for index, item in enumerate(value):
            yield from _time_values(item, f"{path}[{index}]", depth + 1)
        return
    if isinstance(value, str):
        lowered = value.lower()
        for key in TIME_FIELD_NAMES:
            match = re.search(rf"{re.escape(key)}\s*[:=]\s*([^,\s;]+)", lowered)
            if match:
                yield f"{path}.{key}", match.group(1)


def _is_time_key(key: str) -> bool:
    normalized = key.strip().lower()
    return normalized in TIME_FIELD_NAMES or "timestamp" in normalized or "cutoff" in normalized


def _aware_timestamp(value: Any, path: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        raise ValueError(f"{path} must be timezone-aware")
    return parsed.astimezone(SHANGHAI_TZ)


def _reject_forward_labels(value: Any, path: str = "input", depth: int = 0) -> None:
    if depth > 12:
        return
    if is_dataclass(value) and not isinstance(value, type):
        _reject_forward_labels(asdict(value), path, depth + 1)
        return
    if isinstance(value, str):
        lowered = value.lower()
        if any(pattern in lowered for pattern in LEAKAGE_LABEL_PATTERNS):
            raise ValueError(f"{path} is not a PIT-safe candidate feature")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key).strip().lower()
            if any(pattern in key_text for pattern in LEAKAGE_LABEL_PATTERNS):
                raise ValueError(f"{path}.{key} is not a PIT-safe candidate feature")
            _reject_forward_labels(item, f"{path}.{key}", depth + 1)
        return
    if isinstance(value, (tuple, list)):
        for index, item in enumerate(value):
            _reject_forward_labels(item, f"{path}[{index}]", depth + 1)
