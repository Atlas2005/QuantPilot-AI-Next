from dataclasses import replace

from quantpilot_core.account_profile_preflight import (
    AccountCashProfile,
    AccountPosition,
    AccountProfile,
    AccountRiskLimits,
    AccountStatus,
    BrokerCapability,
    BrokerCapabilityProfile,
    BrokerFeeProfile,
    TradePermission,
)
from quantpilot_core.ai_action_paper_bridge import (
    AIActionProposal,
    ActionSide,
    BridgeDecision,
    ProposalSource,
    estimate_trade_cost,
    run_ai_action_paper_bridge,
)


def account(**overrides):
    values = {
        "account_id": "acct-paper-001",
        "status": AccountStatus.ACTIVE.value,
        "cash": AccountCashProfile(
            currency="CNY",
            available_cash=50_000.0,
            frozen_cash=0.0,
            total_equity=100_000.0,
        ),
        "positions": (
            AccountPosition(
                symbol="600000",
                quantity=1000,
                sellable_quantity=800,
                avg_cost=10.0,
                market_value=10_000.0,
                industry="Banking",
            ),
        ),
        "broker_fee": BrokerFeeProfile(
            commission_rate=0.0003,
            min_commission=5.0,
            stamp_tax_rate=0.0005,
            transfer_fee_rate=0.00001,
            slippage_bps=5.0,
        ),
        "broker_capability": BrokerCapabilityProfile(
            broker_name="offline_fixture_broker",
            market="a_share",
            capabilities=(BrokerCapability.A_SHARE_CASH_EQUITY.value,),
            permissions=(
                TradePermission.BUY.value,
                TradePermission.SELL.value,
                TradePermission.CANCEL.value,
            ),
        ),
        "risk_limits": AccountRiskLimits(
            max_single_symbol_weight=0.5,
            max_industry_weight=0.7,
            max_total_position_weight=0.8,
            max_order_value=30_000.0,
        ),
        "evidence_refs": ("fixture:account",),
    }
    values.update(overrides)
    return AccountProfile(**values)


def proposal(**overrides):
    values = {
        "proposal_id": "proposal-001",
        "source": ProposalSource.AI_SUPERVISOR.value,
        "symbol": "600000",
        "side": ActionSide.BUY.value,
        "quantity": 1000,
        "limit_price": 10.5,
        "estimated_price": 10.0,
        "confidence": 0.8,
        "rationale": "Offline fixture proposal for sandbox review.",
        "evidence_refs": ("fixture:proposal",),
    }
    values.update(overrides)
    return AIActionProposal(**values)


def codes(result):
    return tuple(flag.code for flag in result.risk_flags)


def test_valid_buy_proposal_becomes_paper_candidate_instruction() -> None:
    result = run_ai_action_paper_bridge([proposal()], account())

    assert result.ok is True
    assert result.decision == BridgeDecision.ACCEPTED_FOR_PAPER.value
    assert len(result.accepted_instructions) == 1
    instruction = result.accepted_instructions[0]
    assert instruction.proposal_id == "proposal-001"
    assert instruction.symbol == "600000"
    assert instruction.side == ActionSide.BUY.value
    assert instruction.quantity == 1000
    assert instruction.estimated_notional == 10_000.0
    assert instruction.reason == "accepted_for_paper_candidate"


def test_valid_sell_proposal_becomes_paper_candidate_instruction() -> None:
    result = run_ai_action_paper_bridge(
        [proposal(side=ActionSide.SELL.value, quantity=500)],
        account(),
    )

    assert result.ok is True
    assert result.accepted_instructions[0].side == ActionSide.SELL.value
    assert result.accepted_instructions[0].quantity == 500


def test_hold_proposal_emits_no_instruction_and_remains_ok() -> None:
    result = run_ai_action_paper_bridge(
        [
            proposal(
                side=ActionSide.HOLD.value,
                symbol="",
                quantity=0,
                limit_price=None,
                estimated_price=0.0,
            )
        ],
        account(),
    )

    assert result.ok is True
    assert result.decision == BridgeDecision.ACCEPTED_FOR_PAPER.value
    assert result.accepted_instructions == ()


def test_missing_evidence_refs_is_rejected() -> None:
    result = run_ai_action_paper_bridge([proposal(evidence_refs=())], account())

    assert result.decision == BridgeDecision.BLOCKED.value
    assert "evidence_refs_missing" in codes(result)


def test_invalid_confidence_is_rejected() -> None:
    result = run_ai_action_paper_bridge([proposal(confidence=1.1)], account())

    assert "confidence_out_of_range" in codes(result)


def test_buy_without_buy_permission_is_blocked() -> None:
    limited_account = account(
        broker_capability=replace(
            account().broker_capability,
            permissions=(TradePermission.SELL.value,),
        )
    )
    result = run_ai_action_paper_bridge([proposal()], limited_account)

    assert "buy_permission_missing" in codes(result)


def test_sell_without_sell_permission_is_blocked() -> None:
    limited_account = account(
        broker_capability=replace(
            account().broker_capability,
            permissions=(TradePermission.BUY.value,),
        )
    )
    result = run_ai_action_paper_bridge(
        [proposal(side=ActionSide.SELL.value)],
        limited_account,
    )

    assert "sell_permission_missing" in codes(result)


def test_read_only_account_blocks_buy_sell() -> None:
    result = run_ai_action_paper_bridge(
        [proposal()],
        account(status=AccountStatus.READ_ONLY.value),
    )

    assert result.decision == BridgeDecision.BLOCKED.value
    assert result.reason == "account_preflight_failed"
    assert "account_preflight:read_only_trade_permission_active" in codes(result)


def test_kill_switched_account_blocks_buy_sell() -> None:
    result = run_ai_action_paper_bridge(
        [proposal(side=ActionSide.SELL.value)],
        account(status=AccountStatus.KILL_SWITCHED.value),
    )

    assert result.decision == BridgeDecision.BLOCKED.value
    assert "account_preflight:kill_switched_trade_permission_active" in codes(result)


def test_buy_exceeding_available_cash_is_blocked() -> None:
    result = run_ai_action_paper_bridge(
        [proposal(quantity=5000, estimated_price=10.0)],
        account(cash=replace(account().cash, available_cash=10_000.0)),
    )

    assert "buy_cash_insufficient" in codes(result)


def test_sell_exceeding_sellable_quantity_is_blocked() -> None:
    result = run_ai_action_paper_bridge(
        [proposal(side=ActionSide.SELL.value, quantity=900)],
        account(),
    )

    assert "sellable_quantity_insufficient" in codes(result)


def test_max_order_value_breach_is_blocked() -> None:
    result = run_ai_action_paper_bridge(
        [proposal(quantity=4000, estimated_price=10.0)],
        account(),
    )

    assert "max_order_value_breached" in codes(result)


def test_non_100_lot_a_share_quantity_is_blocked_by_default() -> None:
    result = run_ai_action_paper_bridge([proposal(quantity=150)], account())

    assert "a_share_lot_size_invalid" in codes(result)


def test_allow_odd_lot_allows_odd_lot_when_explicit() -> None:
    result = run_ai_action_paper_bridge(
        [proposal(quantity=150)],
        account(),
        allow_odd_lot=True,
    )

    assert result.ok is True
    assert result.accepted_instructions[0].quantity == 150


def test_low_confidence_proposal_requires_manual_review() -> None:
    result = run_ai_action_paper_bridge([proposal(confidence=0.5)], account())

    assert result.ok is False
    assert result.decision == BridgeDecision.REQUIRES_MANUAL_REVIEW.value
    assert "confidence_below_threshold" in codes(result)
    assert result.accepted_instructions == ()


def test_invalid_account_preflight_blocks_all_proposals() -> None:
    result = run_ai_action_paper_bridge(
        [proposal(proposal_id="p1"), proposal(proposal_id="p2")],
        account(evidence_refs=()),
    )

    assert result.decision == BridgeDecision.BLOCKED.value
    assert result.blocked_proposals == ("p1", "p2")
    assert "account_preflight:evidence_refs_missing" in codes(result)


def test_fee_estimate_includes_commission_min_stamp_transfer_and_slippage() -> None:
    broker_fee = account().broker_fee

    assert estimate_trade_cost(proposal(), broker_fee) == 10.1
    assert estimate_trade_cost(proposal(side=ActionSide.SELL.value), broker_fee) == 15.1


def test_bridge_does_not_mutate_account_profile() -> None:
    original = account()

    run_ai_action_paper_bridge([proposal()], original)

    assert original == account()


def test_deterministic_accepted_instruction_fields() -> None:
    result = run_ai_action_paper_bridge(
        [
            proposal(
                proposal_id="deterministic-001",
                side=ActionSide.SELL.value,
                quantity=200,
                estimated_price=11.0,
                limit_price=10.8,
            )
        ],
        account(),
    )

    assert result.accepted_instructions[0].proposal_id == "deterministic-001"
    assert result.accepted_instructions[0].estimated_notional == 2200.0
    assert result.accepted_instructions[0].evidence_refs == ("fixture:proposal",)
