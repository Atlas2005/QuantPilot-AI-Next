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
from quantpilot_core.ai_action_paper_bridge import ActionSide, PaperLedgerCandidateInstruction
from quantpilot_core.paper_ledger_dry_run import (
    PaperLedgerDryRunDecision,
    PaperLedgerDryRunInstructionStatus,
    run_paper_ledger_dry_run,
    simulate_instruction,
    validate_dry_run_instruction,
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


def instruction(**overrides):
    values = {
        "proposal_id": "proposal-001",
        "symbol": "600000",
        "side": ActionSide.BUY.value,
        "quantity": 1000,
        "estimated_price": 10.0,
        "limit_price": 10.5,
        "estimated_notional": 10_000.0,
        "reason": "accepted_for_paper_candidate",
        "evidence_refs": ("fixture:instruction",),
    }
    values.update(overrides)
    return PaperLedgerCandidateInstruction(**values)


def codes(result):
    return tuple(flag.code for flag in result.risk_flags)


def test_valid_buy_instruction_simulates_cash_decrease_and_position_increase() -> None:
    result = run_paper_ledger_dry_run([instruction()], account())

    assert result.ok is True
    assert result.decision == PaperLedgerDryRunDecision.ACCEPTED.value
    assert result.simulated_cash_after == 39_989.9
    assert result.simulated_positions_after == {"600000": 2000}
    assert result.instruction_results[0].estimated_cash_delta == -10_010.1
    assert result.instruction_results[0].estimated_position_delta == 1000


def test_valid_sell_instruction_simulates_cash_increase_and_position_decrease() -> None:
    result = run_paper_ledger_dry_run(
        [instruction(side=ActionSide.SELL.value, quantity=500, estimated_notional=5000.0)],
        account(),
    )

    assert result.ok is True
    assert result.simulated_cash_after == 54_989.95
    assert result.simulated_positions_after == {"600000": 500}
    assert result.instruction_results[0].estimated_cash_delta == 4989.95
    assert result.instruction_results[0].estimated_position_delta == -500


def test_buy_exceeding_available_cash_is_blocked() -> None:
    result = run_paper_ledger_dry_run(
        [instruction(quantity=5000, estimated_notional=50_000.0)],
        account(),
    )

    assert result.decision == PaperLedgerDryRunDecision.BLOCKED.value
    assert "buy_cash_insufficient" in codes(result.instruction_results[0])


def test_sell_exceeding_sellable_quantity_is_blocked() -> None:
    result = run_paper_ledger_dry_run(
        [instruction(side=ActionSide.SELL.value, quantity=900, estimated_notional=9000.0)],
        account(),
    )

    assert "sellable_quantity_insufficient" in codes(result.instruction_results[0])


def test_non_100_lot_a_share_instruction_is_blocked_by_default() -> None:
    result = run_paper_ledger_dry_run(
        [instruction(quantity=150, estimated_notional=1500.0)],
        account(),
    )

    assert "a_share_lot_size_invalid" in codes(result.instruction_results[0])


def test_allow_odd_lot_allows_odd_lot_when_explicit() -> None:
    result = run_paper_ledger_dry_run(
        [instruction(quantity=150, estimated_notional=1500.0)],
        account(),
        allow_odd_lot=True,
    )

    assert result.ok is True
    assert result.instruction_results[0].status == PaperLedgerDryRunInstructionStatus.SIMULATED.value


def test_duplicate_proposal_id_is_rejected() -> None:
    result = run_paper_ledger_dry_run(
        [
            instruction(proposal_id="duplicate"),
            instruction(proposal_id="duplicate"),
        ],
        account(),
    )

    assert result.decision == PaperLedgerDryRunDecision.PARTIAL.value
    assert result.blocked_instruction_ids == ("duplicate",)
    assert "duplicate_proposal_id" in codes(result.instruction_results[1])


def test_invalid_estimated_notional_mismatch_is_rejected() -> None:
    flags = validate_dry_run_instruction(instruction(estimated_notional=9999.0))

    assert "estimated_notional_mismatch" in tuple(flag.code for flag in flags)


def test_missing_evidence_refs_is_rejected() -> None:
    flags = validate_dry_run_instruction(instruction(evidence_refs=()))

    assert "evidence_refs_missing" in tuple(flag.code for flag in flags)


def test_hold_instruction_reaching_dry_run_is_rejected() -> None:
    result = run_paper_ledger_dry_run(
        [
            instruction(
                side=ActionSide.HOLD.value,
                quantity=0,
                estimated_price=0.0,
                estimated_notional=0.0,
            )
        ],
        account(),
    )

    assert "hold_instruction_not_allowed" in codes(result.instruction_results[0])


def test_read_only_account_warns_without_blocking_paper_dry_run() -> None:
    result = run_paper_ledger_dry_run(
        [instruction()],
        account(status=AccountStatus.READ_ONLY.value),
    )

    assert result.decision == PaperLedgerDryRunDecision.ACCEPTED.value
    assert "account_preflight:read_only_trade_permission_active" in codes(result)


def test_kill_switched_account_warns_without_blocking_paper_dry_run() -> None:
    result = run_paper_ledger_dry_run(
        [instruction(side=ActionSide.SELL.value, quantity=500, estimated_notional=5000.0)],
        account(status=AccountStatus.KILL_SWITCHED.value),
    )

    assert result.decision == PaperLedgerDryRunDecision.ACCEPTED.value
    assert "account_preflight:kill_switched_trade_permission_active" in codes(result)


def test_missing_account_evidence_does_not_block_whole_dry_run() -> None:
    result = run_paper_ledger_dry_run([instruction()], account(evidence_refs=()))

    assert result.decision == PaperLedgerDryRunDecision.ACCEPTED.value
    assert result.instruction_results
    assert result.blocked_instruction_ids == ()
    assert "account_preflight:evidence_refs_missing" not in codes(result)


def test_partial_decision_when_one_instruction_blocked_and_another_succeeds() -> None:
    result = run_paper_ledger_dry_run(
        [
            instruction(proposal_id="bad", quantity=5000, estimated_notional=50_000.0),
            instruction(proposal_id="good", quantity=100, estimated_notional=1000.0),
        ],
        account(),
    )

    assert result.ok is False
    assert result.decision == PaperLedgerDryRunDecision.PARTIAL.value
    assert result.blocked_instruction_ids == ("bad",)
    assert result.instruction_results[1].status == PaperLedgerDryRunInstructionStatus.SIMULATED.value


def test_fail_fast_blocks_and_skips_remaining_instructions() -> None:
    result = run_paper_ledger_dry_run(
        [
            instruction(proposal_id="bad", quantity=5000, estimated_notional=50_000.0),
            instruction(proposal_id="skipped", quantity=100, estimated_notional=1000.0),
        ],
        account(),
        fail_fast=True,
    )

    assert result.decision == PaperLedgerDryRunDecision.BLOCKED.value
    assert result.instruction_results[0].status == PaperLedgerDryRunInstructionStatus.REJECTED.value
    assert result.instruction_results[1].status == PaperLedgerDryRunInstructionStatus.SKIPPED.value


def test_deterministic_simulated_positions_after() -> None:
    result = run_paper_ledger_dry_run(
        [
            instruction(proposal_id="buy", quantity=100, estimated_notional=1000.0),
            instruction(
                proposal_id="sell",
                side=ActionSide.SELL.value,
                quantity=200,
                estimated_notional=2000.0,
            ),
        ],
        account(),
    )

    assert result.simulated_positions_after == {"600000": 900}


def test_dry_run_does_not_mutate_account_profile() -> None:
    original = account()

    run_paper_ledger_dry_run([instruction()], original)

    assert original == account()


def test_fee_estimate_includes_commission_min_stamp_transfer_and_slippage() -> None:
    buy_result = simulate_instruction(
        instruction(),
        account(),
        current_cash=50_000.0,
        current_positions={"600000": 1000},
    )
    sell_result = simulate_instruction(
        instruction(side=ActionSide.SELL.value),
        account(positions=(replace(account().positions[0], sellable_quantity=1000),)),
        current_cash=50_000.0,
        current_positions={"600000": 1000},
    )

    assert buy_result.estimated_cash_delta == -10_010.1
    assert sell_result.estimated_cash_delta == 9984.9
