"""Core contract types for QuantPilot-AI 2.0."""

from dataclasses import dataclass
from enum import Enum


class ContractCategory(str, Enum):
    DATA_SOURCE = "data_source"
    DATA_VALIDATOR = "data_validator"
    MARKET_RULE = "market_rule"
    BACKTEST_ENGINE = "backtest_engine"
    FACTOR_ENGINE = "factor_engine"
    PORTFOLIO_ENGINE = "portfolio_engine"
    AGENT_SKILL = "agent_skill"
    REPORTING = "reporting"
    SAFETY = "safety"


class ContractStatus(str, Enum):
    DRAFT = "draft"
    EXPERIMENTAL = "experimental"
    STABLE = "stable"
    DEPRECATED = "deprecated"


class AdapterAction(str, Enum):
    ADOPT_DIRECTLY = "adopt_directly"
    WRAP_WITH_ADAPTER = "wrap_with_adapter"
    BORROW_ARCHITECTURE_ONLY = "borrow_architecture_only"
    PROTOTYPE_REQUIRED = "prototype_required"
    DEFER_UNTIL_FOUNDATION_READY = "defer_until_foundation_ready"
    AVOID_FOR_NOW = "avoid_for_now"


@dataclass(frozen=True)
class ContractMetadata:
    """Serializable metadata for a contract boundary."""

    name: str
    category: ContractCategory
    version: str
    status: ContractStatus
    description: str
    owner: str
    external_dependency: str
    notes: str

    def as_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "category": self.category.value,
            "version": self.version,
            "status": self.status.value,
            "description": self.description,
            "owner": self.owner,
            "external_dependency": self.external_dependency,
            "notes": self.notes,
        }

