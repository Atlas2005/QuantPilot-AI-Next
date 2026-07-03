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
from quantpilot_core.real_data_provider.baostock_adapter import BaoStockDailyBarProvider
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


class FakeBaoStockLoginResult:
    def __init__(self, error_code: str = "0", error_msg: str = "success") -> None:
        self.error_code = error_code
        self.error_msg = error_msg


class FakeBaoStockDataFrame:
    def __init__(self, rows: list[dict[str, str]]) -> None:
        self.rows = rows

    def to_dict(self, orient: str) -> list[dict[str, str]]:
        assert orient == "records"
        return self.rows


class FakeBaoStockQueryResult:
    def __init__(self, rows: list[dict[str, str]]) -> None:
        self.rows = rows
        self.error_code = "0"
        self.error_msg = "success"

    def get_data(self) -> FakeBaoStockDataFrame:
        return FakeBaoStockDataFrame(self.rows)


class FakeBaoStockClient:
    def __init__(
        self,
        *,
        login_result: FakeBaoStockLoginResult | None = None,
        empty_symbol: str | None = None,
        empty_symbols: set[str] | None = None,
    ) -> None:
        self.events: list[str] = []
        self.query_codes: list[str] = []
        self.login_result = login_result or FakeBaoStockLoginResult()
        self.empty_symbols = set(empty_symbols or set())
        if empty_symbol is not None:
            self.empty_symbols.add(empty_symbol)

    def login(self) -> FakeBaoStockLoginResult:
        self.events.append("login")
        return self.login_result

    def logout(self) -> FakeBaoStockLoginResult:
        self.events.append("logout")
        return FakeBaoStockLoginResult()

    def query_history_k_data_plus(self, **kwargs) -> FakeBaoStockQueryResult:
        code = kwargs["code"]
        self.events.append(f"query:{code}")
        self.query_codes.append(code)
        if code in self.empty_symbols:
            return FakeBaoStockQueryResult([])
        return FakeBaoStockQueryResult(_fake_baostock_rows(code))


def config(provider, **overrides) -> RealDataWalkForwardSmokeConfig:
    values = {
        "provider": provider,
        "start_date": "2026-01-01",
        "end_date": "2026-01-18",
        "train_window_days": 5,
        "test_window_days": 3,
        "max_windows": 2,
        "advisory_mode": "disabled",
    }
    values.update(overrides)
    return RealDataWalkForwardSmokeConfig(
        **values,
    )


def _fake_baostock_rows(code: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for index in range(18):
        trade_date = date(2026, 1, 1) + timedelta(days=index)
        base = 10.0 + index * 0.2
        rows.append(
            {
                "date": trade_date.isoformat(),
                "code": code,
                "open": f"{base:.2f}",
                "high": f"{base + 0.4:.2f}",
                "low": f"{base - 0.2:.2f}",
                "close": f"{base + 0.1:.2f}",
                "volume": str(1_000_000 + index * 1_000),
                "amount": f"{(base + 0.1) * 1_000_000:.2f}",
            }
        )
    return rows


def test_config_default_universe_is_stock_first_without_etfs() -> None:
    default = RealDataWalkForwardSmokeConfig()

    assert default.symbols == ("000001.SZ", "000002.SZ", "600000.SH", "601318.SH")
    assert len(default.symbols) == 4
    assert default.allow_partial_universe is True
    assert default.min_symbols_required == 2
    assert default.advisory_mode == "fallback_only"
    assert default.provider == "baostock"
    assert not any(symbol.startswith(("510", "159")) for symbol in default.symbols)


def test_fixture_provider_produces_walk_forward_report() -> None:
    provider = FixtureDailyBarProvider()

    report = run_real_data_walk_forward_smoke(config(provider))

    assert isinstance(report, RealDataWalkForwardSmokeReport)
    assert report.provider == "baostock"
    assert report.symbols == ("000001.SZ", "000002.SZ", "600000.SH", "601318.SH")
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


def test_baostock_smoke_login_wraps_all_symbol_queries(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeBaoStockClient()

    monkeypatch.setattr(
        "quantpilot_core.evaluation.real_data_walk_forward_smoke.BaoStockDailyBarProvider",
        lambda: BaoStockDailyBarProvider(baostock_client=client),
    )

    report = run_real_data_walk_forward_smoke(config("baostock"))

    assert report.notes[0] == "real_data_smoke_completed"
    assert report.windows_run == 2
    assert client.events[0] == "login"
    assert client.events[-1] == "logout"
    assert client.events[1:-1] == [
        "query:sz.000001",
        "query:sz.000002",
        "query:sh.600000",
        "query:sh.601318",
    ]
    assert client.query_codes == ["sz.000001", "sz.000002", "sh.600000", "sh.601318"]


def test_baostock_smoke_skips_empty_explicit_etf_and_still_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeBaoStockClient(empty_symbol="sh.510300")

    monkeypatch.setattr(
        "quantpilot_core.evaluation.real_data_walk_forward_smoke.BaoStockDailyBarProvider",
        lambda: BaoStockDailyBarProvider(baostock_client=client),
    )

    report = run_real_data_walk_forward_smoke(
        config("baostock", symbols=("000001.SZ", "000002.SZ", "510300.SH"))
    )

    assert report.notes[0] == "real_data_smoke_completed"
    assert "empty_provider_rows:sh.510300" in report.data_quality_warnings
    assert "missing_symbols:510300.SH" in report.data_quality_warnings
    assert client.events[-1] == "logout"
    assert client.query_codes == ["sz.000001", "sz.000002", "sh.510300"]


def test_baostock_smoke_all_empty_symbols_return_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeBaoStockClient(empty_symbols={"sz.000001", "sz.000002"})

    monkeypatch.setattr(
        "quantpilot_core.evaluation.real_data_walk_forward_smoke.BaoStockDailyBarProvider",
        lambda: BaoStockDailyBarProvider(baostock_client=client),
    )

    report = run_real_data_walk_forward_smoke(config("baostock", symbols=("000001.SZ", "000002.SZ")))

    assert report.notes[0] == "real_data_provider_unavailable"
    assert report.notes[1] == "provider returned no usable OHLCV rows"
    assert "empty_provider_rows:sz.000001" in report.data_quality_warnings
    assert "empty_provider_rows:sz.000002" in report.data_quality_warnings
    assert client.events[-1] == "logout"


def test_baostock_smoke_fewer_than_min_valid_symbols_return_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeBaoStockClient(empty_symbols={"sz.000002", "sh.600000"})

    monkeypatch.setattr(
        "quantpilot_core.evaluation.real_data_walk_forward_smoke.BaoStockDailyBarProvider",
        lambda: BaoStockDailyBarProvider(baostock_client=client),
    )

    report = run_real_data_walk_forward_smoke(
        config(
            "baostock",
            symbols=("000001.SZ", "000002.SZ", "600000.SH"),
            min_symbols_required=2,
        )
    )

    assert report.notes[0] == "real_data_provider_unavailable"
    assert "valid provider symbols below minimum: 1 < 2" in report.notes[1]
    assert "empty_provider_rows:sz.000002" in report.data_quality_warnings
    assert "empty_provider_rows:sh.600000" in report.data_quality_warnings
    assert client.events[-1] == "logout"


def test_baostock_smoke_login_failure_is_provider_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeBaoStockClient(login_result=FakeBaoStockLoginResult("10002007", "login failed"))

    monkeypatch.setattr(
        "quantpilot_core.evaluation.real_data_walk_forward_smoke.BaoStockDailyBarProvider",
        lambda: BaoStockDailyBarProvider(baostock_client=client),
    )

    report = run_real_data_walk_forward_smoke(config("baostock"))

    assert report.notes[0] == "real_data_provider_unavailable"
    assert "BaoStock login failed: 10002007: login failed" in report.notes[1]
    assert client.events == ["login"]
    assert client.query_codes == []


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
