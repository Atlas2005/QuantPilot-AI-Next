"""Contracts for R13 provider sample fetch preflight."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Mapping

from quantpilot_core.provider_fallback_selector.contracts import (
    ProviderCandidateName,
    ProviderCandidateStatus,
    ProviderFallbackPreference,
)


class ProviderSampleFetchStatus(str, Enum):
    READY = "ready"
    NO_PROVIDER_SELECTED = "no_provider_selected"
    FETCH_FAILED = "fetch_failed"
    GATE_FAILED = "gate_failed"


@dataclass(frozen=True)
class ProviderSampleFetchRequest:
    symbol: str
    start_date: date
    end_date: date
    candidate_statuses: tuple[ProviderCandidateStatus, ...]
    provider_clients: Mapping[ProviderCandidateName, object]
    preference: ProviderFallbackPreference = ProviderFallbackPreference.AKSHARE_FIRST
    min_required_bars: int = 5


@dataclass(frozen=True)
class ProviderSampleFetchResult:
    status: ProviderSampleFetchStatus
    selected_provider: ProviderCandidateName | None
    fetched_bar_count: int
    gate_passed: bool
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    suggested_next_action: str
