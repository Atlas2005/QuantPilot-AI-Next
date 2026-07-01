"""Provider sample fetch config validation using selector and sample quality glue."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from quantpilot_core.provider_fallback_selector import (
    ProviderCandidateName,
    ProviderFallbackSelectionRequest,
    select_provider_candidate,
)
from quantpilot_core.provider_sample_fetch_preflight.contracts import (
    ProviderSampleFetchRequest,
    ProviderSampleFetchResult,
    ProviderSampleFetchStatus,
)
from quantpilot_core.real_data_provider import (
    Adjustment,
    DailyBarRequest,
    NormalizedDailyBar,
    ProviderName,
)
from quantpilot_core.real_provider_gate_bridge import (
    validate_provider_bars_with_small_sample_gate,
)


def run_provider_sample_fetch_preflight(
    request: ProviderSampleFetchRequest,
) -> ProviderSampleFetchResult:
    """Select an offline provider, fetch sample bars, and return quality hints."""

    invalid_reasons = _validate_request_shape(request)
    if invalid_reasons:
        return ProviderSampleFetchResult(
            status=ProviderSampleFetchStatus.FETCH_FAILED,
            selected_provider=None,
            fetched_bar_count=0,
            gate_passed=False,
            reasons=invalid_reasons,
            warnings=(),
            suggested_next_action="Fix the sample fetch request before selecting a provider.",
        )

    selection = select_provider_candidate(
        ProviderFallbackSelectionRequest(
            candidates=request.candidate_statuses,
            preference=request.preference,
        )
    )
    if selection.selected_provider is None:
        return ProviderSampleFetchResult(
            status=ProviderSampleFetchStatus.NO_PROVIDER_SELECTED,
            selected_provider=None,
            fetched_bar_count=0,
            gate_passed=False,
            reasons=selection.reasons,
            warnings=selection.warnings,
            suggested_next_action=selection.suggested_next_action,
        )

    client = request.provider_clients.get(selection.selected_provider)
    if client is None:
        return ProviderSampleFetchResult(
            status=ProviderSampleFetchStatus.FETCH_FAILED,
            selected_provider=selection.selected_provider,
            fetched_bar_count=0,
            gate_passed=False,
            reasons=("missing_injected_provider_client",),
            warnings=selection.warnings,
            suggested_next_action="Inject a fake/offline provider client for the selected provider.",
        )

    try:
        bars = _fetch_offline_bars(
            client=client,
            symbol=request.symbol,
            start_date=request.start_date,
            end_date=request.end_date,
        )
    except Exception as exc:
        return ProviderSampleFetchResult(
            status=ProviderSampleFetchStatus.FETCH_FAILED,
            selected_provider=selection.selected_provider,
            fetched_bar_count=0,
            gate_passed=False,
            reasons=(f"provider_fetch_failed: {exc}",),
            warnings=selection.warnings,
            suggested_next_action="Fix the offline provider fixture before sample validation.",
        )

    if not bars:
        return ProviderSampleFetchResult(
            status=ProviderSampleFetchStatus.GATE_FAILED,
            selected_provider=selection.selected_provider,
            fetched_bar_count=0,
            gate_passed=False,
            reasons=("empty_sample_unusable",),
            warnings=selection.warnings,
            suggested_next_action="Provide at least one normalized sample bar before paper use.",
        )

    quality_warnings: list[str] = list(selection.warnings)
    if len(bars) < request.min_required_bars:
        quality_warnings.append("sample_size_below_requested_minimum")

    provider = _FetchedBarsProvider(
        provider_name=_provider_name_from_candidate(selection.selected_provider),
        bars=bars,
    )
    bridge_request = DailyBarRequest(
        symbol=request.symbol,
        start_date=request.start_date,
        end_date=request.end_date,
        adjustment=Adjustment.NONE,
    )
    gate_result = validate_provider_bars_with_small_sample_gate(provider, bridge_request)
    if not gate_result.gate_passed:
        quality_warnings.extend(f"sample_quality:{reason}" for reason in gate_result.gate_reasons)

    return ProviderSampleFetchResult(
        status=ProviderSampleFetchStatus.READY,
        selected_provider=selection.selected_provider,
        fetched_bar_count=len(bars),
        gate_passed=gate_result.gate_passed and len(bars) >= request.min_required_bars,
        reasons=(),
        warnings=tuple(quality_warnings),
        suggested_next_action=(
            "Feed the validated sample into the paper ledger / Market Reality Sandbox dry path."
        ),
    )


def _validate_request_shape(
    request: ProviderSampleFetchRequest,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if not request.symbol.strip():
        reasons.append("symbol_missing")
    if request.start_date > request.end_date:
        reasons.append("date_range_invalid")
    if request.min_required_bars <= 0:
        reasons.append("min_required_bars_invalid")
    return tuple(reasons)


def _fetch_offline_bars(
    client: object,
    symbol: str,
    start_date: date,
    end_date: date,
) -> list[NormalizedDailyBar]:
    if hasattr(client, "fetch_daily_bars"):
        raw = getattr(client, "fetch_daily_bars")(symbol, start_date, end_date)
    elif hasattr(client, "get_daily_bars"):
        raw = getattr(client, "get_daily_bars")(symbol, start_date, end_date)
    else:
        raise TypeError("provider client must expose fetch_daily_bars or get_daily_bars")
    if not isinstance(raw, list):
        raise TypeError("provider client must return a list of NormalizedDailyBar")
    if not all(isinstance(bar, NormalizedDailyBar) for bar in raw):
        raise TypeError("provider client returned non-normalized daily bars")
    return raw


def _provider_name_from_candidate(candidate: ProviderCandidateName) -> ProviderName:
    if candidate is ProviderCandidateName.BAOSTOCK:
        return ProviderName.BAOSTOCK
    return ProviderName.AKSHARE


@dataclass(frozen=True)
class _FetchedBarsProvider:
    provider_name: ProviderName
    bars: list[NormalizedDailyBar]

    def fetch_daily_bars(self, request: DailyBarRequest) -> list[NormalizedDailyBar]:
        return self.bars
