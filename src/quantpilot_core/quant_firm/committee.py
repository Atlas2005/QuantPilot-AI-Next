"""Investment committee aggregation for the Quant Firm simulation layer."""

from __future__ import annotations

from typing import Iterable

from quantpilot_core.quant_firm.contracts import (
    AgentDecision,
    AgentRecommendation,
    QuantFirmAgentRole,
)


class InvestmentCommitteeAgent:
    """Aggregate deterministic specialist recommendations."""

    role = QuantFirmAgentRole.INVESTMENT_COMMITTEE

    def decide(self, recommendations: Iterable[AgentRecommendation]) -> AgentDecision:
        items = tuple(recommendations)
        if not items:
            confidence = 0.0
            action = "no_recommendations_available"
            rationale = "No specialist recommendations were supplied to the committee."
        else:
            active = tuple(item for item in items if not item.decision.disabled)
            confidence = round(sum(item.score for item in active) / len(active), 6) if active else 0.0
            action = "approve_offline_shadow_cycle" if confidence >= 0.65 else "request_more_offline_evidence"
            rationale = (
                "Committee aggregated deterministic specialist outputs; broker adapter remains disabled "
                "and any future DeepSeek reasoning is advisory only."
            )
        return AgentDecision(
            role=self.role,
            action=action,
            confidence=confidence,
            rationale=rationale,
            evidence_refs=tuple(ref for item in items for ref in item.decision.evidence_refs),
            metadata={
                "recommendation_count": len(items),
                "disabled_roles": tuple(item.role.value for item in items if item.decision.disabled),
                "no_llm_call": True,
                "no_external_api": True,
            },
            advisory_reasoning_hook="deepseek_advisory_only:investment_committee",
        )
