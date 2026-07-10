from __future__ import annotations

from datetime import date
import importlib.util
from pathlib import Path
import sys

import pytest

from quantpilot_core.all_a_share_snapshot.contracts import SnapshotConfig
from quantpilot_core.all_a_share_snapshot.snapshot import SnapshotLoader, build_snapshot
from quantpilot_core.real_data_provider import Adjustment, DailyBarRequest, ProviderError, SnapshotDailyBarProvider


class LocalSnapshotProvider:
    """Small public-protocol fixture; it never talks to a market provider."""

    provider_name = "fixture"

    def fetch_stock_basic(self, statuses):
        return [{"ts_code": "600000.SH", "symbol": "600000", "name": "Bank", "area": "", "industry": "",
                 "market": "Main", "exchange": "SSE", "list_status": "L", "list_date": "20200101", "delist_date": ""}]

    def fetch_trade_cal(self, start, end):
        return [{"exchange": "SSE", "cal_date": day, "is_open": 1} for day in ("20240102", "20240103")]

    def fetch_daily_by_trade_date(self, day):
        return [{"ts_code": "600000.SH", "trade_date": day, "open": 10, "high": 12, "low": 9, "close": 11,
                 "pre_close": 10, "change": 1, "pct_chg": 10, "vol": 123, "amount": 456}]

    def fetch_adj_factor_by_trade_date(self, day):
        return [{"ts_code": "600000.SH", "trade_date": day, "adj_factor": 1}]

    def fetch_index_daily(self, symbol, start, end):
        return [dict(self.fetch_daily_by_trade_date(day)[0], ts_code=symbol) for day in ("20240102", "20240103")]

    def fetch_optional(self, dataset, trade_date=None):
        return []

    def fetch_namechange_by_ts_code(self, ts_code):
        return []


def _snapshot(tmp_path):
    build_snapshot(SnapshotConfig(root=str(tmp_path), start_date="20240102", end_date="20240103", include_optional=False, test_only=True), LocalSnapshotProvider())
    return SnapshotDailyBarProvider(tmp_path)


def test_snapshot_adapter_maps_rows_orders_batch_and_reports_empty_symbols(tmp_path):
    provider = _snapshot(tmp_path)
    request = DailyBarRequest("600000.SH", date(2024, 1, 2), date(2024, 1, 3))
    bars, empty = provider.fetch_many_daily_bars_with_empty_symbols((DailyBarRequest("000001.SZ", date(2024, 1, 2), date(2024, 1, 3)), request))
    assert empty == ("000001.SZ",)
    assert [(bar.symbol, bar.trade_date.isoformat(), bar.open, bar.high, bar.low, bar.close, bar.volume, bar.amount, bar.previous_close, bar.pct_change) for bar in bars] == [
        ("600000.SH", "2024-01-02", 10.0, 12.0, 9.0, 11.0, 123.0, 456.0, 10.0, 10.0),
        ("600000.SH", "2024-01-03", 10.0, 12.0, 9.0, 11.0, 123.0, 456.0, 10.0, 10.0),
    ]
    assert provider.daily_symbol_union("2024-01-02", "2024-01-03") == ("600000.SH",)
    assert provider.snapshot_provenance()["external_calls_occurred"] is False
    with pytest.raises(ProviderError, match="Adjustment.NONE"):
        provider.fetch_daily_bars(DailyBarRequest("600000.SH", date(2024, 1, 2), date(2024, 1, 2), Adjustment.QFQ))


def test_snapshot_adapter_caches_calendar_and_reads_each_daily_partition_once(tmp_path, monkeypatch):
    calls = {"sessions": 0, "daily": []}
    original_sessions, original_daily = SnapshotLoader.sessions, SnapshotLoader.daily

    def sessions(self):
        calls["sessions"] += 1
        return original_sessions(self)

    def daily(self, day):
        calls["daily"].append(day)
        return original_daily(self, day)

    monkeypatch.setattr(SnapshotLoader, "sessions", sessions)
    monkeypatch.setattr(SnapshotLoader, "daily", daily)
    provider = _snapshot(tmp_path)
    requests = tuple(DailyBarRequest(symbol, date(2024, 1, 2), date(2024, 1, 3)) for symbol in ("600000.SH", "000001.SZ", "000002.SZ"))
    provider.fetch_many_daily_bars_with_empty_symbols(requests)
    assert calls == {"sessions": 1, "daily": ["20240102", "20240103"]}


def test_invalid_snapshot_fails_structurally(tmp_path):
    with pytest.raises(ProviderError, match="invalid all-A-share snapshot"):
        SnapshotDailyBarProvider(tmp_path)


def _cli_module():
    path = Path(__file__).parents[2] / "scripts" / "run_real_data_walk_forward_scaleup_v1.py"
    spec = importlib.util.spec_from_file_location("scaleup_cli_for_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_cli_uses_snapshot_union_or_explicit_symbols(monkeypatch, tmp_path):
    module = _cli_module()
    captured = []

    class Provider:
        def __init__(self, root):
            assert root == tmp_path
        def daily_symbol_union(self, start, end):
            return ("600000.SH", "300114.SZ")

    class Report:
        provider = "all_a_share_snapshot"; symbols = ("600000.SH",); valid_symbols = (); skipped_symbols = ()
        windows_run = 0; total_return = benchmark_total_return = strategy_excess_return = max_drawdown = None
        win_rate_by_window = average_window_return = median_window_return = worst_window_return = None
        equity_window_return = actual_position_count_by_window = cash_weight_by_window = gross_exposure_by_window = largest_position_weight_by_window = ()
        filled_trades = rejected_trades = resized_order_count = skipped_below_lot_count = rebalance_sell_count = rebalance_buy_count = 0
        rejected_trade_ratio = cost_to_turnover_ratio = None; turnover = cost_total = 0.0; rejection_reasons = {}; top_contributors = worst_contributors = (); notes = (); data_quality_warnings = (); artifact_path = None
        data_source_provenance = {}

    monkeypatch.setattr(module, "SnapshotDailyBarProvider", Provider)
    monkeypatch.setattr(module, "run_real_data_walk_forward_scaleup_v1", lambda config: captured.append(config) or Report())
    monkeypatch.setattr(sys, "argv", ["runner", "--snapshot-root", str(tmp_path), "--min-symbols-required", "1"])
    assert module.main() == 0 and captured[-1].symbols == ("600000.SH", "300114.SZ")
    monkeypatch.setattr(sys, "argv", ["runner", "--snapshot-root", str(tmp_path), "--symbols", "300114.SZ", "--min-symbols-required", "1"])
    assert module.main() == 0 and captured[-1].symbols == ("300114.SZ",)
