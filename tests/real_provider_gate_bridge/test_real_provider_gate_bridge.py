from datetime import date

import pytest

from quantpilot_core.real_data_provider.contracts import (
    DailyBarRequest,
    NormalizedDailyBar,
    ProviderDataError,
    ProviderName,
)
from quantpilot_core.real_provider_gate_bridge import (
    RealProviderGateBridgeError,
    SmallSampleGateBridgeMetadata,
    validate_provider_bars_with_small_sample_gate,
)


class FakeDailyBarProvider:
    provider_name = ProviderName.AKSHARE

    def __init__(self, bars=None, error=None):
        self.bars = bars or []
        self.error = error
        self.calls = []

    def fetch_daily_bars(self, request):
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        return self.bars


def request():
    return DailyBarRequest(
        symbol="600000",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
    )


def bar(trade_date):
    return NormalizedDailyBar(
        symbol="600000",
        trade_date=trade_date,
        open=10.0,
        close=10.2,
        high=10.5,
        low=9.9,
        volume=1000.0,
        amount=10000.0,
    )


def test_bridge_calls_provider() -> None:
    provider = FakeDailyBarProvider([bar(date(2026, 1, 1))])
    daily_request = request()

    validate_provider_bars_with_small_sample_gate(provider, daily_request)

    assert provider.calls == [daily_request]


def test_valid_fake_bars_pass_small_sample_gate() -> None:
    provider = FakeDailyBarProvider(
        [bar(date(2026, 1, 1)), bar(date(2026, 1, 3))]
    )

    result = validate_provider_bars_with_small_sample_gate(provider, request())

    assert result.provider_name is ProviderName.AKSHARE
    assert result.symbol == "600000"
    assert result.start_date == date(2026, 1, 1)
    assert result.end_date == date(2026, 1, 3)
    assert result.bar_count == 2
    assert result.gate_passed is True
    assert result.gate_reasons == ()


def test_invalid_insufficient_bars_fail_gate() -> None:
    provider = FakeDailyBarProvider([bar(date(2026, 1, 1))])
    metadata = SmallSampleGateBridgeMetadata(
        provider_adapter_probe_plan_reference="",
        approved_r4_gate_decision_reference="",
    )

    result = validate_provider_bars_with_small_sample_gate(
        provider,
        request(),
        metadata=metadata,
    )

    assert result.gate_passed is False
    assert "provider_adapter_probe_plan_reference_missing" in result.gate_reasons
    assert "r4_gate_decision_reference_missing" in result.gate_reasons


def test_empty_provider_output_fails_safely() -> None:
    result = validate_provider_bars_with_small_sample_gate(
        FakeDailyBarProvider([]),
        request(),
    )

    assert result.bar_count == 0
    assert result.gate_passed is False
    assert "scope_too_broad" in result.gate_reasons
    assert "schema_review_missing" in result.gate_reasons
    assert "timestamp_audit_missing" in result.gate_reasons


def test_provider_errors_are_wrapped_clearly() -> None:
    provider = FakeDailyBarProvider(error=ProviderDataError("bad provider row"))

    with pytest.raises(RealProviderGateBridgeError, match="Provider daily-bar fetch"):
        validate_provider_bars_with_small_sample_gate(provider, request())


def test_no_network_or_real_provider_dependency_is_needed() -> None:
    provider = FakeDailyBarProvider([bar(date(2026, 1, 1))])

    result = validate_provider_bars_with_small_sample_gate(provider, request())

    assert result.gate_passed is True
