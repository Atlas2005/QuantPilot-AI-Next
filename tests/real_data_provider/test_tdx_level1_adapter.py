from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

import pytest

from quantpilot_core.continuous_paper import InMemoryReportingStore
from quantpilot_core.real_data_provider import (
    LiveLevel1Collector,
    NormalizedLevel1Event,
    ProviderError,
    TDXLevel1Provider,
    normalize_tdx_level1_snapshot,
)


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")

REAL_TDX_LEVEL1_SNAPSHOT = {
    "ItemNum": "4644",
    "LastClose": "11.61",
    "Open": "11.50",
    "Max": "11.63",
    "Min": "11.28",
    "Now": "11.63",
    "Volume": "2024978",
    "NowVol": "41230",
    "Amount": "231883.98",
    "Inside": "1002155",
    "Outside": "1022824",
    "TickDiff": "0.00",
    "InOutFlag": "2",
    "Jjjz": "0.00",
    "Buyp": ["11.62", "0.00", "0.00", "0.00", "0.00"],
    "Buyv": ["1526", "0", "0", "0", "0"],
    "Sellp": ["11.63", "0.00", "0.00", "0.00", "0.00"],
    "Sellv": ["5329", "0", "0", "0", "0"],
    "UpHome": "0",
    "DownHome": "0",
    "Before5MinNow": "11.61",
    "Average": "11.45",
    "XsFlag": "2",
    "Zangsu": "0.17",
    "ZAFPre3": "3.84",
    "ErrorId": "0",
}


def _time(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 8, 3, hour, minute, second, tzinfo=SHANGHAI_TZ)


def _event(*, price: float = 10.0, volume: float = 100.0, timestamp: datetime | None = None) -> NormalizedLevel1Event:
    observed = timestamp or _time(10, 0)
    return NormalizedLevel1Event(
        symbol="000001.SZ",
        timestamp=observed,
        received_at=observed,
        last_price=price,
        open=9.9,
        high=max(price, 10.2),
        low=min(price, 9.8),
        cumulative_volume_shares=volume,
        cumulative_amount_cny=volume * price,
        average_price=price,
        buy1=price - 0.01,
        sell1=price + 0.01,
        inside_volume_source_value=40.0,
        outside_volume_source_value=60.0,
        raw_payload={"Code": "000001.SZ", "LastPrice": price},
    )


def test_snapshot_normalization_preserves_raw_payload_and_shanghai_time() -> None:
    raw = {
        "Code": "000001.SZ",
        "Date": "20260803",
        "Time": "10:01:02",
        "LastPrice": "10.25",
        "Open": 10.0,
        "High": 10.4,
        "Low": 9.9,
        "Volume": 1200,
        "Amount": 12240,
        "AveragePrice": 10.2,
        "BidPrice1": 10.24,
        "AskPrice1": 10.25,
        "InsideVolume": 500,
        "OutsideVolume": 700,
    }
    event = normalize_tdx_level1_snapshot(raw, received_at=_time(10, 1, 5))[0]

    assert event.symbol == "000001.SZ"
    assert event.timestamp.isoformat() == "2026-08-03T10:01:02+08:00"
    assert event.last_price == 10.25
    assert event.buy1 == 10.24
    assert event.sell1 == 10.25
    assert event.cumulative_volume_shares == 120_000
    assert event.cumulative_amount_cny == 122_400_000
    assert event.inside_volume_source_value == 500
    assert event.outside_volume_source_value == 700
    assert event.raw_payload == raw


def test_verified_tdx_snapshot_contract_normalizes_units_and_preserves_raw_payload() -> None:
    event = normalize_tdx_level1_snapshot(
        REAL_TDX_LEVEL1_SNAPSHOT,
        requested_symbols=("000001.SZ",),
        received_at=_time(18, 0),
    )[0]

    assert event.symbol == "000001.SZ"
    assert (event.last_price, event.open, event.high, event.low) == (11.63, 11.50, 11.63, 11.28)
    assert (event.buy1, event.sell1, event.average_price) == (11.62, 11.63, 11.45)
    assert event.cumulative_volume_shares == 202_497_800
    assert event.cumulative_amount_cny == 2_318_839_800
    assert event.now_volume_source_value == 41_230
    assert event.inside_volume_source_value == 1_002_155
    assert event.outside_volume_source_value == 1_022_824
    assert event.buy_volume_source_values == (1526.0, 0.0, 0.0, 0.0, 0.0)
    assert event.sell_volume_source_values == (5329.0, 0.0, 0.0, 0.0, 0.0)
    assert event.source_units == {
        "Volume": "lots_of_100_shares",
        "Amount": "10000_cny",
        "NowVol": "unconfirmed_tdx_source_unit",
        "Buyv": "unconfirmed_tdx_source_unit",
        "Sellv": "unconfirmed_tdx_source_unit",
        "Inside": "unconfirmed_tdx_source_unit",
        "Outside": "unconfirmed_tdx_source_unit",
    }
    assert event.raw_payload == REAL_TDX_LEVEL1_SNAPSHOT
    derived_vwap = event.cumulative_amount_cny / event.cumulative_volume_shares
    assert derived_vwap == pytest.approx(event.average_price, abs=0.01)


def test_tdx_unit_conversion_multiplies_decimal_source_values_before_float_conversion() -> None:
    raw = {"Now": "1.00", "Volume": "0.01", "Amount": "0.0001"}
    event = normalize_tdx_level1_snapshot(
        raw,
        requested_symbols=("000001.SZ",),
        received_at=_time(18, 0),
    )[0]

    assert event.cumulative_volume_shares == 1.0
    assert event.cumulative_amount_cny == 1.0


class _TQCenterApi:
    def __init__(self) -> None:
        self.initialized = False
        self.callback = None
        self.subscribed = []
        self.unsubscribed = []

    def initialize(self) -> None:
        self.initialized = True

    def get_market_snapshot(self, symbols):
        return {
            symbol: {
                "DateTime": "20260803100102",
                "LastPrice": 10.25,
                "Open": 10.0,
                "High": 10.4,
                "Low": 9.9,
                "Volume": 1200,
                "Amount": 12240,
            }
            for symbol in symbols
        }

    def subscribe_hq(self, symbol, callback):
        self.callback = callback
        self.subscribed.append(symbol)
        return f"subscription-{symbol}"

    def unsubscribe_hq(self, subscription):
        self.unsubscribed.append(subscription)


def test_provider_imports_injected_tqcenter_only_during_initialize(tmp_path: Path) -> None:
    (tmp_path / "tqcenter.py").write_text("# runtime marker\n", encoding="utf-8")
    api = _TQCenterApi()
    imports = []
    provider = TDXLevel1Provider(
        tmp_path,
        module_loader=lambda name: imports.append(name) or api,
        platform_system=lambda: "Windows",
        clock=lambda: _time(10, 1, 5),
    )

    assert imports == []
    provider.initialize()
    events = provider.get_market_snapshot(("000001.SZ",))
    provider.close()

    assert imports == ["tqcenter"]
    assert api.initialized is True
    assert events[0].symbol == "000001.SZ"


def test_provider_subscribes_and_unsubscribes_each_explicit_symbol(tmp_path: Path) -> None:
    (tmp_path / "tqcenter.py").write_text("# runtime marker\n", encoding="utf-8")
    api = _TQCenterApi()
    provider = TDXLevel1Provider(
        tmp_path,
        module_loader=lambda _name: api,
        platform_system=lambda: "Windows",
    )
    provider.initialize()

    subscription = provider.subscribe_hq(("SZ000001", "SH600000"), lambda _payload: None)
    provider.unsubscribe_hq(subscription)
    provider.close()

    assert api.subscribed == ["000001.SZ", "600000.SH"]
    assert api.unsubscribed == ["subscription-000001.SZ", "subscription-600000.SH"]


class _CollectorProvider:
    def __init__(self, snapshots: Sequence[Sequence[NormalizedLevel1Event]], *, subscribe_error: bool = False) -> None:
        self.snapshots = list(snapshots)
        self.subscribe_error = subscribe_error
        self.callback = None
        self.subscription = object()
        self.initialized = False
        self.unsubscribed = False
        self.closed = False

    def initialize(self) -> None:
        self.initialized = True

    def get_market_snapshot(self, symbols: Sequence[str]) -> tuple[NormalizedLevel1Event, ...]:
        if not self.snapshots:
            return ()
        return tuple(self.snapshots.pop(0))

    def subscribe_hq(self, symbols: Sequence[str], callback) -> Any:
        if self.subscribe_error:
            raise ProviderError("subscription unavailable")
        self.callback = callback
        return self.subscription

    def unsubscribe_hq(self, subscription: Any) -> None:
        assert subscription is self.subscription
        self.unsubscribed = True

    def close(self) -> None:
        self.closed = True

    def notify(self, payload: Mapping[str, Any]) -> None:
        assert self.callback is not None
        self.callback(payload)


def test_callback_is_refresh_notification_and_deduplicates_snapshot() -> None:
    first = _event(price=10.0, volume=100)
    second = _event(price=10.1, volume=120, timestamp=_time(10, 0, 10))
    provider = _CollectorProvider(((first,), (second,), (second,)))
    collector = LiveLevel1Collector(provider, ("000001.SZ",))

    collector.start()
    provider.notify({"Code": "000001.SZ", "ErrorId": "0"})
    provider.notify({"Code": "000001.SZ", "ErrorId": "0"})
    collector.shutdown()
    report = collector.report()

    assert report.connection_status == "subscribed"
    assert report.snapshot_count == 3
    assert report.callback_count == 2
    assert report.quote_change_count == 1
    assert report.realtime_market_change_detected is True
    assert report.event_count == 2
    assert report.deduplicated_count == 1
    assert provider.unsubscribed is True
    assert provider.closed is True


def test_callback_heartbeat_is_not_reported_as_a_realtime_market_change() -> None:
    unchanged = _event(price=10.0, volume=100)
    provider = _CollectorProvider(((unchanged,), (unchanged,)))
    store = InMemoryReportingStore()
    collector = LiveLevel1Collector(provider, ("000001.SZ",), sink=store)

    collector.start()
    provider.notify({"Code": "000001.SZ", "ErrorId": "0"})
    collector.shutdown()
    report = collector.report()

    assert report.callback_count == 1
    assert report.quote_change_count == 0
    assert report.realtime_market_change_detected is False
    assert report.event_count == 1
    assert report.deduplicated_count == 1
    assert report.persisted_event_count == 1
    assert report.persisted_bar_count == 1
    assert report.storage_backend == "memory"


def test_polling_fallback_and_graceful_shutdown() -> None:
    provider = _CollectorProvider(((_event(),),), subscribe_error=True)
    collector = LiveLevel1Collector(provider, ("000001.SZ",))

    collector.start()
    assert collector.connection_status == "polling_fallback"
    collector.shutdown()

    assert provider.unsubscribed is False
    assert provider.closed is True
    assert collector.connection_status == "disconnected"


def test_existing_reporting_store_persists_level1_events_and_bars_idempotently() -> None:
    provider = _CollectorProvider(((_event(),),))
    store = InMemoryReportingStore()
    collector = LiveLevel1Collector(provider, ("000001.SZ",), sink=store)

    collector.start()
    collector.shutdown()
    store.persist_market_data(collector.events, collector.bars)

    assert len(store.market_events) == 1
    assert len(store.intraday_bars) == 1
    assert collector.report().persisted_event_count == 1
    assert collector.report().persisted_bar_count == 1


def test_live_provider_fails_clearly_off_windows(tmp_path: Path) -> None:
    provider = TDXLevel1Provider(tmp_path, platform_system=lambda: "Darwin")
    with pytest.raises(Exception, match="only on Windows"):
        provider.initialize()
