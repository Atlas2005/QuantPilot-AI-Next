"""Contracts for advisory order intents used by paper trading loops."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class OrderIntentSide(str, Enum):
    """Supported advisory order intent sides."""

    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class OrderIntentProposalSource(str, Enum):
    """Known proposal sources for order intent handoff."""

    EXEC2 = "exec2"
    LEARNING_DESK = "learning_desk"
    DEEPSEEK_ADVISORY = "deepseek_advisory"
    INVESTMENT_COMMITTEE = "investment_committee"


@dataclass(frozen=True)
class OrderIntent:
    """One normalized, advisory-only order intent."""

    symbol: str
    side: OrderIntentSide | str
    target_weight: float | None = None
    target_shares: int | None = None
    reason: str = ""
    source_agent: str = "exec2"
    confidence: float = 1.0
    strategy_id: str | None = None
    run_label: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OrderIntentProposal:
    """A batch of advisory-only intents ready for paper fill simulation."""

    intents: tuple[OrderIntent, ...]
    proposal_source: OrderIntentProposalSource | str
    advisory_only: bool = True
    created_at: str | None = None
    run_label: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

