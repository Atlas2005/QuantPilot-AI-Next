"""Optional Windows runtime adapter for TDX TQCenter Level1 snapshots."""

from __future__ import annotations

import importlib
import platform
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from quantpilot_core.data_provider_normalization import canonicalize_a_share_symbol
from quantpilot_core.real_data_provider.contracts import (
    NormalizedLevel1Event,
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


@dataclass(frozen=True)
class _TDXSubscription:
    entries: tuple[tuple[str, Any], ...]


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
    ) -> None:
        self.tdx_user_dir = Path(tdx_user_dir)
        self._module_loader = module_loader or importlib.import_module
        self._platform_system = platform_system or platform.system
        self._clock = clock or (lambda: datetime.now(SHANGHAI_TZ))
        self._api: Any | None = None
        self._path_inserted = False
        self._subscriptions: list[_TDXSubscription] = []

    @property
    def initialized(self) -> bool:
        return self._api is not None

    def initialize(self) -> None:
        if self.initialized:
            return
        if self._platform_system() != "Windows":
            raise ProviderDependencyError("TDX Level1 is available only on Windows")
        if not self.tdx_user_dir.is_dir():
            raise ProviderDependencyError(f"TDX user directory not found: {self.tdx_user_dir}")
        module_path = self.tdx_user_dir / "tqcenter.py"
        if not module_path.is_file():
            raise ProviderDependencyError(f"tqcenter.py not found in TDX user directory: {module_path}")
        user_dir = str(self.tdx_user_dir)
        if user_dir not in sys.path:
            sys.path.insert(0, user_dir)
            self._path_inserted = True
        try:
            module = self._module_loader("tqcenter")
        except Exception as exc:
            self._remove_runtime_path()
            raise ProviderDependencyError(f"unable to import tqcenter from {module_path}") from exc
        api = getattr(module, "tq", module)
        missing = tuple(
            name
            for name in ("initialize", "get_market_snapshot", "subscribe_hq", "unsubscribe_hq")
            if not callable(getattr(api, name, None))
        )
        if missing:
            self._remove_runtime_path()
            raise ProviderDependencyError(f"tqcenter is missing required Level1 functions: {', '.join(missing)}")
        try:
            api.initialize()
        except Exception as exc:
            self._remove_runtime_path()
            raise ProviderError("tqcenter Level1 initialization failed") from exc
        self._api = api

    def get_market_snapshot(self, symbols: Sequence[str]) -> tuple[NormalizedLevel1Event, ...]:
        api = self._require_api()
        requested = _canonical_symbols(symbols)
        if not requested:
            raise ValueError("symbols must contain at least one symbol")
        received_at = _shanghai_timestamp(self._clock())
        try:
            raw = api.get_market_snapshot(list(requested))
        except Exception as exc:
            raise ProviderError("tqcenter get_market_snapshot failed") from exc
        return normalize_tdx_level1_snapshot(raw, requested_symbols=requested, received_at=received_at)

    def subscribe_hq(
        self,
        symbols: Sequence[str],
        callback: Callable[[Mapping[str, Any]], None],
    ) -> Any:
        api = self._require_api()
        requested = _canonical_symbols(symbols)
        if not requested:
            raise ValueError("symbols must contain at least one symbol")
        if not callable(callback):
            raise TypeError("callback must be callable")
        entries = []
        try:
            for symbol in requested:
                entries.append((symbol, api.subscribe_hq(symbol, callback)))
        except Exception as exc:
            for symbol, handle in entries:
                try:
                    api.unsubscribe_hq(_unsubscribe_target(symbol, handle))
                except Exception:
                    pass
            raise ProviderError("tqcenter subscribe_hq failed") from exc
        subscription = _TDXSubscription(tuple(entries))
        self._subscriptions.append(subscription)
        return subscription

    def unsubscribe_hq(self, subscription: Any) -> None:
        api = self._require_api()
        try:
            _unsubscribe(api, subscription)
        except Exception as exc:
            raise ProviderError("tqcenter unsubscribe_hq failed") from exc
        self._subscriptions = [item for item in self._subscriptions if item != subscription]

    def close(self) -> None:
        api = self._api
        first_error: Exception | None = None
        if api is not None:
            for subscription in tuple(self._subscriptions):
                try:
                    _unsubscribe(api, subscription)
                except Exception as exc:  # shutdown still releases local runtime state
                    first_error = first_error or exc
        self._subscriptions.clear()
        self._api = None
        self._remove_runtime_path()
        if first_error is not None:
            raise ProviderError("tqcenter unsubscribe_hq failed during shutdown") from first_error

    def _require_api(self) -> Any:
        if self._api is None:
            raise ProviderError("TDX Level1 provider is not initialized")
        return self._api

    def _remove_runtime_path(self) -> None:
        user_dir = str(self.tdx_user_dir)
        if self._path_inserted:
            try:
                sys.path.remove(user_dir)
            except ValueError:
                pass
        self._path_inserted = False


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
    events: list[NormalizedLevel1Event] = []
    for fallback_symbol, raw_row in _snapshot_rows(payload):
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


def _canonical_symbols(symbols: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(canonicalize_tdx_level1_symbol(symbol) for symbol in symbols if str(symbol).strip()))


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


def _unsubscribe(api: Any, subscription: Any) -> None:
    entries = subscription.entries if isinstance(subscription, _TDXSubscription) else (("", subscription),)
    first_error: Exception | None = None
    for symbol, handle in entries:
        try:
            api.unsubscribe_hq(_unsubscribe_target(symbol, handle))
        except Exception as exc:
            first_error = first_error or exc
    if first_error is not None:
        raise first_error


def _unsubscribe_target(symbol: str, handle: Any) -> Any:
    return symbol if handle is None or isinstance(handle, bool) else handle


def _shanghai_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=SHANGHAI_TZ)
    return value.astimezone(SHANGHAI_TZ)
