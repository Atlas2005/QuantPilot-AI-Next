from copy import deepcopy
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
    ActionSide,
    PaperLedgerCandidateInstruction,
)
from quantpilot_core.broker_sandbox_adapter_preflight import (
    BrokerSandboxAdapterDecision,
    BrokerSandboxAdapterMode,
    BrokerSandboxInstruction,
    BrokerSandboxInstructionStatus,
    run_broker_sandbox_adapter_preflight,
    to_broker_sandbox_instruction,
    validate_broker_sandbox_instruction,
)
from quantpilot_core.small_capital_readiness_gate import (
    ReadinessDecision,
    SmallCapitalReadinessGateResult,
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


def readiness(decision=ReadinessDecision.PASS.value):
    return SmallCapitalReadinessGateResult(
        ok=decision == ReadinessDecision.PASS.value,
        decision=decision,
        reason="ok" if decision == ReadinessDecision.PASS.value else "not_ready",
        metrics=(),
        risk_flags=(),
        passed_checks=(),
        failed_checks=("fixture_failed",) if decision == ReadinessDecision.FAIL.value else (),
        manual_review_checks=("fixture_review",) if decision == ReadinessDecision.MANUAL_REVIEW.value else (),
    )


def instruction(**overrides):
    values = {
        "instruction_id": "sandbox-001",
        "proposal_id": "proposal-001",
        "symbol": "600000",
        "side": ActionSide.BUY.value,
        "quantity": 1000,
        "estimated_price": 10.0,
        "limit_price": 10.5,
        "estimated_notional": 10_000.0,
        "mode": BrokerSandboxAdapterMode.BROKER_SANDBOX.value,
        "evidence_refs": ("fixture:instruction",),
    }
    values.update(overrides)
    return BrokerSandboxInstruction(**values)


def candidate(**overrides):
    values = {
        "proposal_id": "proposal-001",
        "symbol": "600000",
        "side": ActionSide.BUY.value,
        "quantity": 1000,
        "estimated_price": 10.0,
        "limit_price": 10.5,
        "estimated_notional": 10_000.0,
        "reason": "accepted_for_paper_candidate",
        "evidence_refs": ("fixture:candidate",),
    }
    values.update(overrides)
    return PaperLedgerCandidateInstruction(**values)


def codes(result):
    return tuple(flag.code for flag in result.risk_flags)


def test_valid_readiness_pass_and_buy_instruction_returns_ready() -> None:
    result = run_broker_sandbox_adapter_preflight([instruction()], account(), readiness())

    assert result.ok is True
    assert result.decision == BrokerSandboxAdapterDecision.READY.value
    assert result.accepted_instruction_ids == ("sandbox-001",)
    assert result.instruction_results[0].status == BrokerSandboxInstructionStatus.ACCEPTED_FOR_SANDBOX.value


def test_valid_readiness_pass_and_sell_instruction_returns_ready() -> None:
    result = run_broker_sandbox_adapter_preflight(
        [
            instruction(
                side=ActionSide.SELL.value,
                quantity=500,
                estimated_notional=5000.0,
            )
        ],
        account(),
        readiness(),
    )

    assert result.decision == BrokerSandboxAdapterDecision.READY.value


def test_readiness_fail_blocks_all_executable_instructions() -> None:
    result = run_broker_sandbox_adapter_preflight([instruction()], account(), readiness(ReadinessDecision.FAIL.value))

    assert result.decision == BrokerSandboxAdapterDecision.BLOCKED.value
    assert "readiness_failed" in codes(result)


def test_readiness_manual_review_produces_manual_review_decision() -> None:
    result = run_broker_sandbox_adapter_preflight(
        [instruction()],
        account(),
        readiness(ReadinessDecision.MANUAL_REVIEW.value),
    )

    assert result.decision == BrokerSandboxAdapterDecision.MANUAL_REVIEW.value
    assert "readiness_manual_review" in codes(result)


def test_read_only_account_blocks_buy_sell() -> None:
    result = run_broker_sandbox_adapter_preflight(
        [instruction()],
        account(status=AccountStatus.READ_ONLY.value),
        readiness(),
    )

    assert result.decision == BrokerSandboxAdapterDecision.BLOCKED.value
    assert "account_status_blocks_trade" in codes(result)


def test_kill_switched_account_blocks_buy_sell() -> None:
    result = run_broker_sandbox_adapter_preflight(
        [instruction(side=ActionSide.SELL.value)],
        account(status=AccountStatus.KILL_SWITCHED.value),
        readiness(),
    )

    assert result.decision == BrokerSandboxAdapterDecision.BLOCKED.value
    assert "account_status_blocks_trade" in codes(result)


def test_buy_without_buy_permission_is_blocked() -> None:
    limited_account = account(
        broker_capability=replace(
            account().broker_capability,
            permissions=(TradePermission.SELL.value,),
        )
    )
    result = run_broker_sandbox_adapter_preflight([instruction()], limited_account, readiness())

    assert "buy_permission_missing" in codes(result)


def test_sell_without_sell_permission_is_blocked() -> None:
    limited_account = account(
        broker_capability=replace(
            account().broker_capability,
            permissions=(TradePermission.BUY.value,),
        )
    )
    result = run_broker_sandbox_adapter_preflight(
        [instruction(side=ActionSide.SELL.value)],
        limited_account,
        readiness(),
    )

    assert "sell_permission_missing" in codes(result)


def test_query_only_only_allows_read_only_check() -> None:
    query_account = account(
        broker_capability=replace(
            account().broker_capability,
            permissions=(TradePermission.QUERY_ONLY.value,),
        )
    )
    blocked = run_broker_sandbox_adapter_preflight([instruction()], query_account, readiness())
    allowed = run_broker_sandbox_adapter_preflight(
        [instruction(mode=BrokerSandboxAdapterMode.READ_ONLY_CHECK.value)],
        query_account,
        readiness(),
    )

    assert "query_only_requires_read_only_check" in codes(blocked)
    assert allowed.decision == BrokerSandboxAdapterDecision.MANUAL_REVIEW.value
    assert "query_only_requires_read_only_check" not in codes(allowed)


def test_paper_only_mode_does_not_claim_broker_readiness() -> None:
    result = run_broker_sandbox_adapter_preflight(
        [instruction(mode=BrokerSandboxAdapterMode.PAPER_ONLY.value)],
        account(),
        readiness(),
    )

    assert result.decision == BrokerSandboxAdapterDecision.MANUAL_REVIEW.value
    assert "paper_only_not_broker_ready" in codes(result)


def test_hold_instruction_is_skipped_and_not_executable() -> None:
    result = run_broker_sandbox_adapter_preflight(
        [
            instruction(
                side=ActionSide.HOLD.value,
                quantity=0,
                estimated_price=0.0,
                estimated_notional=0.0,
            )
        ],
        account(),
        readiness(),
    )

    assert result.decision == BrokerSandboxAdapterDecision.MANUAL_REVIEW.value
    assert result.instruction_results[0].status == BrokerSandboxInstructionStatus.SKIPPED.value


def test_missing_evidence_refs_is_rejected() -> None:
    flags = validate_broker_sandbox_instruction(instruction(evidence_refs=()))

    assert "evidence_refs_missing" in tuple(flag.code for flag in flags)


def test_invalid_estimated_notional_mismatch_is_rejected() -> None:
    flags = validate_broker_sandbox_instruction(instruction(estimated_notional=9999.0))

    assert "estimated_notional_mismatch" in tuple(flag.code for flag in flags)


def test_non_100_lot_a_share_instruction_is_blocked_by_default() -> None:
    result = run_broker_sandbox_adapter_preflight(
        [instruction(quantity=150, estimated_notional=1500.0)],
        account(),
        readiness(),
    )

    assert "a_share_lot_size_invalid" in codes(result)


def test_allow_odd_lot_allows_odd_lot_when_explicitly_enabled() -> None:
    result = run_broker_sandbox_adapter_preflight(
        [instruction(quantity=150, estimated_notional=1500.0)],
        account(),
        readiness(),
        allow_odd_lot=True,
    )

    assert result.decision == BrokerSandboxAdapterDecision.READY.value


def test_buy_exceeding_cash_is_blocked() -> None:
    result = run_broker_sandbox_adapter_preflight(
        [instruction(quantity=5000, estimated_notional=50_000.0)],
        account(),
        readiness(),
    )

    assert "buy_cash_insufficient" in codes(result)


def test_sell_exceeding_sellable_quantity_is_blocked() -> None:
    result = run_broker_sandbox_adapter_preflight(
        [
            instruction(
                side=ActionSide.SELL.value,
                quantity=900,
                estimated_notional=9000.0,
            )
        ],
        account(),
        readiness(),
    )

    assert "sellable_quantity_insufficient" in codes(result)


def test_to_broker_sandbox_instruction_converts_candidate_deterministically() -> None:
    converted = to_broker_sandbox_instruction(
        candidate(),
        instruction_id="sandbox-det-001",
        mode=BrokerSandboxAdapterMode.BROKER_SANDBOX.value,
    )

    assert converted.instruction_id == "sandbox-det-001"
    assert converted.proposal_id == "proposal-001"
    assert converted.symbol == "600000"
    assert converted.estimated_notional == 10_000.0
    assert converted.evidence_refs == ("fixture:candidate",)


def test_no_mutation_of_account_profile() -> None:
    original = account()
    snapshot = deepcopy(original)

    run_broker_sandbox_adapter_preflight([instruction()], original, readiness())

    assert original == snapshot
