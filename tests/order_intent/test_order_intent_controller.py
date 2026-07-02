from __future__ import annotations

from quantpilot_core.execution_optimizer import (
    AllocationCostEstimate,
    OptimizationAssumption,
    PortfolioAllocation,
    PortfolioAllocationPlan,
)
from quantpilot_core.order_intent import (
    OrderIntent,
    OrderIntentController,
    OrderIntentProposal,
    OrderIntentProposalSource,
    OrderIntentSide,
    build_order_intent_proposal,
)
from quantpilot_core.quant_firm import DeepSeekAdvisoryOutput, DeepSeekAdvisoryRole


def allocation(**overrides):
    values = {
        "symbol": "600000",
        "raw_score": 0.8,
        "normalized_score": 1.0,
        "cost_adjusted_score": 0.92,
        "target_weight": 0.2,
        "target_notional": 2000.0,
        "target_shares": 200,
        "cost_estimate": AllocationCostEstimate(fee=1.0, slippage=1.0, turnover_penalty=0.5, total_cost=2.5),
        "vectorbt_weight": 0.2,
        "limitations": ("A-share 100-share lot rounding is applied to target shares.",),
    }
    values.update(overrides)
    return PortfolioAllocation(**values)


def plan(*allocations: PortfolioAllocation) -> PortfolioAllocationPlan:
    rows = allocations or (allocation(),)
    return PortfolioAllocationPlan(
        strategy_id="strategy-a:EXEC2",
        allocations=tuple(rows),
        cash_weight=0.8,
        gross_exposure=sum(row.target_weight for row in rows),
        total_target_notional=sum(row.target_notional for row in rows),
        total_estimated_cost=sum(row.cost_estimate.total_cost for row in rows),
        assumptions=OptimizationAssumption(),
        vectorbt_weights={row.symbol: row.vectorbt_weight for row in rows},
        target_shares={row.symbol: row.target_shares for row in rows},
        limitations=("Offline deterministic portfolio allocation plan for downstream simulation.",),
    )


def advisory() -> DeepSeekAdvisoryOutput:
    return DeepSeekAdvisoryOutput(
        role=DeepSeekAdvisoryRole.PORTFOLIO_DESK,
        advisory_summary="Review cost drag before paper simulation.",
        evidence_used=("portfolio_allocation_plan_summary",),
        failure_explanation="No failure artifact supplied.",
        strategy_mutation_rationale="Keep changes offline.",
        parameter_tuning_suggestions=("review_turnover_penalty",),
        research_directions=("compare_cost_fragility",),
        regime_notes=("market_regime_not_supplied",),
        risk_notes=("flag_cost_drag",),
        tool_integration_notes=("do_not_emit_trade_execution_commands",),
        confidence=0.7,
        used_model="deterministic_fallback",
        is_fallback=True,
    )


def test_exec2_allocation_converts_to_order_intents() -> None:
    proposal = build_order_intent_proposal(plan(), run_label="unit")

    assert proposal.proposal_source is OrderIntentProposalSource.EXEC2
    assert proposal.advisory_only is True
    assert len(proposal.intents) == 1
    intent = proposal.intents[0]
    assert intent.symbol == "600000"
    assert intent.side is OrderIntentSide.BUY
    assert intent.target_weight == 0.2
    assert intent.target_shares == 200
    assert intent.strategy_id == "strategy-a:EXEC2"
    assert intent.metadata["no_broker_live_execution"] is True


def test_deepseek_advisory_rationale_enriches_intent_reason() -> None:
    proposal = build_order_intent_proposal(plan(), deepseek_advisory=advisory())

    assert "DeepSeek advisory rationale" in proposal.intents[0].reason
    assert "Review cost drag before paper simulation." in proposal.intents[0].reason
    assert proposal.metadata["deepseek_advisory_summary"] == "Review cost drag before paper simulation."


def test_a_share_100_share_lot_rule_is_preserved_by_controller() -> None:
    proposal = build_order_intent_proposal(plan(allocation(target_shares=250)))

    assert proposal.intents[0].target_shares == 200
    assert proposal.intents[0].metadata["share_normalization"] == "rounded_down_to_100_share_lot"


def test_invalid_quantity_is_normalized_without_hard_blocking_pipeline() -> None:
    controller = OrderIntentController()
    proposal = controller.normalize_proposal(
        OrderIntentProposal(
            intents=(OrderIntent(symbol="600000", side="buy", target_shares=-10),),
            proposal_source="learning_desk",
        )
    )

    assert proposal.advisory_only is True
    assert proposal.intents[0].target_shares is None
    assert proposal.metadata["normalized_for_paper_trading"] is True


def test_invalid_side_raises_deterministic_contract_error() -> None:
    controller = OrderIntentController()
    proposal = OrderIntentProposal(
        intents=(OrderIntent(symbol="600000", side="short", target_shares=100),),
        proposal_source="learning_desk",
    )

    try:
        controller.normalize_proposal(proposal)
    except ValueError as exc:
        assert "unsupported order intent side" in str(exc)
    else:
        raise AssertionError("expected invalid side to raise ValueError")

