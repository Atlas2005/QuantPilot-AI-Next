"""Contracts for the RQAlpha data bundle and config review layer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RqalphaConfigReviewStatus(str, Enum):
    EVIDENCE_LOADED = "evidence_loaded"
    EVIDENCE_MISSING = "evidence_missing"
    DATA_BUNDLE_REQUIRED = "data_bundle_required"
    CONFIG_REQUIRED = "config_required"
    LOCAL_FIXTURE_NOT_PROVEN = "local_fixture_not_proven"
    READY_FOR_ISOLATED_PROTOTYPE = "ready_for_isolated_prototype"


@dataclass(frozen=True)
class RqalphaEvidenceItem:
    path: str
    exists: bool
    evidence_type: str
    summary: str


@dataclass(frozen=True)
class RqalphaConfigRequirement:
    name: str
    required: bool
    status: str
    reason: str


@dataclass(frozen=True)
class RqalphaConfigReviewResult:
    status: str
    evidence_items: tuple[RqalphaEvidenceItem, ...]
    requirements: tuple[RqalphaConfigRequirement, ...]
    warnings: tuple[str, ...]
    next_actions: tuple[str, ...]
    ready_for_runtime: bool
    production_ready: bool = False
    blocks_other_frameworks: bool = False
