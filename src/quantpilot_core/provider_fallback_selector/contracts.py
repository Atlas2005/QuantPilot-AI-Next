"""Contracts for R12 provider fallback selector preflight."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ProviderCandidateName(str, Enum):
    AKSHARE = "akshare"
    BAOSTOCK = "baostock"


class ProviderAvailability(str, Enum):
    AVAILABLE = "available"
    MISSING = "missing"
    DISABLED = "disabled"
    UNHEALTHY = "unhealthy"


class ProviderFallbackPreference(str, Enum):
    AKSHARE_FIRST = "akshare_first"
    BAOSTOCK_FIRST = "baostock_first"


@dataclass(frozen=True)
class ProviderCandidateStatus:
    name: ProviderCandidateName
    availability: ProviderAvailability
    reason: str = ""


@dataclass(frozen=True)
class ProviderFallbackSelectionRequest:
    candidates: tuple[ProviderCandidateStatus, ...]
    preference: ProviderFallbackPreference = ProviderFallbackPreference.AKSHARE_FIRST
    require_available: bool = True


@dataclass(frozen=True)
class ProviderFallbackSelectionResult:
    selected_provider: ProviderCandidateName | None
    fallback_order: tuple[ProviderCandidateName, ...]
    can_attempt_fetch: bool
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    suggested_next_action: str
