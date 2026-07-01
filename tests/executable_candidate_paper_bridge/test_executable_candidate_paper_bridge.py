from __future__ import annotations

from dataclasses import replace
from pathlib import Path

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
from quantpilot_core.ai_action_paper_bridge import ActionSide
from quantpilot_core.executable_candidate import (
    CandidateAssetType,
    CandidateSide,
    ExecutableCandidateInput,
    evaluate_executable_candidate,
)
from quantpilot_core.executable_candidate.contracts import ExecutableCandidateDecision
from quantpilot_core.executable_candidate_paper_bridge import (
    CandidatePaperBridgeInput,
    build_candidate_paper_bridge_report,
    build_paper_ledger_instruction_from_candidate,
    run_candidate_paper_dry_run,
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
            permissions=(TradePermission.BUY.value, TradePermission.SELL.value),
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


def candidate_input(**overrides) -> ExecutableCandidateInput:
    values = {
        "symbol": "600000",
        "side": CandidateSide.BUY,
        "asset_type": CandidateAssetType.STOCK,
        "signal_score": 0.7,
        "reference_price": 10.0,
        "desired_quantity": 1000,
        "available_cash": 50_000.0,
        "current_position": 1000,
        "sellable_position": 800,
        "previous_close": 9.9,
        "is_suspended": False,
        "is_limit_up": False,
        "is_limit_down": False,
        "available_volume": 100_000,
        "max_participation_rate": 0.1,
        "commission_rate": 0.0003,
        "min_commission": 5.0,
        "stamp_duty_rate": 0.0005,
        "slippage_bps": 2.0,
    }
    values.update(overrides)
    return ExecutableCandidateInput(**values)


def bridge_input(
    *,
    candidate: ExecutableCandidateInput | None = None,
    decision: ExecutableCandidateDecision | None = None,
    account_profile: AccountProfile | None = None,
    evidence_refs: tuple[str, ...] = ("fixture:candidate",),
    proposal_id: str = "candidate-001",
    dry_run_only: bool = True,
) -> CandidatePaperBridgeInput:
    active_candidate = candidate or candidate_input()
    active_decision = decision or evaluate_executable_candidate(active_candidate)
    return CandidatePaperBridgeInput(
        candidate_input=active_candidate,
        candidate_decision=active_decision,
        account_profile=account_profile or account(),
        evidence_refs=evidence_refs,
        proposal_id=proposal_id,
        trade_date="2026-01-02",
        dry_run_only=dry_run_only,
    )


def issue_codes(result) -> tuple[str, ...]:
    return tuple(issue.code for issue in result.issues)


def dry_run_codes(result) -> tuple[str, ...]:
    assert result.dry_run_result is not None
    return tuple(flag.code for flag in result.dry_run_result.risk_flags)


def test_accepted_buy_candidate_creates_dry_run_buy_instruction_using_executable_quantity() -> None:
    candidate = candidate_input(desired_quantity=150)
    decision = evaluate_executable_candidate(candidate)
    result = run_candidate_paper_dry_run(bridge_input(candidate=candidate, decision=decision))

    assert result.accepted is True
    assert result.dry_run_executed is True
    assert result.instruction is not None
    assert result.instruction.side == ActionSide.BUY.value
    assert result.instruction.quantity == 100
    assert result.instruction.estimated_notional == 1000.0


def test_accepted_sell_candidate_creates_dry_run_sell_instruction_using_executable_quantity() -> None:
    candidate = candidate_input(side=CandidateSide.SELL, desired_quantity=200)
    decision = evaluate_executable_candidate(candidate)
    result = run_candidate_paper_dry_run(bridge_input(candidate=candidate, decision=decision))

    assert result.accepted is True
    assert result.instruction is not None
    assert result.instruction.side == ActionSide.SELL.value
    assert result.instruction.quantity == 200


def test_rejected_candidate_does_not_call_dry_run() -> None:
    candidate = candidate_input(is_suspended=True)
    decision = evaluate_executable_candidate(candidate)
    result = run_candidate_paper_dry_run(bridge_input(candidate=candidate, decision=decision))

    assert result.accepted is False
    assert result.dry_run_executed is False
    assert result.dry_run_result is None
    assert "candidate_decision_rejected" in issue_codes(result)


def test_zero_executable_quantity_does_not_call_dry_run() -> None:
    candidate = candidate_input()
    decision = replace(evaluate_executable_candidate(candidate), accepted=True, executable_quantity=0)
    result = run_candidate_paper_dry_run(bridge_input(candidate=candidate, decision=decision))

    assert result.dry_run_executed is False
    assert "executable_quantity_missing" in issue_codes(result)


def test_live_execution_claim_rejects() -> None:
    candidate = candidate_input()
    decision = replace(evaluate_executable_candidate(candidate), live_execution_claim=True)
    result = run_candidate_paper_dry_run(bridge_input(candidate=candidate, decision=decision))

    assert result.dry_run_executed is False
    assert "live_execution_claim_rejected" in issue_codes(result)


def test_broker_execution_reference_present_rejects() -> None:
    candidate = candidate_input()
    decision = replace(evaluate_executable_candidate(candidate), broker_execution_reference="broker-ref")
    result = run_candidate_paper_dry_run(bridge_input(candidate=candidate, decision=decision))

    assert result.dry_run_executed is False
    assert "broker_reference_rejected" in issue_codes(result)


def test_missing_evidence_refs_rejects() -> None:
    result = run_candidate_paper_dry_run(bridge_input(evidence_refs=()))

    assert result.dry_run_executed is False
    assert "evidence_refs_missing" in issue_codes(result)


def test_bridge_result_has_no_live_execution_claim_and_no_broker_reference() -> None:
    result = build_candidate_paper_bridge_report(bridge_input())

    assert result.live_execution_claim is False
    assert result.broker_execution_reference is None
    assert "no_live_execution" in result.decision_notes
    assert "paper_ledger_dry_run_only" in result.decision_notes
    assert "executable_candidate_bridge" in result.decision_notes


def test_bridge_uses_executable_quantity_not_desired_quantity() -> None:
    candidate = candidate_input(desired_quantity=150)
    decision = evaluate_executable_candidate(candidate)
    instruction = build_paper_ledger_instruction_from_candidate(
        bridge_input(candidate=candidate, decision=decision)
    )

    assert candidate.desired_quantity == 150
    assert decision.executable_quantity == 100
    assert instruction.quantity == 100


def test_bridge_reuses_paper_dry_run_for_insufficient_cash() -> None:
    cash_poor_account = account(
        cash=replace(account().cash, available_cash=500.0),
        risk_limits=replace(
            account().risk_limits,
            max_single_symbol_weight=1.0,
            max_industry_weight=1.0,
            max_total_position_weight=1.0,
        ),
    )
    result = run_candidate_paper_dry_run(bridge_input(account_profile=cash_poor_account))

    assert result.dry_run_executed is True
    assert result.accepted is False
    assert "buy_cash_insufficient" in dry_run_codes(result)


def test_bridge_reuses_paper_dry_run_for_insufficient_sellable_shares() -> None:
    candidate = candidate_input(side=CandidateSide.SELL, desired_quantity=800)
    decision = evaluate_executable_candidate(candidate)
    low_sellable_account = account(
        positions=(replace(account().positions[0], sellable_quantity=100),)
    )
    result = run_candidate_paper_dry_run(
        bridge_input(candidate=candidate, decision=decision, account_profile=low_sellable_account)
    )

    assert result.dry_run_executed is True
    assert result.accepted is False
    assert "sellable_quantity_insufficient" in dry_run_codes(result)


def test_no_provider_broker_imports_or_live_order_calls() -> None:
    package_root = Path("src/quantpilot_core/executable_candidate_paper_bridge")
    source_text = "\n".join(path.read_text() for path in sorted(package_root.glob("*.py"))).lower()

    forbidden_fragments = (
        "import akshare",
        "from akshare",
        "import baostock",
        "from baostock",
        "import tushare",
        "from tushare",
        "connect_broker(",
        "place_order(",
        "send_order(",
        "submit_order(",
        "execute_order(",
        "requests.",
        "urllib.request",
    )
    assert not any(fragment in source_text for fragment in forbidden_fragments)
