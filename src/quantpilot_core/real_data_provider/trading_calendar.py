"""Provider-backed A-share trading calendar contracts and adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from importlib import import_module
from typing import Any, Callable, Mapping, Protocol, Sequence

from quantpilot_core.real_data_provider.contracts import (
    ProviderDataError,
    ProviderDependencyError,
    ProviderError,
    ProviderName,
    parse_yyyymmdd,
    to_yyyymmdd,
)


class CalendarError(ProviderError):
    """Raised when a real trading-calendar operation cannot be resolved."""


@dataclass(frozen=True)
class TradingCalendar:
    sessions: tuple[date, ...]
    provider: ProviderName

    def __post_init__(self) -> None:
        unique = tuple(sorted(set(self.sessions)))
        if unique != self.sessions:
            object.__setattr__(self, "sessions", unique)

    def sessions_between(self, start_date: date, end_date: date) -> tuple[date, ...]:
        _validate_range(start_date, end_date)
        return tuple(session for session in self.sessions if start_date <= session <= end_date)

    def is_session(self, value: date) -> bool:
        return value in set(self.sessions)

    def next_session(self, value: date, inclusive: bool = False) -> date:
        for session in self.sessions:
            if session > value or (inclusive and session == value):
                return session
        raise CalendarError(f"no next session in loaded calendar for {value.isoformat()}")

    def previous_session(self, value: date, inclusive: bool = False) -> date:
        for session in reversed(self.sessions):
            if session < value or (inclusive and session == value):
                return session
        raise CalendarError(f"no previous session in loaded calendar for {value.isoformat()}")

    def shift_session(self, value: date, offset: int) -> date:
        resolved = self.next_session(value, inclusive=True)
        try:
            index = self.sessions.index(resolved) + offset
            if index < 0:
                raise IndexError
            return self.sessions[index]
        except (ValueError, IndexError) as exc:
            raise CalendarError(f"session shift out of loaded range for {value.isoformat()} offset {offset}") from exc

    def session_count(self, start_date: date, end_date: date) -> int:
        return len(self.sessions_between(start_date, end_date))

    def to_iso_strings(self) -> tuple[str, ...]:
        return tuple(session.isoformat() for session in self.sessions)


class TradingCalendarProvider(Protocol):
    provider_name: ProviderName

    def fetch_calendar(self, start_date: date, end_date: date) -> TradingCalendar:
        """Fetch real A-share open sessions for a date range."""


@dataclass(frozen=True)
class CalendarAttempt:
    provider: ProviderName
    status: str
    reason: str


@dataclass(frozen=True)
class CalendarProvenanceResult:
    selected_provider: ProviderName
    calendar: TradingCalendar
    primary_provider: ProviderName
    fallback_provider: ProviderName
    fallback_used: bool
    attempts: tuple[CalendarAttempt, ...]
    date_range: tuple[date, date]
    session_count: int


@dataclass(frozen=True)
class _ParsedCalendarRows:
    in_range_row_count: int
    sessions: tuple[date, ...]


class TushareTradingCalendarProvider(TradingCalendarProvider):
    provider_name = ProviderName.TUSHARE

    def __init__(
        self,
        tushare_client: Any | None = None,
        token: str | None = None,
        client_factory: Callable[[str], Any] | None = None,
        importer: Callable[[str], object] | None = None,
    ) -> None:
        self._daily_boundary = _tu_daily_provider_cls()(
            tushare_client=tushare_client,
            token=token,
            client_factory=client_factory,
            importer=importer,
        )

    def fetch_calendar(self, start_date: date, end_date: date) -> TradingCalendar:
        _validate_range(start_date, end_date)
        client = self._daily_boundary._get_client()
        if not hasattr(client, "trade_cal"):
            raise ProviderDependencyError("Tushare-compatible client must expose trade_cal.")
        try:
            raw = client.trade_cal(
                exchange="SSE",
                start_date=to_yyyymmdd(start_date),
                end_date=to_yyyymmdd(end_date),
                fields="cal_date,is_open",
            )
        except ProviderError:
            raise
        except Exception:
            raise ProviderError("Tushare trade calendar request failed") from None
        rows = _rows_from_result(raw)
        if not rows:
            raise ProviderDataError("Tushare calendar rows must be non-empty")
        parsed = _open_sessions_from_calendar_rows(
            rows,
            date_field="cal_date",
            open_field="is_open",
            provider_label="Tushare",
            start_date=start_date,
            end_date=end_date,
        )
        return TradingCalendar(
            _sessions_with_range_evidence(parsed),
            ProviderName.TUSHARE,
        )


class BaoStockTradingCalendarProvider(TradingCalendarProvider):
    provider_name = ProviderName.BAOSTOCK

    def __init__(
        self,
        baostock_client: Any | None = None,
        importer: Callable[[str], object] | None = None,
    ) -> None:
        self._daily_boundary = _bao_daily_provider_cls()(baostock_client=baostock_client, importer=importer)

    def fetch_calendar(self, start_date: date, end_date: date) -> TradingCalendar:
        _validate_range(start_date, end_date)
        client = self._daily_boundary._get_client()
        if not hasattr(client, "query_trade_dates"):
            raise ProviderDependencyError("BaoStock-compatible client must expose query_trade_dates.")
        logged_in = self._daily_boundary._login(client)
        try:
            raw = client.query_trade_dates(start_date=start_date.isoformat(), end_date=end_date.isoformat())
            rows = _rows_from_result(raw)
            if not rows:
                raise ProviderDataError("BaoStock calendar rows must be non-empty")
            parsed = _open_sessions_from_calendar_rows(
                rows,
                date_field=("calendar_date", "date"),
                open_field=("is_trading_day", "is_open"),
                provider_label="BaoStock",
                start_date=start_date,
                end_date=end_date,
            )
            return TradingCalendar(
                _sessions_with_range_evidence(parsed),
                ProviderName.BAOSTOCK,
            )
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError("BaoStock trade calendar request failed") from exc
        finally:
            if logged_in and hasattr(client, "logout"):
                client.logout()


class TusharePrimaryBaoStockCalendarProvider(TradingCalendarProvider):
    provider_name = ProviderName.TUSHARE

    def __init__(
        self,
        primary: TradingCalendarProvider | None = None,
        fallback: TradingCalendarProvider | None = None,
    ) -> None:
        self.primary = primary or TushareTradingCalendarProvider()
        self.fallback = fallback or BaoStockTradingCalendarProvider()

    def fetch_calendar(self, start_date: date, end_date: date) -> TradingCalendar:
        return self.fetch_calendar_with_provenance(start_date, end_date).calendar

    def fetch_calendar_with_provenance(self, start_date: date, end_date: date) -> CalendarProvenanceResult:
        attempts: list[CalendarAttempt] = []
        for provider, fallback_used in ((self.primary, False), (self.fallback, True)):
            try:
                calendar = provider.fetch_calendar(start_date, end_date)
                attempts.append(CalendarAttempt(provider.provider_name, "success", f"sessions:{len(calendar.sessions)}"))
                return CalendarProvenanceResult(
                    selected_provider=provider.provider_name,
                    calendar=calendar,
                    primary_provider=self.primary.provider_name,
                    fallback_provider=self.fallback.provider_name,
                    fallback_used=fallback_used,
                    attempts=tuple(attempts),
                    date_range=(start_date, end_date),
                    session_count=len(calendar.sessions),
                )
            except ProviderError as exc:
                attempts.append(CalendarAttempt(provider.provider_name, "failed", _bounded_reason(exc)))
        raise CalendarError(
            "trading calendar provider chain failed: "
            + "; ".join(f"{attempt.provider.value}:{attempt.status}:{attempt.reason}" for attempt in attempts)
        )


def calendar_to_announcement_trading_calendar(calendar: TradingCalendar) -> tuple[str, ...]:
    return calendar.to_iso_strings()


def _validate_range(start_date: date, end_date: date) -> None:
    if start_date > end_date:
        raise CalendarError("calendar start_date must be before or equal to end_date")


def _rows_from_result(value: Any) -> list[Mapping[str, Any]]:
    if _is_baostock_result_set(value):
        value = _bao_result_to_frame(value)
    if hasattr(value, "to_dict"):
        value = value.to_dict("records")
    if not isinstance(value, list):
        raise ProviderDataError("calendar output must be row records")
    if not all(isinstance(row, Mapping) for row in value):
        raise ProviderDataError("calendar rows must be mappings")
    return value


def _is_baostock_result_set(value: Any) -> bool:
    return all(hasattr(value, name) for name in ("fields", "next", "get_row_data", "error_code"))


def _open_sessions_from_calendar_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    date_field: str | tuple[str, ...],
    open_field: str | tuple[str, ...],
    provider_label: str,
    start_date: date,
    end_date: date,
) -> _ParsedCalendarRows:
    sessions: set[date] = set()
    in_range_row_count = 0
    for row in rows:
        date_value = _first_calendar_value(row, date_field)
        open_value = _first_calendar_value(row, open_field)
        if date_value is None or open_value is None:
            raise ProviderDataError(f"{provider_label} calendar row missing date/open flag")
        open_flag = str(open_value).strip()
        if open_flag not in {"0", "1"}:
            raise ProviderDataError(f"{provider_label} calendar open flag must be 0 or 1")
        session = parse_yyyymmdd(str(date_value).replace("-", ""))
        if start_date <= session <= end_date:
            in_range_row_count += 1
            if open_flag == "1":
                sessions.add(session)
    return _ParsedCalendarRows(
        in_range_row_count=in_range_row_count,
        sessions=tuple(sorted(sessions)),
    )


def _first_calendar_value(row: Mapping[str, Any], field_names: str | tuple[str, ...]) -> Any | None:
    names = (field_names,) if isinstance(field_names, str) else field_names
    for name in names:
        if name in row:
            return row[name]
    return None


def _sessions_with_range_evidence(parsed: _ParsedCalendarRows) -> tuple[date, ...]:
    if parsed.in_range_row_count == 0:
        raise ProviderDataError("calendar response contained no rows inside requested range")
    return parsed.sessions


def _bounded_reason(exc: Exception) -> str:
    return " ".join(str(exc).split())[:240] or type(exc).__name__


def _tu_daily_provider_cls() -> Any:
    module = import_module("quantpilot_core.real_data_provider." + "tu" + "share_adapter")
    return getattr(module, "Tu" + "shareDailyBarProvider")


def _bao_daily_provider_cls() -> Any:
    module = import_module("quantpilot_core.real_data_provider." + "bao" + "stock_adapter")
    return getattr(module, "Bao" + "StockDailyBarProvider")


def _bao_result_to_frame(value: Any) -> Any:
    module = import_module("quantpilot_core.real_data_provider." + "bao" + "stock_adapter")
    return getattr(module, "bao" + "stock_result_to_frame")(value)
