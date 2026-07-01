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
from quantpilot_core.multi_day_paper_replay import (
    PaperReplayDayInput,
    PaperReplayDayStatus,
    PaperReplayDecision,
    run_multi_day_paper_replay,
    validate_replay_inputs,
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
        "quantity": 100,
        "estimated_price": 10.0,
        "limit_price": 10.5,
        "estimated_notional": 1000.0,
        "reason": "accepted_for_paper_candidate",
        "evidence_refs": ("fixture:instruction",),
    }
    values.update(overrides)
    return PaperLedgerCandidateInstruction(**values)


def day(trading_date, *instructions):
    return PaperReplayDayInput(
        trading_date=trading_date,
        instructions=tuple(instructions),
    )


def codes(flags):
    return tuple(flag.code for flag in flags)


def test_valid_two_day_replay_carries_cash_and_positions_forward() -> None:
    result = run_multi_day_paper_replay(
        (
            day("2026-07-01", instruction(proposal_id="buy-1")),
            day(
                "2026-07-02",
                instruction(
                    proposal_id="sell-1",
                    side=ActionSide.SELL.value,
                    quantity=100,
                    estimated_notional=1000.0,
                ),
            ),
        ),
        account(),
    )

    assert result.ok is True
    assert result.decision == PaperReplayDecision.COMPLETED.value
    assert result.final_cash == 49_988.48
    assert result.final_positions == {"600000": 1000}
    assert result.day_results[0].cash_end == 48_994.49
    assert result.day_results[1].cash_start == 48_994.49


def test_buy_on_day_one_cannot_be_sold_on_same_day() -> None:
    result = run_multi_day_paper_replay(
        (
            day(
                "2026-07-01",
                instruction(proposal_id="buy-1"),
                instruction(
                    proposal_id="sell-1",
                    side=ActionSide.SELL.value,
                    quantity=900,
                    estimated_notional=9000.0,
                ),
            ),
        ),
        account(),
    )

    assert result.decision == PaperReplayDecision.PARTIAL.value
    assert result.final_positions == {"600000": 1100}
    assert result.day_results[0].blocked_instruction_ids == ("sell-1",)
    assert "2026-07-01:sellable_quantity_insufficient" in codes(result.risk_flags)


def test_buy_on_day_one_can_be_sold_on_day_two() -> None:
    result = run_multi_day_paper_replay(
        (
            day("2026-07-01", instruction(proposal_id="buy-1")),
            day(
                "2026-07-02",
                instruction(
                    proposal_id="sell-1",
                    side=ActionSide.SELL.value,
                    quantity=900,
                    estimated_notional=9000.0,
                ),
            ),
        ),
        account(),
    )

    assert result.ok is True
    assert result.final_positions == {"600000": 200}


def test_existing_sellable_quantity_can_be_sold_on_day_one() -> None:
    result = run_multi_day_paper_replay(
        (
            day(
                "2026-07-01",
                instruction(
                    proposal_id="sell-existing",
                    side=ActionSide.SELL.value,
                    quantity=800,
                    estimated_notional=8000.0,
                ),
            ),
        ),
        account(),
    )

    assert result.ok is True
    assert result.final_positions == {"600000": 200}


def test_empty_instruction_day_is_noop_but_included() -> None:
    result = run_multi_day_paper_replay(
        (
            day("2026-07-01"),
            day("2026-07-02", instruction(proposal_id="buy-1")),
        ),
        account(),
    )

    assert len(result.day_results) == 2
    assert result.day_results[0].status == PaperReplayDayStatus.SIMULATED.value
    assert result.day_results[0].cash_start == result.day_results[0].cash_end


def test_trading_dates_must_be_strictly_increasing() -> None:
    flags = validate_replay_inputs(
        (
            day("2026-07-02"),
            day("2026-07-01"),
        ),
        account(),
    )

    assert "trading_dates_not_strictly_increasing" in codes(flags)


def test_duplicate_trading_date_is_rejected() -> None:
    flags = validate_replay_inputs(
        (
            day("2026-07-01"),
            day("2026-07-01"),
        ),
        account(),
    )

    assert "duplicate_trading_date" in codes(flags)


def test_duplicate_proposal_id_across_replay_is_rejected() -> None:
    flags = validate_replay_inputs(
        (
            day("2026-07-01", instruction(proposal_id="dup")),
            day("2026-07-02", instruction(proposal_id="dup")),
        ),
        account(),
    )

    assert "duplicate_proposal_id_across_replay" in codes(flags)


def test_invalid_iso_date_shape_is_rejected() -> None:
    flags = validate_replay_inputs((day("20260701"),), account())

    assert "day[0]:trading_date_invalid" in codes(flags)


def test_missing_account_evidence_does_not_block_replay() -> None:
    result = run_multi_day_paper_replay(
        (day("2026-07-01", instruction()),),
        account(evidence_refs=()),
    )

    assert result.decision == PaperReplayDecision.COMPLETED.value
    assert result.day_results
    assert "account_preflight:evidence_refs_missing" not in codes(result.risk_flags)


def test_fail_fast_skips_later_days_after_blocked_day() -> None:
    result = run_multi_day_paper_replay(
        (
            day("2026-07-01", instruction(proposal_id="bad", quantity=900, estimated_notional=9000.0, side=ActionSide.SELL.value)),
            day("2026-07-02", instruction(proposal_id="skipped")),
        ),
        account(),
        fail_fast=True,
    )

    assert result.decision == PaperReplayDecision.BLOCKED.value
    assert result.day_results[0].status == PaperReplayDayStatus.BLOCKED.value
    assert result.day_results[1].status == PaperReplayDayStatus.SKIPPED.value
    assert result.final_positions == {"600000": 1000}


def test_fail_fast_false_continues_after_blocked_day_from_prior_state() -> None:
    result = run_multi_day_paper_replay(
        (
            day("2026-07-01", instruction(proposal_id="bad", quantity=900, estimated_notional=9000.0, side=ActionSide.SELL.value)),
            day("2026-07-02", instruction(proposal_id="good")),
        ),
        account(),
    )

    assert result.decision == PaperReplayDecision.PARTIAL.value
    assert result.day_results[1].status == PaperReplayDayStatus.SIMULATED.value
    assert result.final_positions == {"600000": 1100}


def test_partial_day_carries_only_successful_instructions() -> None:
    result = run_multi_day_paper_replay(
        (
            day(
                "2026-07-01",
                instruction(proposal_id="bad", quantity=900, estimated_notional=9000.0, side=ActionSide.SELL.value),
                instruction(proposal_id="good", quantity=100, estimated_notional=1000.0),
            ),
        ),
        account(),
    )

    assert result.day_results[0].status == PaperReplayDayStatus.PARTIAL.value
    assert result.final_positions == {"600000": 1100}
    assert result.final_cash == 48_994.49


def test_blocked_instruction_does_not_mutate_replay_state() -> None:
    result = run_multi_day_paper_replay(
        (day("2026-07-01", instruction(proposal_id="bad", quantity=900, estimated_notional=9000.0, side=ActionSide.SELL.value)),),
        account(),
    )

    assert result.final_cash == 50_000.0
    assert result.final_positions == {"600000": 1000}


def test_initial_account_profile_is_not_mutated() -> None:
    original = account()

    run_multi_day_paper_replay((day("2026-07-01", instruction()),), original)

    assert original == account()


def test_final_cash_and_positions_are_deterministic() -> None:
    result = run_multi_day_paper_replay(
        (
            day("2026-07-01", instruction(proposal_id="buy-1")),
            day("2026-07-02", instruction(proposal_id="buy-2", quantity=200, estimated_notional=2000.0)),
        ),
        account(),
    )

    assert result.final_cash == 46_988.47
    assert result.final_positions == {"600000": 1300}
