"""Optional Windows runtime adapter for TDX TQCenter Level1 snapshots."""

from __future__ import annotations

import json
import platform
import re
import sys
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from itertools import count
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from quantpilot_core.data_provider_normalization import canonicalize_a_share_symbol
from quantpilot_core.real_data_provider.contracts import (
    NormalizedIntradayBar,
    NormalizedLevel1Event,
    ProviderArgumentError,
    ProviderDataError,
    ProviderDependencyError,
    ProviderError,
    ProviderName,
)


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")

_SYMBOL_FIELDS = ("Code", "code", "StockCode", "stock_code", "SecurityID", "symbol")
_TIMESTAMP_FIELDS = ("DateTime", "datetime", "Timestamp", "timestamp", "QuoteTime", "quote_time")
_DATE_FIELDS = ("Date", "date", "TradingDate", "trading_date", "TradeDate", "trade_date")
_TIME_FIELDS = ("Time", "time", "TickTime", "tick_time", "UpdateTime", "update_time")
_FIELD_ALIASES: Mapping[str, tuple[str, ...]] = {
    "last_price": ("Now", "LastPrice", "last_price", "Price", "price", "NewPrice", "new_price", "Close", "close"),
    "open": ("Open", "open", "OpenPrice", "open_price"),
    "high": ("Max", "High", "high", "HighPrice", "high_price"),
    "low": ("Min", "Low", "low", "LowPrice", "low_price"),
    "cumulative_volume": ("Volume", "volume", "TotalVolume", "total_volume", "Vol", "vol"),
    "cumulative_amount": ("Amount", "amount", "TotalAmount", "total_amount", "TurnoverValue", "turnover_value"),
    "average_price": ("Average", "AveragePrice", "average_price", "AvgPrice", "avg_price"),
    "buy1": ("Buyp", "Buy1", "buy1", "BuyPrice1", "buy_price1", "BidPrice1", "bid_price1", "Bid1", "bid1"),
    "sell1": ("Sellp", "Sell1", "sell1", "SellPrice1", "sell_price1", "AskPrice1", "ask_price1", "Ask1", "ask1"),
    "now_volume": ("NowVol", "now_volume"),
    "inside_volume": ("Inside", "InsideVolume", "inside_volume", "InnerVolume", "inner_volume"),
    "outside_volume": ("Outside", "OutsideVolume", "outside_volume", "OuterVolume", "outer_volume"),
    "buy_volume_levels": ("Buyv", "buy_volume_levels"),
    "sell_volume_levels": ("Sellv", "sell_volume_levels"),
}

_TDX_SOURCE_UNITS: Mapping[str, str] = {
    "Volume": "lots_of_100_shares",
    "Amount": "10000_cny",
    "NowVol": "unconfirmed_tdx_source_unit",
    "Buyv": "unconfirmed_tdx_source_unit",
    "Sellv": "unconfirmed_tdx_source_unit",
    "Inside": "unconfirmed_tdx_source_unit",
    "Outside": "unconfirmed_tdx_source_unit",
}

_TDX_INITIALIZATION_FILE = Path(__file__).resolve()
_REQUIRED_LEVEL1_FUNCTIONS = (
    "initialize",
    "get_market_snapshot",
    "subscribe_hq",
    "unsubscribe_hq",
)
_HISTORICAL_MINUTE_FIELDS = ("Open", "High", "Low", "Close", "Volume", "Amount")
_NO_RAW_RESULT = object()
_SUBSCRIPTION_CALLBACKS: dict[int, _CallbackRegistration] = {}
_SUBSCRIPTION_CALLBACKS_LOCK = threading.RLock()
_SUBSCRIPTION_CALLBACK_IDS = count(1)


class TDXInitializationError(ProviderError):
    """Structured, sanitized failure from a specific TDX initialization stage."""

    def __init__(self, initialization_stage: str, message: str) -> None:
        self.initialization_stage = initialization_stage
        self.sanitized_source_message = _sanitize_exception_message(message)
        super().__init__(
            f"TDX initialization failed at {initialization_stage}: "
            f"{self.sanitized_source_message}"
        )

    def as_dict(self) -> dict[str, str]:
        details = {
            "initialization_stage": self.initialization_stage,
            "exception_type": type(self).__name__,
            "sanitized_exception_message": str(self),
        }
        cause = self.__cause__
        if cause is not None:
            details["cause_exception_type"] = type(cause).__name__
            details["sanitized_cause_message"] = _sanitize_exception_message(str(cause))
        return details


class TDXInitializationDependencyError(TDXInitializationError, ProviderDependencyError):
    """Initialization failure caused by platform, path, import, or API shape."""


class TDXOperationError(ProviderError):
    """Structured, sanitized failure from a specific TDX runtime operation stage."""

    def __init__(
        self,
        operation_stage: str,
        message: str,
        *,
        requested_symbol: str,
        api_call_completed: bool,
        raw_result: Any = _NO_RAW_RESULT,
    ) -> None:
        self.operation_stage = operation_stage
        self.requested_symbol = requested_symbol
        self.api_call_completed = bool(api_call_completed)
        self.sanitized_source_message = _sanitize_exception_message(message)
        self.raw_result_type: str | None = None
        self.raw_result_keys: tuple[str, ...] | None = None
        if raw_result is not _NO_RAW_RESULT:
            self.raw_result_type = type(raw_result).__name__
            if isinstance(raw_result, Mapping):
                self.raw_result_keys = tuple(sorted(str(key) for key in raw_result))
        super().__init__(
            f"TDX operation failed at {operation_stage} for {requested_symbol}: "
            f"{self.sanitized_source_message}"
        )

    def as_dict(self) -> dict[str, Any]:
        details: dict[str, Any] = {
            "operation_stage": self.operation_stage,
            "exception_type": type(self).__name__,
            "sanitized_exception_message": str(self),
            "requested_symbol": self.requested_symbol,
            "api_call_completed": self.api_call_completed,
        }
        if self.raw_result_type is not None:
            details["raw_result_type"] = self.raw_result_type
        if self.raw_result_keys is not None:
            details["raw_result_keys"] = self.raw_result_keys
        cause = self.__cause__
        if cause is not None:
            details["cause_exception_type"] = type(cause).__name__
            details["sanitized_cause_message"] = _sanitize_exception_message(str(cause))
        return details


class TDXSubscriptionError(ProviderError):
    """Sanitized failure while registering the TDX refresh callback."""

    def __init__(self, message: str) -> None:
        self.sanitized_message = _sanitize_exception_message(message)
        super().__init__(f"tqcenter subscribe_hq failed: {self.sanitized_message}")


class TDXUnsubscribeError(ProviderError):
    """Sanitized failure while removing the TDX symbol subscription."""

    def __init__(self, message: str) -> None:
        self.sanitized_message = _sanitize_exception_message(message)
        super().__init__(f"tqcenter unsubscribe_hq failed: {self.sanitized_message}")


@dataclass
class _CallbackDiagnostics:
    callback_count: int = 0
    parse_error_count: int = 0
    dispatch_error_count: int = 0
    last_sanitized_error: str | None = None


@dataclass(frozen=True)
class _CallbackRegistration:
    callback: Callable[[Mapping[str, Any]], None]
    diagnostics: _CallbackDiagnostics


@dataclass(frozen=True)
class _TDXSubscription:
    symbols: tuple[str, ...]
    callback_id: int
    sanitized_response_summary: str


class TDXLevel1Provider:
    """Thin adapter over the verified ``tqcenter.py`` Level1 functions.

    ``tqcenter`` is deliberately imported only from :meth:`initialize`. Tests
    inject a module loader and never require a TDX installation.
    """

    provider_name = ProviderName.TDX_LEVEL1

    def __init__(
        self,
        tdx_user_dir: str | Path,
        *,
        module_loader: Callable[[str], Any] | None = None,
        platform_system: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
        snapshot_fields: Sequence[str] = (),
    ) -> None:
        self.tdx_user_dir = Path(tdx_user_dir)
        self._module_loader = module_loader
        self._platform_system = platform_system or platform.system
        self._clock = clock or (lambda: datetime.now(SHANGHAI_TZ))
        self._snapshot_fields = tuple(str(field) for field in snapshot_fields)
        self._api: Any | None = None
        self._subscriptions: list[_TDXSubscription] = []
        self._callback_diagnostics = _CallbackDiagnostics()
        self._sanitized_subscription_response: str | None = None

    @property
    def initialized(self) -> bool:
        return self._api is not None

    def initialize(self) -> None:
        if self.initialized:
            return
        if self._platform_system() != "Windows":
            raise TDXInitializationDependencyError(
                "platform_validation",
                "TDX Level1 is available only on Windows",
            )
        if not self.tdx_user_dir.is_dir():
            raise TDXInitializationDependencyError(
                "runtime_directory_validation",
                "configured TDX user directory does not exist",
            )
        module_path = self.tdx_user_dir / "tqcenter.py"
        if not module_path.is_file():
            raise TDXInitializationDependencyError(
                "tqcenter_path_validation",
                "tqcenter.py not found in configured TDX user directory",
            )
        if not _TDX_INITIALIZATION_FILE.is_file():
            raise TDXInitializationDependencyError(
                "initialize_path_validation",
                "provider initialization Python file does not exist",
            )
        user_dir = str(self.tdx_user_dir)
        path_was_prepended = not sys.path or sys.path[0] != user_dir
        if path_was_prepended:
            sys.path.insert(0, user_dir)
        try:
            try:
                module = (
                    self._module_loader("tqcenter")
                    if self._module_loader is not None
                    else __import__("tqcenter", fromlist=("tq",))
                )
            except Exception as exc:
                raise TDXInitializationDependencyError(
                    "tqcenter_import",
                    str(exc) or "normal Python import of tqcenter failed",
                ) from exc
            if self._module_loader is None:
                origin = getattr(module, "__file__", None)
                if origin is None or Path(origin).resolve() != module_path.resolve():
                    raise TDXInitializationDependencyError(
                        "tqcenter_origin_validation",
                        "normal Python import did not resolve to configured tqcenter.py",
                    )
            try:
                api = module.tq
            except AttributeError as exc:
                raise TDXInitializationDependencyError(
                    "tq_object_validation",
                    "imported tqcenter module does not expose tqcenter.tq",
                ) from exc
            missing = tuple(
                name
                for name in _REQUIRED_LEVEL1_FUNCTIONS
                if not callable(getattr(api, name, None))
            )
            if missing:
                error = AttributeError(
                    f"tqcenter.tq missing required Level1 functions: {', '.join(missing)}"
                )
                raise TDXInitializationDependencyError(
                    "tq_api_validation",
                    str(error),
                ) from error
            try:
                api.initialize(str(_TDX_INITIALIZATION_FILE))
            except Exception as exc:
                raise TDXInitializationError(
                    "tq_initialize",
                    str(exc) or "tqcenter.tq.initialize failed",
                ) from exc
        finally:
            if path_was_prepended:
                _remove_first_sys_path_entry(user_dir)
        self._api = api

    def get_market_snapshot(self, symbols: Sequence[str]) -> tuple[NormalizedLevel1Event, ...]:
        api = self._require_api()
        requested = _canonical_symbols(symbols)
        _validate_plugin_query_arguments(
            operation="get_market_snapshot",
            symbols=requested,
            collection_phase="live_snapshot_poll",
            reason=_require_non_empty_snapshot_fields(self._snapshot_fields),
        )
        received_at = _shanghai_timestamp(self._clock())
        events: list[NormalizedLevel1Event] = []
        for symbol in requested:
            try:
                raw = api.get_market_snapshot(
                    stock_code=symbol,
                    field_list=list(self._snapshot_fields),
                )
            except Exception as exc:
                raise TDXOperationError(
                    "get_market_snapshot_api_call",
                    str(exc) or "tqcenter.tq.get_market_snapshot failed",
                    requested_symbol=symbol,
                    api_call_completed=False,
                ) from exc
            try:
                _validate_snapshot_return(raw)
            except Exception as exc:
                raise TDXOperationError(
                    "snapshot_return_validation",
                    str(exc),
                    requested_symbol=symbol,
                    api_call_completed=True,
                    raw_result=raw,
                ) from exc
            try:
                _validate_snapshot_symbol_binding(raw, symbol)
            except Exception as exc:
                raise TDXOperationError(
                    "snapshot_symbol_binding",
                    str(exc),
                    requested_symbol=symbol,
                    api_call_completed=True,
                    raw_result=raw,
                ) from exc
            try:
                normalized = normalize_tdx_level1_snapshot(
                    raw,
                    requested_symbols=(symbol,),
                    received_at=received_at,
                )
            except Exception as exc:
                raise TDXOperationError(
                    "snapshot_normalization",
                    str(exc),
                    requested_symbol=symbol,
                    api_call_completed=True,
                    raw_result=raw,
                ) from exc
            events.extend(normalized)
        return tuple(sorted(events, key=lambda event: event.symbol))

    def get_historical_intraday_bars(
        self,
        symbols: Sequence[str],
        *,
        period: str,
        fields: Sequence[str],
        start_time: str,
        end_time: str,
        count: int,
        dividend_type: str,
        fill_data: bool,
    ) -> tuple[NormalizedIntradayBar, ...]:
        """Fetch and normalize local TDX one-minute history through ``tq``."""

        api = self._require_api()
        requested = _canonical_symbols(symbols)
        _validate_plugin_query_arguments(
            operation="get_market_data",
            symbols=requested,
            collection_phase="historical_prime",
            reason=_require_non_empty_time_window(start_time, end_time),
        )
        if period != "1m":
            raise ProviderArgumentError(
                "TDX get_market_data rejected during historical_prime: "
                "period must be '1m' only"
            )
        requested_fields = tuple(str(field).strip() for field in fields if str(field).strip())
        _require_historical_minute_fields(requested_fields)
        get_market_data = getattr(api, "get_market_data", None)
        if not callable(get_market_data):
            raise ProviderDependencyError("tqcenter.tq does not expose get_market_data")
        try:
            raw = get_market_data(
                field_list=list(requested_fields),
                stock_list=list(requested),
                period=period,
                start_time=start_time,
                end_time=end_time,
                count=int(count),
                dividend_type=dividend_type,
                fill_data=bool(fill_data),
            )
        except Exception as exc:
            raise ProviderError("tqcenter get_market_data failed") from exc
        return normalize_tdx_historical_minute_bars(raw, requested_symbols=requested)

    def subscribe_hq(
        self,
        symbols: Sequence[str],
        callback: Callable[[Mapping[str, Any]], None],
    ) -> Any:
        api = self._require_api()
        requested = _canonical_symbols(symbols)
        _validate_plugin_query_arguments(
            operation="subscribe_hq",
            symbols=requested,
            collection_phase="subscription",
            reason=None,
        )
        if not callable(callback):
            raise TypeError("callback must be callable")
        callback_id = _register_subscription_callback(callback, self._callback_diagnostics)
        try:
            response = api.subscribe_hq(
                stock_list=list(requested),
                callback=_tdx_subscription_callback,
            )
        except Exception as exc:
            _unregister_subscription_callback(callback_id)
            raise TDXSubscriptionError(
                str(exc) or "tqcenter.tq.subscribe_hq raised an exception"
            ) from exc
        try:
            response_summary = _interpret_subscription_response(response)
        except Exception as exc:
            _unregister_subscription_callback(callback_id)
            raise TDXSubscriptionError(str(exc)) from exc
        self._sanitized_subscription_response = response_summary
        subscription = _TDXSubscription(requested, callback_id, response_summary)
        self._subscriptions.append(subscription)
        return subscription

    def unsubscribe_hq(self, subscription: Any) -> None:
        if not isinstance(subscription, _TDXSubscription) or subscription not in self._subscriptions:
            return
        self._subscriptions = [item for item in self._subscriptions if item != subscription]
        _unregister_subscription_callback(subscription.callback_id)
        api = self._api
        if api is None:
            return
        try:
            api.unsubscribe_hq(stock_list=list(subscription.symbols))
        except Exception as exc:
            raise TDXUnsubscribeError(
                str(exc) or "tqcenter.tq.unsubscribe_hq raised an exception"
            ) from exc

    def close(self) -> None:
        api = self._api
        if api is None:
            return
        first_error: Exception | None = None
        for subscription in tuple(self._subscriptions):
            try:
                self.unsubscribe_hq(subscription)
            except Exception as exc:  # shutdown still releases local runtime state
                first_error = first_error or exc
        self._subscriptions.clear()
        self._api = None
        if first_error is not None:
            raise ProviderError("tqcenter unsubscribe_hq failed during shutdown") from first_error

    def callback_diagnostics(self) -> Mapping[str, Any]:
        with _SUBSCRIPTION_CALLBACKS_LOCK:
            return {
                "callback_count": self._callback_diagnostics.callback_count,
                "callback_parse_error_count": self._callback_diagnostics.parse_error_count,
                "callback_dispatch_error_count": self._callback_diagnostics.dispatch_error_count,
                "last_sanitized_callback_error": self._callback_diagnostics.last_sanitized_error,
                "sanitized_subscription_response": self._sanitized_subscription_response,
            }

    def _require_api(self) -> Any:
        if self._api is None:
            raise ProviderError("TDX Level1 provider is not initialized")
        return self._api

def normalize_tdx_level1_snapshot(
    payload: Any,
    *,
    requested_symbols: Sequence[str] = (),
    received_at: datetime | None = None,
) -> tuple[NormalizedLevel1Event, ...]:
    """Normalize supported TQCenter snapshot shapes without losing raw rows."""

    received = _shanghai_timestamp(received_at or datetime.now(SHANGHAI_TZ))
    requested = _canonical_symbols(requested_symbols)
    requested_set = set(requested)
    snapshot_rows = _snapshot_rows(payload)
    if len(requested) != 1 and any(
        _lookup(raw_row, _SYMBOL_FIELDS) in (None, "") and fallback_symbol in (None, "")
        for fallback_symbol, raw_row in snapshot_rows
    ):
        raise ProviderDataError(
            "TDX Level1 snapshot symbol binding is ambiguous without a symbol field"
        )
    events: list[NormalizedLevel1Event] = []
    for fallback_symbol, raw_row in snapshot_rows:
        row = dict(raw_row)
        symbol_value = _lookup(row, _SYMBOL_FIELDS)
        if symbol_value in (None, "") and fallback_symbol in (None, "") and len(requested) == 1:
            fallback_symbol = requested[0]
        symbol = canonicalize_tdx_level1_symbol(symbol_value if symbol_value not in (None, "") else fallback_symbol)
        if requested_set and symbol not in requested_set:
            continue
        last_price = _required_number(_lookup(row, _FIELD_ALIASES["last_price"]), "last_price")
        raw_volume = _optional_decimal(
            _lookup(row, _FIELD_ALIASES["cumulative_volume"]),
            "cumulative_volume",
        )
        raw_amount = _optional_decimal(
            _lookup(row, _FIELD_ALIASES["cumulative_amount"]),
            "cumulative_amount",
        )
        timestamp, timestamp_source = _snapshot_timestamp(row, received)
        try:
            events.append(
                NormalizedLevel1Event(
                    symbol=symbol,
                    timestamp=timestamp,
                    received_at=received,
                    last_price=last_price,
                    open=_optional_number(_lookup(row, _FIELD_ALIASES["open"]), "open"),
                    high=_optional_number(_lookup(row, _FIELD_ALIASES["high"]), "high"),
                    low=_optional_number(_lookup(row, _FIELD_ALIASES["low"]), "low"),
                    cumulative_volume_shares=_scaled_number(raw_volume, Decimal("100")),
                    cumulative_amount_cny=_scaled_number(raw_amount, Decimal("10000")),
                    average_price=_optional_number(
                        _lookup(row, _FIELD_ALIASES["average_price"]),
                        "average_price",
                    ),
                    buy1=_first_level_number(_lookup(row, _FIELD_ALIASES["buy1"]), "buy1"),
                    sell1=_first_level_number(_lookup(row, _FIELD_ALIASES["sell1"]), "sell1"),
                    now_volume_source_value=_optional_number(
                        _lookup(row, _FIELD_ALIASES["now_volume"]),
                        "now_volume",
                    ),
                    inside_volume_source_value=_optional_number(
                        _lookup(row, _FIELD_ALIASES["inside_volume"]),
                        "inside_volume",
                    ),
                    outside_volume_source_value=_optional_number(
                        _lookup(row, _FIELD_ALIASES["outside_volume"]),
                        "outside_volume",
                    ),
                    buy_volume_source_values=_number_levels(
                        _lookup(row, _FIELD_ALIASES["buy_volume_levels"]),
                        "buy_volume_levels",
                    ),
                    sell_volume_source_values=_number_levels(
                        _lookup(row, _FIELD_ALIASES["sell_volume_levels"]),
                        "sell_volume_levels",
                    ),
                    source_units=dict(_TDX_SOURCE_UNITS),
                    timestamp_source=timestamp_source,
                    raw_payload=row,
                )
            )
        except (TypeError, ValueError) as exc:
            raise ProviderDataError(f"invalid TDX Level1 snapshot for {symbol}: {exc}") from exc
    by_symbol: dict[str, NormalizedLevel1Event] = {}
    for event in events:
        prior = by_symbol.get(event.symbol)
        if prior is not None and prior != event:
            raise ProviderDataError(f"conflicting TDX Level1 rows for {event.symbol}")
        by_symbol[event.symbol] = event
    return tuple(by_symbol[symbol] for symbol in sorted(by_symbol))


def _validate_snapshot_return(payload: Any) -> None:
    if not isinstance(payload, Mapping):
        raise ProviderDataError("TDX get_market_snapshot must return a mapping")
    for _fallback_symbol, row in _snapshot_rows(payload):
        error_id = _lookup(row, ("ErrorId", "error_id"))
        if error_id not in (None, "") and str(error_id).strip() != "0":
            raise ProviderDataError(
                f"TDX get_market_snapshot returned ErrorId={str(error_id).strip()}"
            )


def _validate_snapshot_symbol_binding(payload: Mapping[str, Any], requested_symbol: str) -> None:
    rows = _snapshot_rows(payload)
    if len(rows) != 1:
        raise ProviderDataError(
            "TDX get_market_snapshot returned an ambiguous number of rows for one requested symbol"
        )
    fallback_symbol, row = rows[0]
    symbol_value = _lookup(row, _SYMBOL_FIELDS)
    if symbol_value in (None, ""):
        symbol_value = fallback_symbol
    if symbol_value in (None, ""):
        return  # the externally requested symbol is authoritative for this one-row response
    returned_symbol = canonicalize_tdx_level1_symbol(symbol_value)
    if returned_symbol != requested_symbol:
        raise ProviderDataError(
            f"TDX snapshot symbol {returned_symbol} does not match requested symbol {requested_symbol}"
        )


def normalize_tdx_historical_minute_bars(
    payload: Any,
    *,
    requested_symbols: Sequence[str],
) -> tuple[NormalizedIntradayBar, ...]:
    """Normalize field-oriented ``tq.get_market_data`` output into minute bars."""

    requested = _canonical_symbols(requested_symbols)
    if not requested:
        raise ValueError("requested_symbols must contain at least one symbol")
    if not isinstance(payload, Mapping):
        raise ProviderDataError("TDX historical minute data must be a field mapping")
    payload_fields = {_key_token(key): (str(key), value) for key, value in payload.items()}
    field_points: dict[str, dict[tuple[str, datetime], tuple[Any, Any]]] = {}
    for field in _HISTORICAL_MINUTE_FIELDS:
        found = payload_fields.get(_key_token(field))
        if found is None:
            raise ProviderDataError(f"TDX historical minute data is missing {field}")
        source_name, source_values = found
        field_points[field] = _historical_field_points(
            source_values,
            requested_symbols=requested,
            field_name=source_name,
        )

    keys = set().union(*(set(points) for points in field_points.values()))
    output = []
    for symbol, timestamp in sorted(keys, key=lambda item: (item[1], item[0])):
        missing = [
            field
            for field in _HISTORICAL_MINUTE_FIELDS
            if (symbol, timestamp) not in field_points[field]
        ]
        if missing:
            raise ProviderDataError(
                f"TDX historical minute row for {symbol} at {timestamp.isoformat()} "
                f"is missing fields: {', '.join(missing)}"
            )
        raw_values = {
            field: field_points[field][(symbol, timestamp)][0]
            for field in _HISTORICAL_MINUTE_FIELDS
        }
        raw_timestamp = field_points["Open"][(symbol, timestamp)][1]
        volume = _required_historical_decimal(raw_values["Volume"], "Volume")
        amount = _required_historical_decimal(raw_values["Amount"], "Amount")
        volume_shares = float(volume * Decimal("100"))
        amount_cny = float(amount * Decimal("10000"))
        average_price = amount_cny / volume_shares if volume_shares > 0 else None
        try:
            output.append(
                NormalizedIntradayBar(
                    symbol=symbol,
                    start=timestamp,
                    end=timestamp + timedelta(minutes=1),
                    interval_minutes=1,
                    open=_required_number(raw_values["Open"], "historical Open"),
                    high=_required_number(raw_values["High"], "historical High"),
                    low=_required_number(raw_values["Low"], "historical Low"),
                    close=_required_number(raw_values["Close"], "historical Close"),
                    volume=volume_shares,
                    amount=amount_cny,
                    average_price=average_price,
                    event_count=1,
                    raw_payload={
                        "timestamp": raw_timestamp,
                        **raw_values,
                        "source_units": {
                            "Volume": "lots_of_100_shares",
                            "Amount": "10000_cny",
                        },
                    },
                )
            )
        except (TypeError, ValueError) as exc:
            raise ProviderDataError(
                f"invalid TDX historical minute row for {symbol} at {timestamp.isoformat()}: {exc}"
            ) from exc
    return tuple(output)


def _snapshot_rows(payload: Any) -> tuple[tuple[str | None, Mapping[str, Any]], ...]:
    if payload is None:
        return ()
    if hasattr(payload, "to_dict") and not isinstance(payload, Mapping):
        try:
            payload = payload.to_dict("records")
        except TypeError:
            payload = payload.to_dict()
    if isinstance(payload, Mapping):
        if _looks_like_snapshot_row(payload):
            return ((None, payload),)
        rows = []
        for symbol, value in payload.items():
            if not isinstance(value, Mapping):
                raise ProviderDataError("TDX Level1 snapshot mapping values must be mappings")
            rows.append((str(symbol), value))
        return tuple(rows)
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        rows = []
        for value in payload:
            if not isinstance(value, Mapping):
                raise ProviderDataError("TDX Level1 snapshot rows must be mappings")
            rows.append((None, value))
        return tuple(rows)
    raise ProviderDataError("TDX Level1 snapshot must be a mapping, sequence, or dataframe-like object")


def _looks_like_snapshot_row(row: Mapping[str, Any]) -> bool:
    tokens = {_key_token(key) for key in row}
    expected = {_key_token(key) for key in (*_SYMBOL_FIELDS, *_FIELD_ALIASES["last_price"])}
    return bool(tokens & expected)


def _snapshot_timestamp(row: Mapping[str, Any], received_at: datetime) -> tuple[datetime, str]:
    combined = _lookup(row, _TIMESTAMP_FIELDS)
    if combined not in (None, ""):
        parsed = _parse_datetime(combined, received_at.date())
        if parsed is not None:
            return parsed, "provider"
    raw_date = _lookup(row, _DATE_FIELDS)
    raw_time = _lookup(row, _TIME_FIELDS)
    if raw_date not in (None, "") or raw_time not in (None, ""):
        parsed_date = _parse_date(raw_date) or received_at.date()
        parsed = _parse_datetime(raw_time, parsed_date)
        if parsed is not None:
            return parsed, "provider"
    return received_at, "collector"


def _parse_datetime(value: Any, fallback_date: date) -> datetime | None:
    if isinstance(value, datetime):
        return _shanghai_timestamp(value)
    if isinstance(value, time):
        return datetime.combine(fallback_date, value, tzinfo=value.tzinfo or SHANGHAI_TZ).astimezone(SHANGHAI_TZ)
    text = str(value).strip()
    if not text:
        return None
    digits = re.sub(r"\D", "", text)
    formats: tuple[tuple[str, str], ...] = (
        (digits, "%Y%m%d%H%M%S") if len(digits) == 14 else ("", ""),
        (digits, "%Y%m%d%H%M%S%f") if len(digits) in {17, 20} else ("", ""),
    )
    for candidate, fmt in formats:
        if candidate:
            try:
                return datetime.strptime(candidate, fmt).replace(tzinfo=SHANGHAI_TZ)
            except ValueError:
                pass
    if len(digits) <= 6 and digits:
        padded = digits.zfill(6)
        try:
            parsed_time = datetime.strptime(padded, "%H%M%S").time()
            return datetime.combine(fallback_date, parsed_time, tzinfo=SHANGHAI_TZ)
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _shanghai_timestamp(parsed)


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = re.sub(r"\D", "", str(value or ""))
    if len(text) != 8:
        return None
    try:
        return datetime.strptime(text, "%Y%m%d").date()
    except ValueError:
        return None


def _lookup(row: Mapping[str, Any], aliases: Sequence[str]) -> Any:
    normalized = {_key_token(key): value for key, value in row.items()}
    for alias in aliases:
        token = _key_token(alias)
        if token in normalized:
            return normalized[token]
    return None


def _key_token(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).strip().lower())


def _required_number(value: Any, field_name: str) -> float:
    result = _optional_number(value, field_name)
    if result is None or result <= 0:
        raise ProviderDataError(f"TDX Level1 {field_name} must be positive")
    return result


def _optional_number(value: Any, field_name: str) -> float | None:
    decimal_value = _optional_decimal(value, field_name)
    return None if decimal_value is None else float(decimal_value)


def _optional_decimal(value: Any, field_name: str) -> Decimal | None:
    if value is None or isinstance(value, bool) or (isinstance(value, str) and not value.strip()):
        return None
    try:
        result = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ProviderDataError(f"TDX Level1 {field_name} must be numeric") from exc
    if not result.is_finite() or result < 0:
        raise ProviderDataError(f"TDX Level1 {field_name} must be non-negative and finite")
    return result


def _scaled_number(value: Decimal | None, multiplier: Decimal) -> float | None:
    return None if value is None else float(value * multiplier)


def _first_level_number(value: Any, field_name: str) -> float | None:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        value = value[0] if value else None
    return _optional_number(value, field_name)


def _number_levels(value: Any, field_name: str) -> tuple[float, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ProviderDataError(f"TDX Level1 {field_name} must be a sequence")
    output = []
    for index, item in enumerate(value):
        numeric = _optional_number(item, f"{field_name}[{index}]")
        if numeric is None:
            raise ProviderDataError(f"TDX Level1 {field_name}[{index}] must be numeric")
        output.append(numeric)
    return tuple(output)


def _require_historical_minute_fields(fields: Sequence[str]) -> None:
    available = {_key_token(field) for field in fields}
    missing = [field for field in _HISTORICAL_MINUTE_FIELDS if _key_token(field) not in available]
    if missing:
        raise ValueError(
            "TDX historical one-minute fields must include: " + ", ".join(missing)
        )


def _historical_field_points(
    values: Any,
    *,
    requested_symbols: Sequence[str],
    field_name: str,
) -> dict[tuple[str, datetime], tuple[Any, Any]]:
    mapping = _data_mapping(values, field_name)
    requested = set(requested_symbols)
    output: dict[tuple[str, datetime], tuple[Any, Any]] = {}
    for outer_key, outer_value in mapping.items():
        outer_symbol = _try_historical_symbol(outer_key)
        if outer_symbol is not None:
            if outer_symbol not in requested:
                continue
            nested = _data_mapping(outer_value, field_name)
            for raw_timestamp, raw_value in nested.items():
                timestamp = _historical_timestamp(raw_timestamp, field_name)
                output[(outer_symbol, timestamp)] = (raw_value, raw_timestamp)
            continue

        timestamp = _try_historical_timestamp(outer_key)
        if timestamp is None:
            raise ProviderDataError(
                f"TDX historical {field_name} contains an unsupported index value"
            )
        nested = _optional_data_mapping(outer_value)
        if nested is None:
            if len(requested_symbols) != 1:
                raise ProviderDataError(
                    f"TDX historical {field_name} row does not identify a symbol"
                )
            output[(requested_symbols[0], timestamp)] = (outer_value, outer_key)
            continue
        for raw_symbol, raw_value in nested.items():
            symbol = canonicalize_tdx_level1_symbol(raw_symbol)
            if symbol in requested:
                output[(symbol, timestamp)] = (raw_value, outer_key)
    if not output:
        raise ProviderDataError(f"TDX historical {field_name} contains no requested rows")
    return output


def _data_mapping(value: Any, field_name: str) -> Mapping[Any, Any]:
    mapping = _optional_data_mapping(value)
    if mapping is None:
        raise ProviderDataError(
            f"TDX historical {field_name} must expose timestamp-indexed values"
        )
    return mapping


def _optional_data_mapping(value: Any) -> Mapping[Any, Any] | None:
    if isinstance(value, Mapping):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        converted = to_dict()
        if isinstance(converted, Mapping):
            return converted
    return None


def _try_historical_symbol(value: Any) -> str | None:
    try:
        return canonicalize_tdx_level1_symbol(value)
    except ProviderDataError:
        return None


def _historical_timestamp(value: Any, field_name: str) -> datetime:
    timestamp = _try_historical_timestamp(value)
    if timestamp is None:
        raise ProviderDataError(f"TDX historical {field_name} timestamp is invalid")
    return timestamp


def _try_historical_timestamp(value: Any) -> datetime | None:
    to_datetime = getattr(value, "to_pydatetime", None)
    if callable(to_datetime):
        value = to_datetime()
    if isinstance(value, datetime):
        return _shanghai_timestamp(value)
    text = str(value).strip()
    if not text:
        return None
    digits = re.sub(r"\D", "", text)
    timestamp_formats = (
        (12, "%Y%m%d%H%M"),
        (14, "%Y%m%d%H%M%S"),
        (17, "%Y%m%d%H%M%S%f"),
    )
    for length, fmt in timestamp_formats:
        if len(digits) == length:
            try:
                return datetime.strptime(digits, fmt).replace(tzinfo=SHANGHAI_TZ)
            except ValueError:
                pass
    if text.isdigit() and len(text) in {10, 13}:
        divisor = 1000 if len(text) == 13 else 1
        try:
            return datetime.fromtimestamp(int(text) / divisor, tz=SHANGHAI_TZ)
        except (OverflowError, OSError, ValueError):
            pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _shanghai_timestamp(parsed)


def _required_historical_decimal(value: Any, field_name: str) -> Decimal:
    result = _optional_decimal(value, f"historical {field_name}")
    if result is None:
        raise ProviderDataError(f"TDX historical {field_name} must be numeric")
    return result


def _remove_first_sys_path_entry(value: str) -> None:
    try:
        sys.path.remove(value)
    except ValueError:
        pass


def _sanitize_exception_message(value: Any) -> str:
    message = str(value).strip() or "no exception message"
    message = re.sub(
        r"(?i)\b(?:postgres(?:ql)?|https?|mysql|redis)://[^\s,;]+",
        "<redacted-uri>",
        message,
    )
    message = re.sub(
        r"(?i)\b(password|passwd|pwd|token|secret|api[_-]?key|dsn)\s*[:=]\s*[^\s,;]+",
        r"\1=<redacted>",
        message,
    )
    message = re.sub(r"(?<!\w)[A-Za-z]:\\[^\s\"']+", "<path>", message)
    message = re.sub(r"(?<!\w)/(?:[^/\s\"']+/)+[^\s\"']*", "<path>", message)
    return message[:1000]


def _canonical_symbols(symbols: Sequence[str]) -> tuple[str, ...]:
    output: list[str] = []
    for symbol in symbols:
        text = str(symbol).strip()
        if not text:
            continue
        try:
            output.append(canonicalize_tdx_level1_symbol(text))
        except ProviderDataError as exc:
            raise ProviderArgumentError(str(exc)) from exc
    return tuple(dict.fromkeys(output))


def _validate_plugin_query_arguments(
    *,
    operation: str,
    symbols: Sequence[str],
    collection_phase: str,
    reason: str | None,
) -> None:
    """Reject invalid plugin-boundary arguments before they reach tqcenter.

    The TDX TQ plugin prints ``入参不能为空`` and drops its connection when a
    call arrives with empty arguments. Validating here converts that opaque
    plugin storm into a structured, per-symbol contained ProviderArgumentError
    carrying operation, symbol, collection phase, and reason.
    """

    if not symbols:
        raise ProviderArgumentError(
            f"TDX {operation} skipped during {collection_phase}: "
            "no valid symbols supplied (raw symbols were empty)"
        )
    if reason is not None:
        raise ProviderArgumentError(
            f"TDX {operation} skipped during {collection_phase}: {reason} "
            f"for symbols {', '.join(symbols)}"
        )


def _require_non_empty_time_window(start_time: str, end_time: str) -> str | None:
    if not str(start_time or "").strip() or not str(end_time or "").strip():
        return "start_time and end_time must be non-empty"
    return None


def _require_non_empty_snapshot_fields(fields: Sequence[str]) -> str | None:
    for field in fields:
        if not str(field or "").strip():
            return "snapshot field names must be non-empty"
    return None


def canonicalize_tdx_level1_symbol(value: Any) -> str:
    text = str(value or "").strip().upper()
    if not text:
        raise ProviderDataError("TDX Level1 symbol is missing")
    if re.fullmatch(r"(?:SH|SZ|BJ)\d{6}", text):
        text = f"{text[2:]}.{text[:2]}"
    elif re.fullmatch(r"\d{6}\.(?:SH|SZ|BJ)", text):
        pass
    elif re.fullmatch(r"(?:SH|SZ|BJ)\.\d{6}", text):
        text = f"{text[3:]}.{text[:2]}"
    else:
        text = canonicalize_a_share_symbol(text)
    if not re.fullmatch(r"\d{6}\.(?:SH|SZ|BJ)", text):
        raise ProviderDataError(f"unsupported TDX Level1 symbol: {value}")
    return text


def _register_subscription_callback(
    callback: Callable[[Mapping[str, Any]], None],
    diagnostics: _CallbackDiagnostics,
) -> int:
    callback_id = next(_SUBSCRIPTION_CALLBACK_IDS)
    with _SUBSCRIPTION_CALLBACKS_LOCK:
        _SUBSCRIPTION_CALLBACKS[callback_id] = _CallbackRegistration(callback, diagnostics)
    return callback_id


def _unregister_subscription_callback(callback_id: int) -> None:
    with _SUBSCRIPTION_CALLBACKS_LOCK:
        _SUBSCRIPTION_CALLBACKS.pop(callback_id, None)


def _tdx_subscription_callback(payload: Any) -> None:
    """Normalize and contain the Windows ctypes callback boundary."""

    with _SUBSCRIPTION_CALLBACKS_LOCK:
        registrations = tuple(_SUBSCRIPTION_CALLBACKS.values())
        for registration in registrations:
            registration.diagnostics.callback_count += 1
    try:
        normalized = _normalize_tdx_callback_payload(payload)
    except BaseException as exc:
        sanitized = _safe_callback_error_message(exc)
        with _SUBSCRIPTION_CALLBACKS_LOCK:
            for registration in registrations:
                registration.diagnostics.parse_error_count += 1
                registration.diagnostics.last_sanitized_error = sanitized
        return
    for registration in registrations:
        try:
            registration.callback(normalized)
        except BaseException as exc:
            sanitized = _safe_callback_error_message(exc)
            with _SUBSCRIPTION_CALLBACKS_LOCK:
                registration.diagnostics.dispatch_error_count += 1
                registration.diagnostics.last_sanitized_error = sanitized


def _normalize_tdx_callback_payload(payload: Any) -> Mapping[str, Any]:
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, Mapping):
        raise TypeError("TDX callback payload must decode to a mapping")
    return dict(payload)


def _interpret_subscription_response(response: Any) -> str:
    if response is False:
        raise ProviderDataError("tqcenter.tq.subscribe_hq returned False")
    parsed = response
    if isinstance(parsed, bytes):
        parsed = parsed.decode("utf-8")
    if isinstance(parsed, str):
        try:
            parsed = json.loads(parsed)
        except json.JSONDecodeError as exc:
            raise ProviderDataError("tqcenter.tq.subscribe_hq returned malformed JSON") from exc
    if not isinstance(parsed, Mapping):
        raise ProviderDataError("tqcenter.tq.subscribe_hq must return a mapping or JSON mapping")
    error_id = parsed.get("ErrorId", parsed.get("error_id"))
    if error_id is None:
        raise ProviderDataError("tqcenter.tq.subscribe_hq response is missing ErrorId")
    if not _is_zero_error_id(error_id):
        raise ProviderDataError(
            f"tqcenter.tq.subscribe_hq returned ErrorId={str(error_id).strip()}"
        )
    message = str(parsed.get("Msg", "")).strip()
    summary = {
        "ErrorId": str(error_id).strip(),
        "Msg": _sanitize_exception_message(message) if message else "",
        "run_id": str(parsed.get("run_id", "")),
    }
    return json.dumps(summary, ensure_ascii=False, sort_keys=True)


def _is_zero_error_id(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        return Decimal(str(value).strip()) == Decimal("0")
    except (InvalidOperation, ValueError):
        return False


def _safe_callback_error_message(exc: BaseException) -> str:
    try:
        return _sanitize_exception_message(str(exc))
    except BaseException:
        return f"{type(exc).__name__}: callback boundary failure"


def _active_callback_registrations() -> int:
    with _SUBSCRIPTION_CALLBACKS_LOCK:
        return len(_SUBSCRIPTION_CALLBACKS)


def sanitize_tdx_error_message(value: Any) -> str:
    """Return the repository-safe representation used in runtime reports."""

    return _sanitize_exception_message(value)


def _shanghai_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=SHANGHAI_TZ)
    return value.astimezone(SHANGHAI_TZ)
