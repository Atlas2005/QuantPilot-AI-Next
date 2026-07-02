"""Order intent controller for EXEC2 and advisory evidence handoff."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, Mapping

from quantpilot_core.execution_optimizer import PortfolioAllocationPlan
from quantpilot_core.order_intent.contracts import (
    OrderIntent,
    OrderIntentProposal,
    OrderIntentProposalSource,
    OrderIntentSide,
)


class OrderIntentController:
    """Normalize advisory allocation output into paper-trading-ready intents."""

    def __init__(self, *, lot_size: int = 100) -> None:
        if lot_size <= 0:
            raise ValueError("lot_size must be positive")
        self.lot_size = lot_size

    def from_exec2_plan(
        self,
        plan: PortfolioAllocationPlan,
        *,
        deepseek_advisory: Any | None = None,
        committee_metadata: Mapping[str, Any] | None = None,
        run_label: str | None = None,
    ) -> OrderIntentProposal:
        """Convert an EXEC2 allocation plan into advisory-only paper intents."""

        if not isinstance(plan, PortfolioAllocationPlan):
            raise TypeError("plan must be a PortfolioAllocationPlan")

        intents = []
        for allocation in plan.allocations:
            side = OrderIntentSide.BUY if allocation.target_shares > 0 or allocation.target_weight > 0 else OrderIntentSide.HOLD
            target_shares = self._normalize_shares(allocation.target_shares)
            reason = self._reason_for_allocation(allocation.symbol, allocation.limitations, deepseek_advisory)
            metadata = {
                "raw_score": allocation.raw_score,
                "normalized_score": allocation.normalized_score,
                "cost_adjusted_score": allocation.cost_adjusted_score,
                "target_notional": allocation.target_notional,
                "cost_estimate_total": allocation.cost_estimate.total_cost,
                "vectorbt_weight": allocation.vectorbt_weight,
                "limitations": allocation.limitations,
                "no_broker_live_execution": True,
            }
            if deepseek_advisory is not None:
                role = getattr(deepseek_advisory, "role", None)
                metadata["deepseek_role"] = getattr(role, "value", role)
                metadata["deepseek_evidence_used"] = getattr(deepseek_advisory, "evidence_used", ())
            if allocation.target_shares != target_shares:
                metadata["share_normalization"] = "rounded_down_to_100_share_lot"
            intents.append(
                OrderIntent(
                    symbol=allocation.symbol,
                    side=side,
                    target_weight=allocation.target_weight,
                    target_shares=target_shares,
                    reason=reason,
                    source_agent="exec2",
                    confidence=allocation.cost_adjusted_score,
                    strategy_id=plan.strategy_id,
                    run_label=run_label,
                    metadata=metadata,
                )
            )

        proposal_metadata = {
            "strategy_id": plan.strategy_id,
            "cash_weight": plan.cash_weight,
            "gross_exposure": plan.gross_exposure,
            "total_target_notional": plan.total_target_notional,
            "total_estimated_cost": plan.total_estimated_cost,
            "exec2_limitations": plan.limitations,
            "no_broker_live_execution": True,
        }
        if committee_metadata:
            proposal_metadata["investment_committee"] = dict(committee_metadata)
        if deepseek_advisory is not None:
            proposal_metadata["deepseek_advisory_summary"] = deepseek_advisory.advisory_summary

        return OrderIntentProposal(
            intents=tuple(intents),
            proposal_source=OrderIntentProposalSource.EXEC2,
            advisory_only=True,
            created_at=_utc_now_iso(),
            run_label=run_label,
            metadata=proposal_metadata,
        )

    def normalize_proposal(self, proposal: OrderIntentProposal) -> OrderIntentProposal:
        """Normalize side and lot constraints without acting as a hard blocker."""

        normalized = tuple(self.normalize_intent(intent) for intent in proposal.intents)
        metadata = dict(proposal.metadata)
        metadata["normalized_for_paper_trading"] = True
        metadata["no_broker_live_execution"] = True
        return replace(proposal, intents=normalized, advisory_only=True, metadata=metadata)

    def normalize_intent(self, intent: OrderIntent) -> OrderIntent:
        """Normalize one intent into the deterministic A-share paper boundary."""

        side = self._normalize_side(intent.side)
        target_shares = self._normalize_shares(intent.target_shares)
        metadata = dict(intent.metadata)
        metadata["a_share_lot_size"] = self.lot_size
        metadata["no_broker_live_execution"] = True
        if intent.target_shares is not None and target_shares != intent.target_shares:
            metadata["share_normalization"] = "rounded_down_to_100_share_lot"
        if side is OrderIntentSide.HOLD:
            target_shares = target_shares if target_shares and target_shares > 0 else None
        return replace(intent, side=side, target_shares=target_shares, metadata=metadata)

    def _normalize_side(self, side: OrderIntentSide | str) -> OrderIntentSide:
        try:
            return side if isinstance(side, OrderIntentSide) else OrderIntentSide(str(side).lower())
        except ValueError as exc:
            raise ValueError(f"unsupported order intent side: {side}") from exc

    def _normalize_shares(self, shares: int | None) -> int | None:
        if shares is None:
            return None
        if shares <= 0:
            return None
        return (shares // self.lot_size) * self.lot_size or None

    def _reason_for_allocation(
        self,
        symbol: str,
        limitations: tuple[str, ...],
        deepseek_advisory: Any | None,
    ) -> str:
        parts = [f"EXEC2 allocation intent for {symbol}."]
        if limitations:
            parts.append(" ".join(limitations))
        if deepseek_advisory is not None:
            parts.append(f"DeepSeek advisory rationale: {getattr(deepseek_advisory, 'advisory_summary', '')}")
        return " ".join(parts)


def build_order_intent_proposal(
    plan: PortfolioAllocationPlan,
    *,
    deepseek_advisory: Any | None = None,
    committee_metadata: Mapping[str, Any] | None = None,
    run_label: str | None = None,
    lot_size: int = 100,
) -> OrderIntentProposal:
    """Registry-safe wrapper for building paper-trading order intents."""

    controller = OrderIntentController(lot_size=lot_size)
    return controller.from_exec2_plan(
        plan,
        deepseek_advisory=deepseek_advisory,
        committee_metadata=committee_metadata,
        run_label=run_label,
    )


def _utc_now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()
