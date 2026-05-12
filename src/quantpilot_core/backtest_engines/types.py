"""Types for backtest engine metadata evaluation."""

from dataclasses import dataclass
from enum import Enum


class BacktestEngineCategory(str, Enum):
    VECTORIZED_RESEARCH = "vectorized_research"
    EVENT_DRIVEN = "event_driven"
    ML_RESEARCH_PLATFORM = "ml_research_platform"
    FULL_TRADING_PLATFORM = "full_trading_platform"
    A_SHARE_ORIENTED = "a_share_oriented"
    LIGHTWEIGHT_EDUCATIONAL = "lightweight_educational"
    UNKNOWN = "unknown"


class BacktestIntegrationPolicy(str, Enum):
    REGISTRY_ONLY = "registry_only"
    EVALUATION_ONLY = "evaluation_only"
    PROTOTYPE_LATER = "prototype_later"
    ADAPTER_LATER = "adapter_later"
    BORROW_ARCHITECTURE_ONLY = "borrow_architecture_only"
    AVOID_FOR_NOW = "avoid_for_now"


class BacktestRiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class BacktestReadinessStatus(str, Enum):
    NOT_EVALUATED = "not_evaluated"
    METADATA_REVIEWED = "metadata_reviewed"
    PROTOTYPE_REQUIRED = "prototype_required"
    REJECTED = "rejected"
    APPROVED_FOR_ADAPTER_LATER = "approved_for_adapter_later"


@dataclass(frozen=True)
class BacktestEngineCandidate:
    """Static metadata for a backtest engine candidate."""

    name: str
    category: BacktestEngineCategory
    integration_policy: BacktestIntegrationPolicy
    readiness_status: BacktestReadinessStatus
    license_risk: BacktestRiskLevel
    live_trading_risk: BacktestRiskLevel
    a_share_fit_risk: BacktestRiskLevel
    windows_risk: BacktestRiskLevel
    dependency_risk: BacktestRiskLevel
    notes: str

