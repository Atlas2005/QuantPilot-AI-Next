from __future__ import annotations

from datetime import date, timedelta

import pytest

from quantpilot_core.evaluation import (
    RealDataWalkForwardSmokeConfig,
    RealDataWalkForwardSmokeReport,
    run_real_data_walk_forward_smoke,
)
from quantpilot_core.real_data_provider import (
    DailyBarRequest,
    NormalizedDailyBar,
    ProviderName,
)
from quantpilot_core.tool_registry import build_default_tool_registry


class FixtureDailyBarProvider:
    provider_name = ProviderName.BAOSTOCK

    def __init__(self) -> None:
        self.requests: list[DailyBarRequest] = []

    def fetch_daily_bars(self, request: DailyBarRequest) -> list[NormalizedDailyBar]:
        self.requests.append(request)
        canonical = request.symbol[3:] + "." + request.symbol[:2].upper()
        start = date(2026, 1, 1)
        rows: list[NormalizedDailyBar] = []
        for index in range(18):
            trade_date = start + timedelta(days=index)
            base = 10.0 + index * 0.2
            rows.append(
                NormalizedDailyBar(
                    symbol=request.symbol,
                    trade_date=trade_date,
                    open=base,
                    high=base + 0.4,
                    low=base - 0.2,
                    close=base + (0.1 if canonical.endswith(".SZ") else 0.05),
                    volume=1_000_000 + index * 1_000,
                    amount=(base + 0.1) * 1_000_000,
                    provider=ProviderName.BAOSTOCK,
                )
            )
        return rows


class UnavailableProvider:
    provider_name = ProviderName.BAOSTOCK

    def fetch_daily_bars(self, request: DailyBarRequest) -> list[NormalizedDailyBar]:
        raise RuntimeError("fixture provider unavailable")


def config(provider) -> RealDataWalkForwardSmokeConfig:
    return RealDataWalkForwardSmokeConfig(
        provider=provider,
        start_date="2026-01-01",
        end_date="2026-01-18",
        train_window_days=5,
        test_window_days=3,
        max_windows=2,
        advisory_mode="disabled",
    )


def test_config_default_universe_is_small_ashare_and_etf_oriented() -> None:
    default = RealDataWalkForwardSmokeConfig()

    assert default.symbols == ("000001.SZ", "000002.SZ", "510300.SH", "510500.SH")
    assert len(default.symbols) == 4
    assert default.advisory_mode == "fallback_only"
    assert default.provider == "baostock"


def test_fixture_provider_produces_walk_forward_report() -> None:
    provider = FixtureDailyBarProvider()

    report = run_real_data_walk_forward_smoke(config(provider))

    assert isinstance(report, RealDataWalkForwardSmokeReport)
    assert report.provider == "baostock"
    assert report.symbols == ("000001.SZ", "000002.SZ", "510300.SH", "510500.SH")
    assert report.windows_run == 2
    assert report.final_equity is not None
    assert report.total_return is not None
    assert report.max_drawdown is not None
    assert report.filled_trades >= 1
    assert report.rejected_trades >= 0
    assert report.cost_total >= 0
    assert len(report.per_window_metrics) == 2
    assert {"ending_equity", "net_pnl", "trade_count", "rejected_count", "cost_total"} <= set(
        report.per_window_metrics[0]
    )
    assert report.leakage_checks == (
        "real-data-smoke-1:train_and_test_slices_validated",
        "real-data-smoke-2:train_and_test_slices_validated",
    )
    assert "real_data_smoke_completed" in report.notes
    assert "no_broker_live_execution" in report.notes
    assert all(call.symbol.startswith(("sz.", "sh.")) for call in provider.requests)


def test_windows_are_train_before_test_without_future_leakage() -> None:
    report = run_real_data_walk_forward_smoke(config(FixtureDailyBarProvider()))

    for metrics in report.per_window_metrics:
        assert metrics["train_end"] < metrics["test_start"]
        assert metrics["test_end"] <= "2026-01-18"


def test_invalid_advisory_mode_is_forced_to_fallback_only() -> None:
    payload = config(FixtureDailyBarProvider())
    payload = RealDataWalkForwardSmokeConfig(
        symbols=payload.symbols,
        start_date=payload.start_date,
        end_date=payload.end_date,
        initial_cash=payload.initial_cash,
        train_window_days=payload.train_window_days,
        test_window_days=payload.test_window_days,
        max_windows=payload.max_windows,
        provider=payload.provider,
        advisory_mode="live_model",
    )

    report = run_real_data_walk_forward_smoke(payload)

    assert "advisory_mode_forced_to_fallback_only" in report.data_quality_warnings
    assert "advisory_mode:fallback_only" in report.notes


def test_provider_unavailable_path_is_structured_and_clear() -> None:
    report = run_real_data_walk_forward_smoke(config(UnavailableProvider()))

    assert report.windows_run == 0
    assert report.final_equity is None
    assert report.total_return is None
    assert report.per_window_metrics == ()
    assert report.notes[0] == "real_data_provider_unavailable"
    assert "fixture provider unavailable" in report.notes[1]


def test_tool_registry_wrapper_runs_with_fixture_provider() -> None:
    registry = build_default_tool_registry()

    result = registry.execute("run_real_data_walk_forward_smoke", config=config(FixtureDailyBarProvider()))

    assert result.ok is True
    assert isinstance(result.output, RealDataWalkForwardSmokeReport)
    assert result.output.windows_run == 2


def test_no_network_or_live_dependency_is_needed_for_fixture_run(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_provider_constructor(*args, **kwargs):
        raise AssertionError("real provider constructor must not be used")

    monkeypatch.setattr(
        "quantpilot_core.evaluation.real_data_walk_forward_smoke.BaoStockDailyBarProvider",
        fail_provider_constructor,
    )
    monkeypatch.setattr(
        "quantpilot_core.evaluation.real_data_walk_forward_smoke.AkShareDailyBarProvider",
        fail_provider_constructor,
    )
    monkeypatch.setattr(
        "quantpilot_core.evaluation.real_data_walk_forward_smoke.import_module",
        fail_provider_constructor,
    )

    report = run_real_data_walk_forward_smoke(config(FixtureDailyBarProvider()))

    assert report.windows_run == 2
    assert "no_broker_live_execution" in report.notes
