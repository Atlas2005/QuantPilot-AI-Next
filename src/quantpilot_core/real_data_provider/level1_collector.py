"""Level1 collector with baseline snapshots, subscriptions, and polling fallback."""

from __future__ import annotations

import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from quantpilot_core.real_data_provider.contracts import (
    Level1MarketDataProvider,
    NormalizedIntradayBar,
    NormalizedLevel1Event,
    ProviderArgumentError,
    ProviderDataError,
    ProviderError,
)
from quantpilot_core.real_data_provider.intraday_aggregation import MinuteBarAggregator
from quantpilot_core.real_data_provider.tdx_level1_adapter import (
    TDXOperationError,
    canonicalize_tdx_level1_symbol,
    sanitize_tdx_error_message,
)


class Level1MarketDataSink(Protocol):
    def persist_market_data(
        self,
        events: Sequence[NormalizedLevel1Event],
        bars: Sequence[NormalizedIntradayBar],
    ) -> None: ...


@dataclass(frozen=True)
class Level1CollectorReport:
    connection_status: str
    symbols: tuple[str, ...]
    event_count: int
    snapshot_count: int
    bar_count: int
    callback_count: int
    callback_parse_error_count: int
    callback_dispatch_error_count: int
    last_sanitized_callback_error: str | None
    quote_change_count: int
    polling_count: int
    deduplicated_count: int
    persisted_event_count: int
    persisted_bar_count: int
    storage_backend: str
    realtime_market_change_detected: bool
    subscription_attempted: bool
    subscription_succeeded: bool
    subscription_error_type: str | None
    sanitized_subscription_error: str | None
    sanitized_subscription_response: str | None
    polling_fallback_active: bool
    unsubscribe_attempted: bool
    unsubscribe_succeeded: bool
    unsubscribe_error_type: str | None
    sanitized_unsubscribe_error: str | None
    shadow: bool
    invalid_argument_count: int = 0
    no_data_count: int = 0
    provider_failure_count: int = 0
    reconnect_attempt_count: int = 0
    reconnect_success_count: int = 0
    symbols_skipped_count: int = 0
    last_sanitized_provider_error: str | None = None

    def as_dict(self) -> Mapping[str, Any]:
        return asdict(self)


class LiveLevel1Collector:
    """Collect normalized snapshots without signal or execution behavior."""

    def __init__(
        self,
        provider: Level1MarketDataProvider,
        symbols: Sequence[str],
        *,
        aggregator: MinuteBarAggregator | None = None,
        sink: Level1MarketDataSink | None = None,
        storage_backend: str | None = None,
        poll_interval_seconds: float = 1.0,
        shadow: bool = False,
        monotonic: Any = None,
        max_consecutive_retries: int = 3,
        retry_backoff_seconds: float = 1.0,
        retry_backoff_cap_seconds: float = 30.0,
        max_reconnect_attempts: int = 3,
        reconnect_backoff_seconds: float = 5.0,
    ) -> None:
        normalized = tuple(
            dict.fromkeys(
                canonicalize_tdx_level1_symbol(symbol)
                for symbol in symbols
                if str(symbol).strip()
            )
        )
        if not normalized:
            raise ValueError("symbols must contain at least one symbol")
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        self.provider = provider
        self.symbols = normalized
        self.aggregator = aggregator or MinuteBarAggregator()
        self.sink = sink
        self.storage_backend = storage_backend or _storage_backend_name(sink)
        self.poll_interval_seconds = float(poll_interval_seconds)
        self.shadow = bool(shadow)
        self.max_consecutive_retries = max(1, int(max_consecutive_retries))
        self.retry_backoff_seconds = max(0.0, float(retry_backoff_seconds))
        self.retry_backoff_cap_seconds = max(self.retry_backoff_seconds, float(retry_backoff_cap_seconds))
        self.max_reconnect_attempts = max(0, int(max_reconnect_attempts))
        self.reconnect_backoff_seconds = max(0.0, float(reconnect_backoff_seconds))
        self._monotonic = monotonic or time.monotonic
        self._stop = threading.Event()
        self._refresh_lock = threading.Lock()
        self._subscription: Any | None = None
        self._running = False
        self._closed = False
        self._connection_status = "not_initialized"
        self._active_connection_status = "not_initialized"
        self._callback_error: Exception | None = None
        self._last_event_keys: dict[str, tuple[Any, ...]] = {}
        self._events: list[NormalizedLevel1Event] = []
        self._bars: list[NormalizedIntradayBar] = []
        self._snapshot_count = 0
        self._callback_count = 0
        self._quote_change_count = 0
        self._polling_count = 0
        self._deduplicated_count = 0
        self._persisted_event_count = 0
        self._persisted_bar_count = 0
        self._subscription_attempted = False
        self._subscription_succeeded = False
        self._subscription_error_type: str | None = None
        self._sanitized_subscription_error: str | None = None
        self._unsubscribe_attempted = False
        self._unsubscribe_succeeded = False
        self._unsubscribe_error_type: str | None = None
        self._sanitized_unsubscribe_error: str | None = None
        self._invalid_argument_count = 0
        self._no_data_count = 0
        self._provider_failure_count = 0
        self._reconnect_attempt_count = 0
        self._reconnect_success_count = 0
        self._symbols_skipped_count = 0
        self._consecutive_failures = 0
        self._last_sanitized_provider_error: str | None = None

    @property
    def events(self) -> tuple[NormalizedLevel1Event, ...]:
        return tuple(self._events)

    @property
    def bars(self) -> tuple[NormalizedIntradayBar, ...]:
        return tuple(self._bars)

    @property
    def connection_status(self) -> str:
        return self._connection_status

    def start(self) -> None:
        if self._running:
            return
        if self._closed:
            raise RuntimeError("collector cannot be restarted after shutdown")
        self.provider.initialize()
        self._running = True
        # The initial snapshot uses the same classification, backoff, and
        # connection recovery as the poll loop: request errors skip without
        # touching the connection, no-data continues, and real provider
        # failures retry with backoff until the recovery budget is exhausted,
        # at which point the original error is raised instead of running on.
        self._initial_refresh()
        if self._subscription is None:
            self._subscribe()

    def _subscribe(self) -> None:
        self._subscription_attempted = True
        try:
            self._subscription = self.provider.subscribe_hq(self.symbols, self._on_refresh_notification)
            self._subscription_succeeded = True
            self._set_connection_status("subscribed")
        except ProviderError as exc:
            self._subscription = None
            cause = exc.__cause__ or exc
            self._subscription_error_type = type(cause).__name__
            self._sanitized_subscription_error = sanitize_tdx_error_message(str(cause))
            self._set_connection_status("polling_fallback")

    def run(self, duration_seconds: float) -> Level1CollectorReport:
        if duration_seconds < 0:
            raise ValueError("duration_seconds must be non-negative")
        started = self._monotonic()
        next_poll = started + self.poll_interval_seconds
        try:
            self.start()
            while not self._stop.is_set():
                if self._callback_error is not None:
                    if isinstance(self._callback_error, TDXOperationError):
                        raise self._callback_error
                    raise ProviderError("TDX Level1 callback refresh failed") from self._callback_error
                now = self._monotonic()
                if now - started >= duration_seconds:
                    break
                wait_seconds = min(max(0.0, next_poll - now), max(0.0, duration_seconds - (now - started)))
                self._stop.wait(wait_seconds)
                if self._stop.is_set():
                    break
                now = self._monotonic()
                if now >= next_poll:
                    self._polling_count += 1
                    self._refresh_with_resilience()
                    next_poll = self._monotonic() + self.poll_interval_seconds
        finally:
            self.shutdown()
        return self.report()

    def _initial_refresh(self) -> None:
        """Bounded initial snapshot with the same classification as polling.

        Loops with backoff until the first successful poll, or until the
        recovery budget is exhausted, in which case the original provider
        error is raised. Only ``ProviderArgumentError`` counts as an invalid
        argument; any other error propagates to the caller. No-data never
        retries and never touches the connection.
        """

        while True:
            try:
                events = self.refresh(self.symbols, count_as_change=False)
            except ProviderArgumentError as exc:
                self._invalid_argument_count += 1
                self._last_sanitized_provider_error = sanitize_tdx_error_message(str(exc))
                return
            except ProviderError as exc:
                self._provider_failure_count += 1
                self._consecutive_failures += 1
                self._last_sanitized_provider_error = sanitize_tdx_error_message(str(exc))
                delay = min(
                    self.retry_backoff_seconds * (2 ** (self._consecutive_failures - 1)),
                    self.retry_backoff_cap_seconds,
                )
                if self._consecutive_failures >= self.max_consecutive_retries:
                    if self._reconnect_attempt_count >= self.max_reconnect_attempts:
                        raise exc  # recovery budget exhausted: fail clearly
                    self._maybe_reconnect()
                    delay = self.reconnect_backoff_seconds
                self._stop.wait(delay)
                continue
            self._consecutive_failures = 0
            if not events:
                self._no_data_count += 1
            return

    def _refresh_with_resilience(self) -> None:
        """Poll with bounded backoff and connection recovery.

        No-data polls are normal and never reconnect. Only the narrow
        ``ProviderArgumentError`` counts as an invalid argument and is
        skipped without touching the connection; any other error propagates
        to the caller. A real provider failure triggers bounded backoff and,
        after consecutive retries, a bounded reconnect (close + initialize +
        re-subscribe).
        """

        try:
            events = self.refresh(self.symbols)
        except ProviderArgumentError as exc:
            self._invalid_argument_count += 1
            self._last_sanitized_provider_error = sanitize_tdx_error_message(str(exc))
            return
        except ProviderError as exc:
            self._provider_failure_count += 1
            self._consecutive_failures += 1
            self._last_sanitized_provider_error = sanitize_tdx_error_message(str(exc))
            delay = min(
                self.retry_backoff_seconds * (2 ** (self._consecutive_failures - 1)),
                self.retry_backoff_cap_seconds,
            )
            if self._consecutive_failures >= self.max_consecutive_retries:
                self._maybe_reconnect()
                delay = self.reconnect_backoff_seconds
            self._stop.wait(delay)
            return
        self._consecutive_failures = 0
        if not events:
            self._no_data_count += 1

    def _maybe_reconnect(self) -> None:
        if self._reconnect_attempt_count >= self.max_reconnect_attempts:
            return
        self._reconnect_attempt_count += 1
        try:
            self.provider.close()
        except Exception as exc:
            self._last_sanitized_provider_error = sanitize_tdx_error_message(str(exc))
        # The previous subscription belonged to the closed connection.
        self._subscription = None
        try:
            self.provider.initialize()
            self._consecutive_failures = 0
            self._reconnect_success_count += 1
            try:
                self._subscribe()
            except Exception as exc:
                # Polling fallback remains usable when re-subscription fails.
                self._last_sanitized_provider_error = sanitize_tdx_error_message(str(exc))
        except Exception as exc:
            self._last_sanitized_provider_error = sanitize_tdx_error_message(str(exc))

    def refresh(
        self,
        symbols: Sequence[str] | None = None,
        *,
        count_as_change: bool = True,
    ) -> tuple[NormalizedLevel1Event, ...]:
        requested = tuple(symbols or self.symbols)
        with self._refresh_lock:
            valid: list[str] = []
            for symbol in requested:
                try:
                    valid.append(canonicalize_tdx_level1_symbol(symbol))
                except ProviderDataError:
                    # Truly invalid input is counted per symbol and skipped;
                    # no-data polls must never inflate this counter.
                    self._symbols_skipped_count += 1
            events = self.provider.get_market_snapshot(valid) if valid else ()
            self._snapshot_count += 1
            accepted: list[NormalizedLevel1Event] = []
            completed_bars: list[NormalizedIntradayBar] = []
            allowed = set(self.symbols)
            for event in events:
                if event.symbol not in allowed:
                    continue
                try:
                    key = _event_key(event)
                    duplicate = self._last_event_keys.get(event.symbol) == key
                    if not duplicate:
                        self._last_event_keys[event.symbol] = key
                except Exception as exc:
                    raise TDXOperationError(
                        "snapshot_deduplication",
                        str(exc) or "snapshot deduplication failed",
                        requested_symbol=event.symbol,
                        api_call_completed=True,
                        raw_result=event.raw_payload,
                    ) from exc
                if duplicate:
                    self._deduplicated_count += 1
                    continue
                accepted.append(event)
                completed_bars.extend(self.aggregator.update(event))
            self._events.extend(accepted)
            self._bars.extend(completed_bars)
            if count_as_change:
                self._quote_change_count += len(accepted)
            self._persist(accepted, completed_bars)
            return tuple(accepted)

    def shutdown(self) -> None:
        if self._closed:
            return
        self._stop.set()
        first_error: Exception | None = None
        if self._subscription is not None:
            self._unsubscribe_attempted = True
            try:
                self.provider.unsubscribe_hq(self._subscription)
                self._unsubscribe_succeeded = True
            except Exception as exc:
                cause = exc.__cause__ or exc
                self._unsubscribe_error_type = type(cause).__name__
                self._sanitized_unsubscribe_error = sanitize_tdx_error_message(str(cause))
            self._subscription = None
        partial_bars = self.aggregator.flush()
        self._bars.extend(partial_bars)
        try:
            self._persist((), partial_bars)
        except Exception as exc:
            first_error = first_error or exc
        try:
            self.provider.close()
        except Exception as exc:
            first_error = first_error or exc
        self._running = False
        self._closed = True
        self._connection_status = "disconnected"
        if first_error is not None:
            raise first_error

    def report(self) -> Level1CollectorReport:
        callback_diagnostics = _callback_diagnostics(self.provider)
        return Level1CollectorReport(
            connection_status=self._active_connection_status,
            symbols=self.symbols,
            event_count=len(self._events),
            snapshot_count=self._snapshot_count,
            bar_count=len(self._bars),
            callback_count=int(callback_diagnostics.get("callback_count", self._callback_count)),
            callback_parse_error_count=int(
                callback_diagnostics.get("callback_parse_error_count", 0)
            ),
            callback_dispatch_error_count=int(
                callback_diagnostics.get("callback_dispatch_error_count", 0)
            ),
            last_sanitized_callback_error=callback_diagnostics.get(
                "last_sanitized_callback_error"
            ),
            quote_change_count=self._quote_change_count,
            polling_count=self._polling_count,
            deduplicated_count=self._deduplicated_count,
            persisted_event_count=self._persisted_event_count,
            persisted_bar_count=self._persisted_bar_count,
            storage_backend=self.storage_backend,
            realtime_market_change_detected=self._quote_change_count > 0,
            subscription_attempted=self._subscription_attempted,
            subscription_succeeded=self._subscription_succeeded,
            subscription_error_type=self._subscription_error_type,
            sanitized_subscription_error=self._sanitized_subscription_error,
            sanitized_subscription_response=callback_diagnostics.get(
                "sanitized_subscription_response"
            ),
            polling_fallback_active=self._active_connection_status == "polling_fallback",
            unsubscribe_attempted=self._unsubscribe_attempted,
            unsubscribe_succeeded=self._unsubscribe_succeeded,
            unsubscribe_error_type=self._unsubscribe_error_type,
            sanitized_unsubscribe_error=self._sanitized_unsubscribe_error,
            shadow=self.shadow,
            invalid_argument_count=self._invalid_argument_count,
            no_data_count=self._no_data_count,
            provider_failure_count=self._provider_failure_count,
            reconnect_attempt_count=self._reconnect_attempt_count,
            reconnect_success_count=self._reconnect_success_count,
            symbols_skipped_count=self._symbols_skipped_count,
            last_sanitized_provider_error=self._last_sanitized_provider_error,
        )

    def _on_refresh_notification(self, payload: Mapping[str, Any]) -> None:
        if not self._running or self._stop.is_set():
            return
        self._callback_count += 1
        error_id = str(payload.get("ErrorId", payload.get("error_id", "0"))).strip()
        if error_id not in {"", "0"}:
            return
        raw_symbol = payload.get("Code", payload.get("code"))
        requested: Sequence[str] = self.symbols
        if raw_symbol not in (None, ""):
            normalized = canonicalize_tdx_level1_symbol(raw_symbol)
            if normalized not in set(self.symbols):
                return
            requested = (normalized,)
        try:
            self.refresh(requested)
        except Exception as exc:
            self._callback_error = exc
            self._stop.set()

    def _persist(
        self,
        events: Sequence[NormalizedLevel1Event],
        bars: Sequence[NormalizedIntradayBar],
    ) -> None:
        if self.sink is None or (not events and not bars):
            return
        self.sink.persist_market_data(events, bars)
        self._persisted_event_count += len(events)
        self._persisted_bar_count += len(bars)

    def _set_connection_status(self, status: str) -> None:
        self._connection_status = status
        self._active_connection_status = status


def _event_key(event: NormalizedLevel1Event) -> tuple[Any, ...]:
    provider_timestamp = event.timestamp.isoformat() if event.timestamp_source == "provider" else None
    return (
        event.symbol,
        provider_timestamp,
        event.last_price,
        event.open,
        event.high,
        event.low,
        event.cumulative_volume_shares,
        event.cumulative_amount_cny,
        event.average_price,
        event.buy1,
        event.sell1,
        event.now_volume_source_value,
        event.inside_volume_source_value,
        event.outside_volume_source_value,
        event.buy_volume_source_values,
        event.sell_volume_source_values,
    )


def _storage_backend_name(sink: Level1MarketDataSink | None) -> str:
    if sink is None:
        return "none"
    name = type(sink).__name__.lower()
    if "postgres" in name:
        return "postgresql"
    if "memory" in name:
        return "memory"
    return name


def _callback_diagnostics(provider: Level1MarketDataProvider) -> Mapping[str, Any]:
    diagnostics = getattr(provider, "callback_diagnostics", None)
    if not callable(diagnostics):
        return {}
    try:
        value = diagnostics()
    except Exception:
        return {}
    return value if isinstance(value, Mapping) else {}
