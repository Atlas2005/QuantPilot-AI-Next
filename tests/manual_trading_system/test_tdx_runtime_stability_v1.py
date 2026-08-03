"""Targeted runtime-stability tests for the TDX intraday path.

Covers the TQ empty-argument reconnect storm, single-instance runtime lock,
Ctrl+C cancellation, and TongDaXin V6.06 formula compatibility. No real
TongDaXin, TQ plugin, network, DeepSeek, broker, or account is used.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

import pytest

from quantpilot_core.manual_trading_system import (
    AfterCloseConfig,
    IntradayConfig,
    RuntimeLockError,
    SystemDirLock,
    install_marker_bundle,
    run_after_close,
    run_intraday,
)
from quantpilot_core.manual_trading_system import system as manual_system_module
from quantpilot_core.manual_trading_system import runtime_lock as runtime_lock_module
from quantpilot_core.manual_trading_system.markers import FORMULA_SOURCE
from quantpilot_core.real_data_provider import (
    Level1CollectorReport,
    LiveLevel1Collector,
    NormalizedLevel1Event,
    ProviderArgumentError,
    ProviderDataError,
    ProviderError,
    ProviderName,
    TDXLevel1Provider,
    normalize_tdx_level1_snapshot,
)
from quantpilot_core.tdx_manual_signal_bridge.tq_visibility import (
    build_transition_warning_payloads,
    publish_transition_warnings,
)
from tests.manual_trading_system.test_manual_trading_system_v1 import (
    _production_input,
)

import scripts.run_quantpilot_manual_system_v1 as manual_cli


SHANGHAI = ZoneInfo("Asia/Shanghai")


def _production_input_for(
    path: Path,
    *,
    decision: str,
    execution: str,
    symbols: tuple[str, ...] = ("000001.SZ", "600519.SH"),
) -> Path:
    previous = f"{int(decision[8:10]) - 1:02d}"
    rows = []
    for offset, symbol in enumerate(symbols):
        rows.extend(
            [
                {
                    "symbol": symbol,
                    "date": f"{decision[:8]}{previous}",
                    "open": 9.8 + offset,
                    "high": 10.1 + offset,
                    "low": 9.7 + offset,
                    "close": 9.9 + offset,
                    "volume": 10000,
                },
                {
                    "symbol": symbol,
                    "date": decision,
                    "open": 9.9 + offset,
                    "high": 10.2 + offset,
                    "low": 9.8 + offset,
                    "close": 10.0 + offset,
                    "volume": 11000,
                },
            ]
        )
    payload = {
        "symbols": list(symbols),
        "bars": rows,
        "information_signals": [
            {
                "signal": {"signal_id": "known-at-close"},
                "available_at": f"{decision}T14:00:00+08:00",
            }
        ],
        "information_provenance": {
            "daily_production_input_v1": {
                "decision_session": decision,
                "future_market_rows_serialized": 0,
                "selected_scores": {symbol: 0.9 - index * 0.1 for index, symbol in enumerate(symbols)},
            }
        },
        "quant_firm_context": {
            "daily_production_input_v1": {
                "decision_session": decision,
                "execution_session": execution,
            }
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# TDX adapter: empty arguments never reach the TQ plugin boundary
# ---------------------------------------------------------------------------


class _TQApi:
    def __init__(self) -> None:
        self.initialize_calls = 0
        self.snapshot_calls: list[tuple[str, list[str]]] = []
        self.market_data_calls: list[Mapping[str, Any]] = []
        self.subscribe_calls: list[list[str]] = []
        self.unsubscribe_calls: list[list[str]] = []

    def initialize(self, initialization_path: str) -> None:
        self.initialize_calls += 1

    def get_market_snapshot(self, *, stock_code: str, field_list: list[str]) -> dict[str, Any]:
        self.snapshot_calls.append((stock_code, field_list))
        return {"Code": stock_code, "Now": "10.00"}

    def get_market_data(self, **kwargs: Any) -> dict[str, Any]:
        self.market_data_calls.append(kwargs)
        return {}

    def subscribe_hq(self, *, stock_list: list[str], callback: Any) -> dict[str, Any]:
        self.subscribe_calls.append(stock_list)
        return {"ErrorId": 0}

    def unsubscribe_hq(self, *, stock_list: list[str]) -> None:
        self.unsubscribe_calls.append(stock_list)


def _provider_with(api: _TQApi, tdx_user_dir: Path) -> TDXLevel1Provider:
    tdx_user_dir.mkdir(parents=True, exist_ok=True)
    (tdx_user_dir / "tqcenter.py").write_text("# runtime marker\n", encoding="utf-8")
    return TDXLevel1Provider(
        tdx_user_dir,
        module_loader=lambda _name: type("Module", (), {"tq": api})(),
        platform_system=lambda: "Windows",
    )


def test_empty_symbol_is_filtered_before_plugin_call(tmp_path: Path) -> None:
    api = _TQApi()
    provider = _provider_with(api, tmp_path)
    provider.initialize()

    events = provider.get_market_snapshot(("", "000001.SZ"))

    assert [item.symbol for item in events] == ["000001.SZ"]
    assert api.snapshot_calls == [("000001.SZ", [])]


def test_only_empty_symbols_raise_before_plugin_call(tmp_path: Path) -> None:
    api = _TQApi()
    provider = _provider_with(api, tmp_path)
    provider.initialize()

    with pytest.raises(ProviderArgumentError, match="no valid symbols supplied"):
        provider.get_market_snapshot(("", "  "))

    assert api.snapshot_calls == []


def test_invalid_symbol_does_not_close_shared_adapter(tmp_path: Path) -> None:
    api = _TQApi()
    provider = _provider_with(api, tmp_path)
    provider.initialize()

    with pytest.raises(ProviderArgumentError, match="unsupported TDX Level1 symbol"):
        provider.get_market_snapshot(("not-a-symbol",))

    # The shared adapter stays healthy and serves the next request.
    events = provider.get_market_snapshot(("000001.SZ",))
    assert [item.symbol for item in events] == ["000001.SZ"]
    assert provider.initialized is True


def test_empty_history_time_window_rejected_before_plugin_call(tmp_path: Path) -> None:
    api = _TQApi()
    provider = _provider_with(api, tmp_path)
    provider.initialize()

    with pytest.raises(ProviderArgumentError, match="start_time and end_time must be non-empty"):
        provider.get_historical_intraday_bars(
            ("000001.SZ",),
            period="1m",
            fields=("Open", "High", "Low", "Close", "Volume", "Amount"),
            start_time="",
            end_time="",
            count=20,
            dividend_type="none",
            fill_data=False,
        )

    assert api.market_data_calls == []


def test_adapter_close_is_idempotent_and_reuses_one_connection(tmp_path: Path) -> None:
    api = _TQApi()
    provider = _provider_with(api, tmp_path)
    provider.initialize()
    subscription = provider.subscribe_hq(("000001.SZ",), lambda _payload: None)
    provider.get_market_snapshot(("000001.SZ",))
    provider.get_market_snapshot(("600519.SH",))

    provider.close()
    provider.close()

    assert api.initialize_calls == 1  # one connection, reused across polls
    assert len(api.unsubscribe_calls) == 1  # close happened exactly once
    assert provider.initialized is False


# ---------------------------------------------------------------------------
# Collector: no-data and invalid arguments never reconnect; real failures do
# ---------------------------------------------------------------------------


class _CollectorProvider:
    def __init__(
        self,
        *,
        fail_mode: str = "none",
        failure_burst: int = 0,
        recover_after_burst: bool = False,
        initial_ok: bool = False,
    ) -> None:
        self.fail_mode = fail_mode
        self.failure_burst = failure_burst
        self.recover_after_burst = recover_after_burst
        self.initial_ok = initial_ok
        self.initialize_calls = 0
        self.close_calls = 0
        self.snapshot_calls = 0
        self.subscribe_calls = 0

    def initialize(self) -> None:
        self.initialize_calls += 1

    def close(self) -> None:
        self.close_calls += 1

    def subscribe_hq(self, symbols: Sequence[str], callback: Any) -> Any:
        self.subscribe_calls += 1
        return object()

    def unsubscribe_hq(self, subscription: Any) -> None:
        return None

    def callback_diagnostics(self) -> Mapping[str, Any]:
        return {}

    def get_market_snapshot(self, symbols: Sequence[str]) -> tuple[NormalizedLevel1Event, ...]:
        self.snapshot_calls += 1
        if self.initial_ok and self.snapshot_calls == 1:
            return ()
        if self.failure_burst > 0:
            self.failure_burst -= 1
            if self.fail_mode == "provider":
                raise ProviderError("provider transport failure")
            raise ProviderArgumentError("TDX get_market_snapshot skipped: invalid request")
        if self.fail_mode == "provider":
            if self.recover_after_burst:
                return ()
            raise ProviderError("provider transport failure")
        if self.fail_mode == "invalid":
            raise ProviderArgumentError("TDX get_market_snapshot skipped: invalid request")
        if self.fail_mode == "value_error":
            raise ValueError("unexpected local error")
        return ()


def _collector(provider: _CollectorProvider, **kwargs: Any) -> LiveLevel1Collector:
    settings: dict[str, Any] = {
        "poll_interval_seconds": 0.001,
        "max_consecutive_retries": 2,
        "retry_backoff_seconds": 0.001,
        "retry_backoff_cap_seconds": 0.005,
        "max_reconnect_attempts": 1,
        "reconnect_backoff_seconds": 0.001,
    }
    settings.update(kwargs)
    return LiveLevel1Collector(provider, ("000001.SZ",), **settings)


def test_no_data_poll_is_normal_and_never_reconnects() -> None:
    provider = _CollectorProvider()
    collector = _collector(provider)

    report = collector.run(0.01)

    assert report.no_data_count >= 1
    assert report.provider_failure_count == 0
    assert report.reconnect_attempt_count == 0
    assert report.invalid_argument_count == 0
    assert provider.initialize_calls == 1  # only the start-time initialize
    assert provider.close_calls == 1  # only the shutdown close


def test_invalid_argument_skips_poll_without_closing_or_reconnecting() -> None:
    provider = _CollectorProvider(fail_mode="invalid", initial_ok=True)
    collector = _collector(provider)

    report = collector.run(0.01)

    assert report.invalid_argument_count >= 1
    assert report.provider_failure_count == 0
    assert report.reconnect_attempt_count == 0
    assert provider.initialize_calls == 1
    assert provider.close_calls == 1  # shutdown only; polls never closed it


def test_initial_request_error_is_tolerated_without_closing_connection() -> None:
    provider = _CollectorProvider(fail_mode="invalid")
    collector = _collector(provider)

    report = collector.run(0.01)

    assert report.invalid_argument_count >= 1
    assert report.provider_failure_count == 0
    assert report.reconnect_attempt_count == 0
    assert provider.initialize_calls == 1
    assert provider.close_calls == 1  # shutdown only; request errors never closed it


def test_plain_value_error_propagates_and_is_not_invalid_argument() -> None:
    provider = _CollectorProvider(fail_mode="value_error")
    collector = _collector(provider)

    with pytest.raises(ValueError, match="unexpected local error"):
        collector._refresh_with_resilience()

    report = collector.report()
    assert report.invalid_argument_count == 0
    assert report.provider_failure_count == 0
    assert report.reconnect_attempt_count == 0


def test_plain_value_error_propagates_from_initial_refresh() -> None:
    provider = _CollectorProvider(fail_mode="value_error")
    collector = _collector(provider)

    with pytest.raises(ValueError, match="unexpected local error"):
        collector.start()

    assert collector.report().invalid_argument_count == 0


def test_initial_provider_failure_is_bounded_and_fails_clearly() -> None:
    provider = _CollectorProvider(fail_mode="provider")
    collector = _collector(provider)

    with pytest.raises(ProviderError, match="provider transport failure"):
        collector.run(0.02)

    assert collector.report().reconnect_attempt_count == 1
    assert collector.report().reconnect_success_count == 1
    assert collector.report().provider_failure_count >= 2
    assert provider.initialize_calls == 2  # start + reconnect before failing


def test_no_data_polls_never_inflate_symbols_skipped_count() -> None:
    provider = _CollectorProvider()
    collector = LiveLevel1Collector(
        provider,
        ("000001.SZ", "000002.SZ", "000003.SZ", "600000.SH", "600519.SH", "601318.SH"),
        poll_interval_seconds=0.001,
    )

    for _ in range(10):
        collector._refresh_with_resilience()

    report = collector.report()
    assert report.no_data_count == 10
    assert report.symbols_skipped_count == 0


def test_invalid_symbol_input_counts_skip_without_calling_provider() -> None:
    provider = _CollectorProvider()
    collector = _collector(provider)

    events = collector.refresh(("", "not-a-symbol", "000001.SZ"))

    assert events == ()
    assert collector.report().symbols_skipped_count == 2
    assert provider.snapshot_calls == 1
    assert provider.close_calls == 0


def test_real_adapter_request_error_is_invalid_argument_not_provider_failure(
    tmp_path: Path,
) -> None:
    """Integration: real TDXLevel1Provider -> LiveLevel1Collector.

    An invalid snapshot field configuration makes the real adapter raise
    ProviderArgumentError on every poll. It must count as an invalid
    argument, never as a provider failure, and never close the adapter.
    """
    tdx_dir = tmp_path / "tdx"
    tdx_dir.mkdir(parents=True, exist_ok=True)
    (tdx_dir / "tqcenter.py").write_text("# runtime marker\n", encoding="utf-8")
    api = _TQApi()
    provider = TDXLevel1Provider(
        tdx_dir,
        module_loader=lambda _name: type("Module", (), {"tq": api})(),
        platform_system=lambda: "Windows",
        snapshot_fields=("",),
    )
    collector = LiveLevel1Collector(
        provider,
        ("000001.SZ",),
        poll_interval_seconds=0.001,
        max_consecutive_retries=2,
        retry_backoff_seconds=0.001,
        retry_backoff_cap_seconds=0.005,
        max_reconnect_attempts=1,
        reconnect_backoff_seconds=0.001,
    )

    collector.start()

    assert collector.report().invalid_argument_count == 1
    assert collector.report().provider_failure_count == 0
    assert collector.report().reconnect_attempt_count == 0
    assert api.snapshot_calls == []  # the plugin was never reached
    assert provider.initialized is True  # the adapter was never closed
    collector.shutdown()


def test_provider_failure_triggers_bounded_reconnect_with_backoff() -> None:
    provider = _CollectorProvider(fail_mode="provider", initial_ok=True)
    collector = _collector(provider)

    report = collector.run(0.02)

    assert report.provider_failure_count >= 2
    assert report.reconnect_attempt_count == 1  # bounded: max_reconnect_attempts=1
    assert report.reconnect_success_count == 1
    assert provider.initialize_calls == 2  # start + one reconnect
    assert provider.close_calls == 2  # reconnect close + shutdown close


def test_success_resets_consecutive_failure_counter_between_bursts() -> None:
    provider = _CollectorProvider(
        fail_mode="provider", failure_burst=2, recover_after_burst=True, initial_ok=True
    )
    collector = _collector(provider, max_consecutive_retries=3)

    report = collector.run(0.02)

    # First burst of two failures recovers before max_consecutive_retries,
    # so no reconnect happens; the counter was reset by the successful poll.
    assert report.provider_failure_count == 2
    assert report.reconnect_attempt_count == 0
    assert provider.initialize_calls == 1


def test_collector_shutdown_is_idempotent() -> None:
    provider = _CollectorProvider()
    collector = _collector(provider)

    collector.start()
    collector.shutdown()
    collector.shutdown()

    assert provider.close_calls == 1
    # The report keeps the last active connection status (existing semantics).
    assert collector.report().connection_status == "subscribed"


def test_collector_report_new_fields_have_legacy_positional_defaults() -> None:
    legacy = Level1CollectorReport(
        "disconnected", ("000001.SZ",), 0, 1, 0, 0, 0, 0, None, 0, 1, 0, 0, 0,
        "memory", False, False, False, None, None, None, False,
        False, False, None, None, False,
    )

    assert legacy.invalid_argument_count == 0
    assert legacy.no_data_count == 0
    assert legacy.provider_failure_count == 0
    assert legacy.reconnect_attempt_count == 0
    assert legacy.reconnect_success_count == 0
    assert legacy.symbols_skipped_count == 0
    assert legacy.last_sanitized_provider_error is None


# ---------------------------------------------------------------------------
# run_intraday: derived history window, runtime lock, Ctrl+C shutdown
# ---------------------------------------------------------------------------


class _IntradayProvider:
    provider_name = ProviderName.TDX_LEVEL1

    def __init__(self, *, raise_on_snapshot: BaseException | None = None) -> None:
        self.initialize_calls = 0
        self.close_calls = 0
        self.history_calls: list[tuple[tuple[str, ...], Mapping[str, Any]]] = []
        self._raise_on_snapshot = raise_on_snapshot

    def initialize(self) -> None:
        self.initialize_calls += 1

    def get_historical_intraday_bars(self, symbols: Sequence[str], **kwargs: Any):
        self.history_calls.append((tuple(symbols), dict(kwargs)))
        return ()

    def get_market_snapshot(self, symbols: Sequence[str]):
        if self._raise_on_snapshot is not None:
            raise self._raise_on_snapshot
        return ()

    def subscribe_hq(self, symbols: Sequence[str], callback: Any) -> object:
        return object()

    def unsubscribe_hq(self, subscription: Any) -> None:
        return None

    def close(self) -> None:
        self.close_calls += 1

    def callback_diagnostics(self) -> Mapping[str, Any]:
        return {}


def _ready_system_dir(tmp_path: Path) -> Path:
    root = tmp_path / "system"
    input_path = _production_input(tmp_path / "input.json")
    run_after_close(AfterCloseConfig(input_path, root, live_ai=False))
    return root


def test_run_intraday_derives_live_window_up_to_current_minute(
    tmp_path: Path,
) -> None:
    root = _ready_system_dir(tmp_path)
    provider = _IntradayProvider()

    run_intraday(
        IntradayConfig(root, "D:/tongdaxin/PYPlugins/user", duration_seconds=0, publish_to_tq=False),
        provider=provider,
        clock=lambda: datetime(2026, 8, 4, 11, 10, 37, tzinfo=SHANGHAI),
    )

    assert provider.history_calls
    _, kwargs = provider.history_calls[0]
    assert kwargs["start_time"] == "20260803093000"
    assert kwargs["end_time"] == "20260804111000"  # latest completed minute


def test_live_window_spans_decision_and_execution_sessions(
    tmp_path: Path,
) -> None:
    root = tmp_path / "system"
    input_path = _production_input_for(
        tmp_path / "input.json",
        decision="2026-07-31",
        execution="2026-08-03",
    )
    run_after_close(AfterCloseConfig(input_path, root, live_ai=False))
    provider = _IntradayProvider()

    run_intraday(
        IntradayConfig(root, "D:/tongdaxin/PYPlugins/user", duration_seconds=0, publish_to_tq=False),
        provider=provider,
        clock=lambda: datetime(2026, 8, 3, 11, 10, 37, tzinfo=SHANGHAI),
    )

    _, kwargs = provider.history_calls[0]
    assert kwargs["start_time"] == "20260731093000"  # decision session prior context
    assert kwargs["end_time"] == "20260803111000"  # execution session current minute
    assert kwargs["end_time"] <= "20260803111000"
    assert kwargs["start_time"] <= "20260803093000" <= kwargs["end_time"]


def test_run_intraday_explicit_times_are_passed_through(tmp_path: Path) -> None:
    root = _ready_system_dir(tmp_path)
    provider = _IntradayProvider()

    run_intraday(
        IntradayConfig(
            root, "D:/tongdaxin/PYPlugins/user",
            duration_seconds=0, publish_to_tq=False,
            start_time="20260803100000", end_time="20260803110000",
        ),
        provider=provider,
    )

    _, kwargs = provider.history_calls[0]
    assert kwargs["start_time"] == "20260803100000"
    assert kwargs["end_time"] == "20260803110000"


@pytest.mark.parametrize(
    "now_compact,expected_end",
    [
        # pre-open: end is the decision session close, never a future minute
        ("20260803085959", "20260731150000"),
        # morning: latest completed minute
        ("20260803100037", "20260803100000"),
        ("20260803113000", "20260803113000"),
        # lunch: the last completed morning minute, never lunch/future data
        ("20260803113500", "20260803113000"),
        # afternoon: latest completed minute
        ("20260803130000", "20260803130000"),
        ("20260803143005", "20260803143000"),
        # post-close: clamped to the execution session close
        ("20260803150000", "20260803150000"),
        ("20260803153000", "20260803150000"),
    ],
)
def test_live_historical_end_session_boundaries(
    now_compact: str, expected_end: str
) -> None:
    now = datetime.strptime(now_compact, "%Y%m%d%H%M%S").replace(tzinfo=SHANGHAI)
    end = manual_system_module._live_historical_end("20260803", "20260731", now)
    assert end == expected_end


def test_run_intraday_pre_open_window_uses_decision_session_close(
    tmp_path: Path,
) -> None:
    root = tmp_path / "system"
    input_path = _production_input_for(
        tmp_path / "input.json",
        decision="2026-07-31",
        execution="2026-08-03",
    )
    run_after_close(AfterCloseConfig(input_path, root, live_ai=False))
    provider = _IntradayProvider()

    run_intraday(
        IntradayConfig(root, "D:/tongdaxin/PYPlugins/user", duration_seconds=0, publish_to_tq=False),
        provider=provider,
        clock=lambda: datetime(2026, 8, 3, 8, 59, 59, tzinfo=SHANGHAI),
    )

    _, kwargs = provider.history_calls[0]
    assert kwargs["start_time"] == "20260731093000"
    assert kwargs["end_time"] == "20260731150000"  # not a future execution minute


@pytest.mark.parametrize(
    "start_time,end_time,match",
    [
        ("20260803100000", "", "requires both start_time and end_time"),
        ("", "20260803100000", "requires both start_time and end_time"),
        ("2026080310000", "20260803110000", "14-digit YYYYMMDDHHMMSS"),
        ("20260803110000", "20260803100000", "start_time must not be later"),
    ],
)
def test_explicit_partial_or_invalid_window_is_structured_request_error(
    tmp_path: Path, start_time: str, end_time: str, match: str
) -> None:
    root = _ready_system_dir(tmp_path)
    provider = _IntradayProvider()

    with pytest.raises(ProviderArgumentError, match=match):
        run_intraday(
            IntradayConfig(
                root, "D:/tongdaxin/PYPlugins/user",
                duration_seconds=0, publish_to_tq=False,
                start_time=start_time, end_time=end_time,
            ),
            provider=provider,
        )

    assert provider.history_calls == []  # rejected before any plugin call


def test_second_intraday_instance_for_same_system_dir_fails_fast(
    tmp_path: Path,
) -> None:
    root = _ready_system_dir(tmp_path)
    held = SystemDirLock(root)
    held.acquire()
    try:
        with pytest.raises(RuntimeLockError, match=f"owner pid={os.getpid()}"):
            run_intraday(
                IntradayConfig(root, "D:/tongdaxin/PYPlugins/user", duration_seconds=0, publish_to_tq=False),
                provider=_IntradayProvider(),
            )
    finally:
        held.release()

    # After release the same directory is usable again.
    run_intraday(
        IntradayConfig(root, "D:/tongdaxin/PYPlugins/user", duration_seconds=0, publish_to_tq=False),
        provider=_IntradayProvider(),
    )


def test_stale_lock_from_dead_process_is_recovered(tmp_path: Path) -> None:
    import socket

    root = _ready_system_dir(tmp_path)
    lock = SystemDirLock(root)
    lock.acquire()
    dead_pid = _dead_pid()
    lock.release()
    lock_path = root / ".qp_intraday.lock"
    lock_path.write_text(
        json.dumps({
            "pid": str(dead_pid),
            "started_at": "2026-08-03T00:00:00+00:00",
            "host": socket.gethostname(),
            "nonce": "stale-nonce",
        }),
        encoding="utf-8",
    )
    _age_lock_file(lock_path, seconds=120)

    run_intraday(
        IntradayConfig(root, "D:/tongdaxin/PYPlugins/user", duration_seconds=0, publish_to_tq=False),
        provider=_IntradayProvider(),
    )
    assert not lock_path.exists()  # released by the run


def test_partially_written_lock_is_not_stolen(tmp_path: Path) -> None:
    root = tmp_path / "system"
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / ".qp_intraday.lock"
    now = datetime.now(timezone.utc)
    lock_path.write_bytes(b'{"pid": "1", "non')  # torn write
    lock = SystemDirLock(root, clock=lambda: now, grace_seconds=30)

    with pytest.raises(RuntimeLockError, match="unreadable"):
        lock.acquire()

    assert lock_path.exists()  # never stolen while the write is fresh


def test_torn_lock_older_than_grace_is_recovered(tmp_path: Path) -> None:
    root = tmp_path / "system"
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / ".qp_intraday.lock"
    lock_path.write_bytes(b"not-json-at-all")
    now = datetime(2026, 8, 3, 10, 0, tzinfo=timezone.utc)
    _age_lock_file(lock_path, seconds=120, now=now)
    lock = SystemDirLock(root, clock=lambda: now, grace_seconds=30)

    lock.acquire()
    assert lock_path.exists()
    lock.release()
    assert not lock_path.exists()


def test_foreign_host_lock_is_never_deleted(tmp_path: Path) -> None:
    root = _ready_system_dir(tmp_path)
    lock_path = root / ".qp_intraday.lock"
    lock_path.write_text(
        json.dumps({
            "pid": str(_dead_pid()),
            "host": "other-pc",
            "nonce": "foreign",
            "started_at": "2026-08-03T00:00:00+00:00",
        }),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeLockError, match="on host other-pc"):
        SystemDirLock(root).acquire()

    assert lock_path.exists()


def test_release_never_deletes_another_tokens_lock(tmp_path: Path) -> None:
    import socket

    root = tmp_path / "system"
    lock = SystemDirLock(root)
    lock.acquire()
    lock_path = root / ".qp_intraday.lock"
    lock_path.write_text(
        json.dumps({
            "pid": str(os.getpid()),
            "nonce": "different-token",
            "host": socket.gethostname(),
        }),
        encoding="utf-8",
    )

    lock.release()

    assert lock_path.exists()  # token mismatch: not our lock anymore
    lock_path.unlink()


def test_pid_reuse_detected_via_process_start_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runtime_lock_module, "_WINDOWS", False)
    monkeypatch.setattr(runtime_lock_module, "_posix_pid_alive", lambda pid: True)
    monkeypatch.setattr(
        runtime_lock_module,
        "_process_start_identity",
        lambda pid: "linux-starttime:999",
    )

    reused = {"pid": "1234", "process_start_identity": "linux-starttime:111"}
    assert runtime_lock_module._owner_alive(reused) is False  # pid reused -> stale
    same_process = {"pid": "1234", "process_start_identity": "linux-starttime:999"}
    assert runtime_lock_module._owner_alive(same_process) is True


def test_two_process_single_instance_smoke(tmp_path: Path) -> None:
    """Real two-process smoke of the single-instance contract (POSIX path).

    Process A holds the lock and stays alive; process B must fail fast on
    the same directory; A must survive (the owner is never terminated); after
    A exits normally the lock is released. The Windows equivalent runs via
    scripts/windows/quantpilot-single-instance-smoke.ps1.
    """
    root = tmp_path / "smoke"
    root.mkdir()
    repo = Path(__file__).resolve().parents[2]
    code_a = f"""
import sys, time
sys.path.insert(0, {str(repo / "src")!r})
from quantpilot_core.manual_trading_system import SystemDirLock
lock = SystemDirLock({str(root)!r})
lock.acquire()
print("ACQUIRED", flush=True)
time.sleep(3)
lock.release()
print("RELEASED", flush=True)
"""
    code_b = f"""
import sys
sys.path.insert(0, {str(repo / "src")!r})
from quantpilot_core.manual_trading_system import RuntimeLockError, SystemDirLock
try:
    SystemDirLock({str(root)!r}).acquire()
except RuntimeLockError:
    print("REJECTED", flush=True)
    sys.exit(3)
print("UNEXPECTED_ACQUIRE", flush=True)
sys.exit(2)
"""
    lock_path = root / ".qp_intraday.lock"
    proc_a = subprocess.Popen(
        [sys.executable, "-c", code_a],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        deadline = time.monotonic() + 30
        acquired = False
        while time.monotonic() < deadline:
            if "ACQUIRED" in proc_a.stdout.readline():
                acquired = True
                break
            if proc_a.poll() is not None:
                raise AssertionError(
                    f"owner process A exited early: {proc_a.stderr.read()}"
                )
        assert acquired, "owner process A never acquired the lock"

        result = subprocess.run(
            [sys.executable, "-c", code_b],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 3
        assert "REJECTED" in result.stdout
        assert proc_a.poll() is None, "owner process A was terminated"
        assert lock_path.exists()
    except BaseException:
        if proc_a.poll() is None:
            proc_a.terminate()
        proc_a.wait(timeout=10)
        raise

    proc_a.wait(timeout=30)  # A must exit normally on its own
    remaining = proc_a.stdout.read()
    assert "RELEASED" in remaining
    assert not lock_path.exists()  # released on normal exit


def test_windows_stale_recovery_never_calls_os_kill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import socket

    root = _ready_system_dir(tmp_path)
    lock_path = root / ".qp_intraday.lock"
    lock_path.write_text(
        json.dumps({
            "pid": str(_dead_pid()),
            "host": socket.gethostname(),
            "nonce": "stale",
            "started_at": "2026-08-03T00:00:00+00:00",
        }),
        encoding="utf-8",
    )
    _age_lock_file(lock_path, seconds=120)

    def fail_if_called(pid: int, sig: int) -> None:
        raise AssertionError("os.kill must never be used on Windows")

    monkeypatch.setattr(runtime_lock_module, "_WINDOWS", True)
    monkeypatch.setattr(runtime_lock_module.os, "kill", fail_if_called)
    monkeypatch.setattr(runtime_lock_module, "_windows_pid_alive", lambda pid: False)
    # Identity probing uses ctypes on the simulated Windows platform; make it
    # unavailable so only the liveness probe decides staleness.
    monkeypatch.setattr(runtime_lock_module, "_process_start_identity", lambda pid: "")

    lock = SystemDirLock(root)
    lock.acquire()
    lock.release()


def test_windows_probe_uses_openprocess_getexitcode_and_never_terminates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ctypes as real_ctypes

    calls: list[tuple[Any, ...]] = []

    class _FakeFunction:
        def __init__(self, name: str, impl: Any) -> None:
            self.name = name
            self._impl = impl
            self.argtypes = None
            self.restype = None

        def __call__(self, *args: Any) -> Any:
            return self._impl(*args)

    class _FakeKernel32:
        def __init__(self, handle: Any, exit_code: int, *, open_error: int = 0) -> None:
            self.handle = handle
            self.exit_code = exit_code
            self.open_error = open_error
            self.OpenProcess = _FakeFunction("OpenProcess", self._open)
            self.GetExitCodeProcess = _FakeFunction("GetExitCodeProcess", self._get_exit_code)
            self.GetProcessTimes = _FakeFunction("GetProcessTimes", self._get_process_times)
            self.CloseHandle = _FakeFunction("CloseHandle", self._close)

        def _get_process_times(self, *args: Any) -> bool:
            calls.append(("GetProcessTimes", *args))
            return False

        def _open(self, access: int, inherit: bool, pid: int) -> Any:
            calls.append(("OpenProcess", access, inherit, pid))
            return self.handle

        def _get_exit_code(self, handle: Any, out: Any) -> bool:
            calls.append(("GetExitCodeProcess", handle))
            out.contents.value = self.exit_code
            return True

        def _close(self, handle: Any) -> None:
            calls.append(("CloseHandle", handle))

    monkeypatch.setattr(
        real_ctypes,
        "WinDLL",
        lambda _name, **_kwargs: _FakeKernel32(handle=777, exit_code=259),
        raising=False,
    )
    monkeypatch.setattr(real_ctypes, "get_last_error", lambda: 0, raising=False)

    assert runtime_lock_module._windows_pid_alive(4242) is True
    assert ("OpenProcess", 0x1000 | 0x00100000, False, 4242) in calls
    assert ("GetExitCodeProcess", 777) in calls
    assert ("CloseHandle", 777) in calls
    assert not any(call[0] == "TerminateProcess" for call in calls)

    monkeypatch.setattr(
        real_ctypes,
        "WinDLL",
        lambda _name, **_kwargs: _FakeKernel32(handle=777, exit_code=0),
    )
    assert runtime_lock_module._windows_pid_alive(4243) is False


def test_windows_kernel32_prototypes_are_abi_correct() -> None:
    import ctypes as real_ctypes
    from ctypes import wintypes

    from quantpilot_core.manual_trading_system.runtime_lock import (
        _FILETIME,
        _configure_kernel32_prototypes,
    )

    class _FakeFunction:
        def __init__(self, name: str) -> None:
            self.name = name
            self.argtypes = None
            self.restype = None

    from types import SimpleNamespace

    kernel32 = SimpleNamespace(
        OpenProcess=_FakeFunction("OpenProcess"),
        GetExitCodeProcess=_FakeFunction("GetExitCodeProcess"),
        GetProcessTimes=_FakeFunction("GetProcessTimes"),
        CloseHandle=_FakeFunction("CloseHandle"),
    )
    _configure_kernel32_prototypes(kernel32)

    assert kernel32.OpenProcess.argtypes == [
        wintypes.DWORD, wintypes.BOOL, wintypes.DWORD,
    ]
    # OpenProcess.restype must be a pointer-sized HANDLE, never the c_int
    # ctypes default (which truncates 64-bit handles).
    assert kernel32.OpenProcess.restype is wintypes.HANDLE
    assert real_ctypes.sizeof(wintypes.HANDLE) == real_ctypes.sizeof(real_ctypes.c_void_p)
    assert kernel32.GetExitCodeProcess.argtypes == [
        wintypes.HANDLE, real_ctypes.POINTER(wintypes.DWORD),
    ]
    assert kernel32.GetExitCodeProcess.restype is wintypes.BOOL
    times = kernel32.GetProcessTimes.argtypes
    assert times[0] is wintypes.HANDLE
    assert all(arg == real_ctypes.POINTER(_FILETIME) for arg in times[1:])
    assert kernel32.GetProcessTimes.restype is wintypes.BOOL
    assert kernel32.CloseHandle.argtypes == [wintypes.HANDLE]
    assert kernel32.CloseHandle.restype is wintypes.BOOL
    assert [name for name, _ in _FILETIME._fields_] == [
        "dwLowDateTime", "dwHighDateTime",
    ]
    assert all(field_type is wintypes.DWORD for _, field_type in _FILETIME._fields_)


def test_different_system_dirs_run_independently(tmp_path: Path) -> None:
    first = _ready_system_dir(tmp_path / "one")
    second = _ready_system_dir(tmp_path / "two")
    first_lock = SystemDirLock(first)
    first_lock.acquire()
    try:
        run_intraday(
            IntradayConfig(second, "D:/tongdaxin/PYPlugins/user", duration_seconds=0, publish_to_tq=False),
            provider=_IntradayProvider(),
        )
    finally:
        first_lock.release()


def test_keyboard_interrupt_closes_provider_once_and_releases_lock(
    tmp_path: Path,
) -> None:
    root = _ready_system_dir(tmp_path)
    provider = _IntradayProvider(raise_on_snapshot=KeyboardInterrupt())

    with pytest.raises(KeyboardInterrupt):
        run_intraday(
            IntradayConfig(root, "D:/tongdaxin/PYPlugins/user", duration_seconds=0, publish_to_tq=False),
            provider=provider,
        )

    assert provider.close_calls == 1  # collector shutdown owns the single close
    assert not (root / ".qp_intraday.lock").exists()  # lock released
    # The same system directory is immediately usable after cancellation.
    run_intraday(
        IntradayConfig(root, "D:/tongdaxin/PYPlugins/user", duration_seconds=0, publish_to_tq=False),
        provider=_IntradayProvider(),
    )


def test_cli_keyboard_interrupt_returns_130_without_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _raise_cancel(_args: Any) -> Mapping[str, Any]:
        raise KeyboardInterrupt()

    monkeypatch.setattr(manual_cli, "_run_intraday", _raise_cancel)
    exit_code = manual_cli.main([
        "intraday", "--tdx-user-dir", "D:/tongdaxin/PYPlugins/user",
    ])
    stdout = capsys.readouterr().out

    assert exit_code == 130
    assert json.loads(stdout)["status"] == "cancelled"
    assert "Traceback" not in stdout


def test_windows_wrapper_recognizes_exit_130_as_cancellation() -> None:
    text = Path("scripts/windows/manual_system_common_v1.ps1").read_text(encoding="ascii")
    assert "$exitCode -eq 130" in text
    assert "cancelled by user" in text
    # Every other non-zero exit code still surfaces as a failure.
    assert 'if ($exitCode -ne 0)' in text
    assert "throw \"QuantPilot manual system failed with exit code $exitCode.\"" in text


# ---------------------------------------------------------------------------
# TongDaXin V6.06 formula compatibility
# ---------------------------------------------------------------------------


def test_formula_bundle_has_no_overlong_or_dynamic_segments(tmp_path: Path) -> None:
    bundle = install_marker_bundle(tmp_path / "bundle")
    formula = Path(bundle["formula_path"]).read_text(encoding="utf-8")

    assert "INVALIDATION_LINE" not in formula
    assert "INV_LINE" in formula
    assert "NUMTOSTR" not in formula
    assert "' +" not in formula  # no string-addition DRAWTEXT concatenation


def test_formula_identifiers_respect_tdx_15_character_limit() -> None:
    identifiers = set()
    for line in FORMULA_SOURCE.splitlines():
        match = re.match(r"^([A-Z_][A-Z_0-9]*)\s*(?::=|:)", line.strip())
        if match:
            identifiers.add(match.group(1))
    assert "INVALIDATION_LINE" not in identifiers
    assert identifiers
    for identifier in identifiers:
        assert len(identifier) <= 15, identifier


def test_formula_keeps_fixed_labels_and_signal_tq_mapping() -> None:
    assert "'买'" in FORMULA_SOURCE
    assert "'持'" in FORMULA_SOURCE
    assert "'弱'" in FORMULA_SOURCE
    assert "'卖'" in FORMULA_SOURCE
    assert "'失效'" in FORMULA_SOURCE
    assert "INVALIDATION := SIGNALS_TQ(9,0);" in FORMULA_SOURCE
    assert "INV_LINE: IF(VALID, INVALIDATION, DRAWNULL)" in FORMULA_SOURCE


def test_install_readme_documents_v606_compatibility(tmp_path: Path) -> None:
    bundle = install_marker_bundle(tmp_path / "bundle")
    readme = Path(bundle["acceptance_procedure_path"]).read_text(encoding="utf-8")
    assert "V6.06" in readme
    assert "INV_LINE" in readme
    assert "NUMTOSTR" in readme


def test_signal_tq_binding_and_marker_bundle_generation_unchanged(tmp_path: Path) -> None:
    bundle = install_marker_bundle(tmp_path / "bundle")
    assert bundle["marker_adapter_initialized"] is True
    assert bundle["broker_calls"] == bundle["order_submission_calls"] == 0
    formula = Path(bundle["formula_path"]).read_text(encoding="utf-8")
    # The formula binds the 14 mapped SIGNALS_TQ columns (1..5, 7..10, 12..16).
    assert formula.count("SIGNALS_TQ(") == 14
    assert "SIGNALS_TQ(16,0)" in formula


# ---------------------------------------------------------------------------
# send_warn empty-argument guard
# ---------------------------------------------------------------------------


def test_transition_warning_with_empty_timestamp_is_skipped_and_audited() -> None:
    payloads, skipped = build_transition_warning_payloads(
        [
            {
                "schema_version": "tdx_prediction_signal_v1",
                "symbol": "000002.SZ",
                "state": "ENTRY",
            }
        ],
        include_skip_diagnostics=True,
    )
    assert payloads == ()
    assert skipped[0]["reason"] == "empty_timestamp"
    assert skipped[0]["raw_symbol"] == "000002.SZ"
    assert skipped[0]["has_timestamp"] is False


def test_transition_warning_with_timestamp_is_published() -> None:
    payloads = build_transition_warning_payloads(
        [
            {
                "schema_version": "tdx_prediction_signal_v1",
                "symbol": "000002.SZ",
                "state": "ENTRY",
                "timestamp": "2026-08-04T10:00:00+08:00",
            }
        ]
    )
    assert len(payloads) == 1
    assert payloads[0]["timestamp"] == "2026-08-04T10:00:00+08:00"


class _WarnApi:
    def __init__(self) -> None:
        self.calls: list[Mapping[str, Any]] = []

    def send_warn(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"ErrorId": 0, "Msg": "ok"}


def test_skipped_warnings_are_exposed_in_publication_report() -> None:
    api = _WarnApi()
    report = publish_transition_warnings(
        [
            {
                "schema_version": "tdx_prediction_signal_v1",
                "signal_id": "empty-symbol",
                "symbol": "",
                "state": "ENTRY",
            },
            {
                "schema_version": "tdx_prediction_signal_v1",
                "signal_id": "no-timestamp",
                "symbol": "000002.SZ",
                "state": "ENTRY",
            },
            {
                "schema_version": "tdx_prediction_signal_v1",
                "signal_id": "good",
                "symbol": "000002.SZ",
                "state": "ENTRY",
                "timestamp": "2026-08-04T10:00:00+08:00",
            },
        ],
        api=api,
    )

    assert report["warning_count"] == 1
    assert report["skipped_warning_count"] == 2
    reasons = {item["reason"] for item in report["skipped_warning_diagnostics"]}
    assert reasons == {"empty_symbol", "empty_timestamp"}
    assert len(api.calls) == 1  # the TQ plugin only saw the valid warning
    assert api.calls[0]["timestamp"] == "2026-08-04T10:00:00+08:00"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _age_lock_file(path: Path, *, seconds: float, now: datetime | None = None) -> None:
    reference = now or datetime.now(timezone.utc)
    os.utime(path, (reference.timestamp() - seconds, reference.timestamp() - seconds))


def _dead_pid() -> int:
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait()
    assert process.returncode == 0
    return process.pid
