"""Contracts for the R18 PIT data and feature-store preflight."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PITFeatureBuildMode(str, Enum):
    OFFLINE_PREFLIGHT = "offline_preflight"


class PITFeatureStoreStatus(str, Enum):
    READY = "ready"
    REJECTED = "rejected"


class PITFeatureValueKind(str, Enum):
    NUMERIC = "numeric"


@dataclass(frozen=True)
class PITFeatureStoreManifest:
    feature_set_id: str
    version: str
    source_ref: str
    build_mode: PITFeatureBuildMode = PITFeatureBuildMode.OFFLINE_PREFLIGHT
    sandbox_only: bool = True
    no_live_trading: bool = True
    no_order_execution: bool = True
    point_in_time: bool = True


@dataclass(frozen=True)
class PITFeatureRecord:
    symbol: str
    feature_name: str
    feature_value: float
    observation_date: str
    available_date: str
    as_of_date: str
    value_kind: PITFeatureValueKind = PITFeatureValueKind.NUMERIC
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class PITFeatureStorePreflightResult:
    status: PITFeatureStoreStatus
    ok: bool
    feature_set_id: str
    accepted_record_count: int
    rejected_record_count: int
    can_feed_sandbox: bool
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    suggested_next_action: str
