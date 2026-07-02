"""Pure adapter contracts for mature paper/backtest frameworks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from quantpilot_core.order_intent import OrderIntentProposal, OrderIntentSide


@dataclass(frozen=True)
class VectorbtOrderIntentMapping:
    target_weights: Mapping[str, float]
    target_shares: Mapping[str, int]
    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class DisabledRuntimeAdapterMapping:
    framework: str
    enabled: bool
    order_semantics: tuple[Mapping[str, Any], ...]
    reason: str


class VectorbtOrderIntentAdapter:
    """Map intents into vectorbt-compatible target weights and sizes."""

    def to_target_mapping(self, proposal: OrderIntentProposal) -> VectorbtOrderIntentMapping:
        weights: dict[str, float] = {}
        shares: dict[str, int] = {}
        for intent in proposal.intents:
            if _side_value(intent.side) == OrderIntentSide.HOLD.value:
                continue
            if intent.target_weight is not None:
                weights[intent.symbol] = intent.target_weight
            if intent.target_shares is not None:
                shares[intent.symbol] = intent.target_shares
        return VectorbtOrderIntentMapping(
            target_weights=dict(sorted(weights.items())),
            target_shares=dict(sorted(shares.items())),
            metadata={
                "adapter": "vectorbt_order_intent",
                "imports_vectorbt": False,
                "advisory_only": proposal.advisory_only,
            },
        )


class RQAlphaPaperIntentAdapter:
    """Disabled pure mapping placeholder for RQAlpha-style order semantics."""

    enabled = False

    def to_order_semantics(self, proposal: OrderIntentProposal) -> DisabledRuntimeAdapterMapping:
        return _disabled_mapping("rqalpha", proposal)


class BacktraderOrderIntentAdapter:
    """Disabled pure mapping placeholder for Backtrader-style order semantics."""

    enabled = False

    def to_order_semantics(self, proposal: OrderIntentProposal) -> DisabledRuntimeAdapterMapping:
        return _disabled_mapping("backtrader", proposal)


def _disabled_mapping(framework: str, proposal: OrderIntentProposal) -> DisabledRuntimeAdapterMapping:
    semantics = tuple(
        {
            "symbol": intent.symbol,
            "side": _side_value(intent.side),
            "target_percent": intent.target_weight,
            "size": intent.target_shares,
            "order_type": "market_paper_placeholder",
        }
        for intent in proposal.intents
    )
    return DisabledRuntimeAdapterMapping(
        framework=framework,
        enabled=False,
        order_semantics=semantics,
        reason=f"{framework} runtime is intentionally disabled in core tests; pure mapping only.",
    )


def _side_value(side: OrderIntentSide | str) -> str:
    return side.value if isinstance(side, OrderIntentSide) else str(side)

