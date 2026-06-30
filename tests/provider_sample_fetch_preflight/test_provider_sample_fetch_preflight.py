from datetime import date, timedelta

from quantpilot_core.provider_fallback_selector import (
    ProviderAvailability,
    ProviderCandidateName,
    ProviderCandidateStatus,
    ProviderFallbackPreference,
)
from quantpilot_core.provider_sample_fetch_preflight import (
    ProviderSampleFetchRequest,
    ProviderSampleFetchStatus,
    run_provider_sample_fetch_preflight,
)
from quantpilot_core.real_data_provider import NormalizedDailyBar


class FetchDailyBarsClient:
    def __init__(self, bars=None, error=None):
        self.bars = bars or []
        self.error = error
        self.calls = []

    def fetch_daily_bars(self, symbol, start_date, end_date):
        self.calls.append((symbol, start_date, end_date))
        if self.error is not None:
            raise self.error
        return self.bars


class GetDailyBarsClient:
    def __init__(self, bars):
        self.bars = bars
        self.calls = []

    def get_daily_bars(self, symbol, start_date, end_date):
        self.calls.append((symbol, start_date, end_date))
        return self.bars


def status(name, availability, reason=""):
    return ProviderCandidateStatus(name=name, availability=availability, reason=reason)


def bars(symbol="600000", count=5):
    start = date(2026, 1, 1)
    return [
        NormalizedDailyBar(
            symbol=symbol,
            trade_date=start + timedelta(days=index),
            open=10.0 + index,
            high=10.8 + index,
            low=9.8 + index,
            close=10.2 + index,
            volume=1000.0 + index,
            amount=10000.0 + index,
        )
        for index in range(count)
    ]


def request(
    *,
    symbol="600000",
    start_date=date(2026, 1, 1),
    end_date=date(2026, 1, 5),
    candidate_statuses=None,
    preference=ProviderFallbackPreference.AKSHARE_FIRST,
    provider_clients=None,
    min_required_bars=5,
):
    return ProviderSampleFetchRequest(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        candidate_statuses=tuple(
            candidate_statuses
            if candidate_statuses is not None
            else (
                status(ProviderCandidateName.AKSHARE, ProviderAvailability.AVAILABLE),
                status(ProviderCandidateName.BAOSTOCK, ProviderAvailability.AVAILABLE),
            )
        ),
        preference=preference,
        provider_clients=provider_clients
        if provider_clients is not None
        else {ProviderCandidateName.AKSHARE: FetchDailyBarsClient(bars())},
        min_required_bars=min_required_bars,
    )


def test_valid_fake_provider_sample_returns_ready_and_gate_passed() -> None:
    result = run_provider_sample_fetch_preflight(request())

    assert result.status is ProviderSampleFetchStatus.READY
    assert result.gate_passed is True
    assert result.fetched_bar_count == 5
    assert result.reasons == ()


def test_akshare_selected_when_both_available_and_akshare_first() -> None:
    result = run_provider_sample_fetch_preflight(request())

    assert result.selected_provider is ProviderCandidateName.AKSHARE


def test_baostock_selected_when_akshare_missing_and_baostock_available() -> None:
    result = run_provider_sample_fetch_preflight(
        request(
            candidate_statuses=(
                status(ProviderCandidateName.AKSHARE, ProviderAvailability.MISSING),
                status(ProviderCandidateName.BAOSTOCK, ProviderAvailability.AVAILABLE),
            ),
            provider_clients={
                ProviderCandidateName.BAOSTOCK: FetchDailyBarsClient(bars())
            },
        )
    )

    assert result.selected_provider is ProviderCandidateName.BAOSTOCK
    assert result.status is ProviderSampleFetchStatus.READY


def test_no_provider_selected_when_both_missing() -> None:
    result = run_provider_sample_fetch_preflight(
        request(
            candidate_statuses=(
                status(ProviderCandidateName.AKSHARE, ProviderAvailability.MISSING),
                status(ProviderCandidateName.BAOSTOCK, ProviderAvailability.MISSING),
            ),
            provider_clients={},
        )
    )

    assert result.status is ProviderSampleFetchStatus.NO_PROVIDER_SELECTED
    assert result.selected_provider is None
    assert result.reasons == ("no_available_provider",)


def test_missing_injected_provider_client_returns_fetch_failed() -> None:
    result = run_provider_sample_fetch_preflight(request(provider_clients={}))

    assert result.status is ProviderSampleFetchStatus.FETCH_FAILED
    assert result.reasons == ("missing_injected_provider_client",)


def test_fake_provider_exception_returns_fetch_failed() -> None:
    result = run_provider_sample_fetch_preflight(
        request(
            provider_clients={
                ProviderCandidateName.AKSHARE: FetchDailyBarsClient(
                    error=RuntimeError("offline fixture failed")
                )
            }
        )
    )

    assert result.status is ProviderSampleFetchStatus.FETCH_FAILED
    assert result.reasons == ("provider_fetch_failed: offline fixture failed",)


def test_empty_symbol_fails_deterministically() -> None:
    result = run_provider_sample_fetch_preflight(request(symbol=" "))

    assert result.status is ProviderSampleFetchStatus.FETCH_FAILED
    assert result.reasons == ("symbol_missing",)


def test_reversed_dates_fail_deterministically() -> None:
    result = run_provider_sample_fetch_preflight(
        request(start_date=date(2026, 1, 5), end_date=date(2026, 1, 1))
    )

    assert result.status is ProviderSampleFetchStatus.FETCH_FAILED
    assert result.reasons == ("date_range_invalid",)


def test_insufficient_sample_size_returns_gate_failed() -> None:
    result = run_provider_sample_fetch_preflight(
        request(provider_clients={ProviderCandidateName.AKSHARE: FetchDailyBarsClient(bars(count=3))})
    )

    assert result.status is ProviderSampleFetchStatus.GATE_FAILED
    assert result.gate_passed is False
    assert result.reasons == ("insufficient_sample_size",)


def test_gate_failure_reasons_are_included_when_sample_data_invalid() -> None:
    result = run_provider_sample_fetch_preflight(
        request(
            provider_clients={
                ProviderCandidateName.AKSHARE: FetchDailyBarsClient(
                    bars(symbol="000001", count=5)
                )
            }
        )
    )

    assert result.status is ProviderSampleFetchStatus.GATE_FAILED
    assert "symbol_mapping_audit_missing" in result.reasons


def test_supports_fetch_daily_bars_method() -> None:
    client = FetchDailyBarsClient(bars())

    result = run_provider_sample_fetch_preflight(
        request(provider_clients={ProviderCandidateName.AKSHARE: client})
    )

    assert result.status is ProviderSampleFetchStatus.READY
    assert client.calls == [("600000", date(2026, 1, 1), date(2026, 1, 5))]


def test_supports_get_daily_bars_method() -> None:
    client = GetDailyBarsClient(bars())

    result = run_provider_sample_fetch_preflight(
        request(provider_clients={ProviderCandidateName.AKSHARE: client})
    )

    assert result.status is ProviderSampleFetchStatus.READY
    assert client.calls == [("600000", date(2026, 1, 1), date(2026, 1, 5))]


def test_selector_warnings_are_propagated() -> None:
    result = run_provider_sample_fetch_preflight(
        request(
            candidate_statuses=(
                status(
                    ProviderCandidateName.AKSHARE,
                    ProviderAvailability.MISSING,
                    "optional dependency missing",
                ),
                status(ProviderCandidateName.BAOSTOCK, ProviderAvailability.AVAILABLE),
            ),
            provider_clients={
                ProviderCandidateName.BAOSTOCK: FetchDailyBarsClient(bars())
            },
        )
    )

    assert "akshare missing: optional dependency missing" in result.warnings


def test_baostock_first_preference_selects_baostock() -> None:
    result = run_provider_sample_fetch_preflight(
        request(
            preference=ProviderFallbackPreference.BAOSTOCK_FIRST,
            provider_clients={
                ProviderCandidateName.BAOSTOCK: FetchDailyBarsClient(bars())
            },
        )
    )

    assert result.selected_provider is ProviderCandidateName.BAOSTOCK


def test_no_network_or_real_provider_dependency_is_needed() -> None:
    result = run_provider_sample_fetch_preflight(request())

    assert result.status is ProviderSampleFetchStatus.READY
