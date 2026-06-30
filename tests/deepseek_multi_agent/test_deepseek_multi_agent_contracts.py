import pytest

from quantpilot_core.deepseek_multi_agent import (
    AgentActionProposal,
    AgentAuditRecord,
    AgentContext,
    AgentFinding,
    AgentRequest,
    AgentRiskFlag,
    AgentRole,
    SupervisorDecision,
    SupervisorDecisionType,
    ToolPermission,
    default_permissions_for_role,
    run_deepseek_multi_agent_contract_preflight,
    validate_action_proposal,
    validate_agent_request,
    validate_supervisor_decision,
)


def context(sandbox_mode=True):
    return AgentContext(
        as_of_date="2026-06-30",
        market="A-share",
        asset_universe=("600000",),
        sandbox_mode=sandbox_mode,
        run_id="r16-test-run",
    )


def proposal(**overrides):
    values = {
        "symbol": "600000",
        "side": "BUY",
        "quantity": 100,
        "limit_price": 10.0,
        "confidence": 0.7,
        "reason": "typed sandbox proposal",
        "source_role": AgentRole.EXECUTION_AGENT,
        "required_gates": ("small_sample_gate", "paper_ledger"),
    }
    values.update(overrides)
    return AgentActionProposal(**values)


def test_all_default_roles_have_deterministic_permissions() -> None:
    first = {role: default_permissions_for_role(role) for role in AgentRole}
    second = {role: default_permissions_for_role(role) for role in AgentRole}

    assert first == second
    assert first[AgentRole.DATA_AGENT] == (
        ToolPermission.READ_MARKET_DATA,
        ToolPermission.WRITE_AUDIT_LOG,
    )
    assert ToolPermission.ORCHESTRATE_AGENTS in first[AgentRole.SUPERVISOR_AGENT]


def test_valid_context_request_finding_proposal_decision_contracts_can_be_created() -> None:
    risk = AgentRiskFlag("sample_size", "medium", "Small sample only")
    request = AgentRequest(
        role=AgentRole.RISK_AGENT,
        task="Review sandbox action",
        context=context(),
        tool_permissions=default_permissions_for_role(AgentRole.RISK_AGENT),
        input_refs=("sample_gate",),
    )
    finding = AgentFinding(
        role=AgentRole.RISK_AGENT,
        summary="Risk reviewed",
        confidence=0.8,
        evidence_refs=("paper_ledger",),
        risk_flags=(risk,),
    )
    action = proposal()
    decision = SupervisorDecision(
        decision=SupervisorDecisionType.ALLOW_TO_SANDBOX.value,
        reason="Sandbox only",
        proposals=(action,),
        risk_flags=(risk,),
        audit_refs=("audit-1",),
    )
    audit = AgentAuditRecord(
        run_id="r16-test-run",
        role=AgentRole.RISK_AGENT,
        action_type="review",
        summary="Reviewed",
        input_refs=("sample_gate",),
        output_refs=("decision",),
        blocked=False,
        block_reason=None,
    )

    assert request.role is AgentRole.RISK_AGENT
    assert finding.risk_flags == (risk,)
    assert decision.proposals == (action,)
    assert audit.blocked is False


def test_invalid_confidence_is_rejected() -> None:
    with pytest.raises(ValueError, match="confidence"):
        proposal(confidence=1.1)


def test_invalid_permission_for_role_is_rejected() -> None:
    request = AgentRequest(
        role=AgentRole.DATA_AGENT,
        task="Read account",
        context=context(),
        tool_permissions=(ToolPermission.READ_ACCOUNT_SNAPSHOT,),
        input_refs=(),
    )

    assert validate_agent_request(request) == (
        "permission_not_allowed:data_agent:read_account_snapshot",
    )


def test_buy_sell_without_gates_is_rejected() -> None:
    blocked = validate_action_proposal(proposal(required_gates=()), context())

    assert "required_gates_missing" in blocked
    assert "execution_agent_gate_bypass" in blocked


def test_live_trading_decision_is_rejected() -> None:
    decision = SupervisorDecision(
        decision="ALLOW_TO_LIVE_TRADING",
        reason="not allowed",
        proposals=(),
        risk_flags=(),
        audit_refs=(),
    )

    assert "live_trading_decision_rejected" in validate_supervisor_decision(
        decision,
        context(),
    )


def test_supervisor_can_only_allow_to_sandbox() -> None:
    decision = SupervisorDecision(
        decision=SupervisorDecisionType.ALLOW_TO_SANDBOX.value,
        reason="sandbox",
        proposals=(proposal(),),
        risk_flags=(),
        audit_refs=(),
    )

    assert "supervisor_can_only_allow_to_sandbox" in validate_supervisor_decision(
        decision,
        context(sandbox_mode=False),
    )


def test_execution_agent_cannot_bypass_gates() -> None:
    blocked = validate_action_proposal(
        proposal(required_gates=("BYPASS_GATES",)),
        context(),
    )

    assert "gate_bypass_requested" in blocked


def test_natural_language_only_output_is_not_valid_action_proposal() -> None:
    assert validate_action_proposal("Buy 600000 tomorrow", context()) == (
        "typed_action_proposal_required",
    )


def test_preflight_returns_ok_for_valid_sandbox_only_setup() -> None:
    request = AgentRequest(
        role=AgentRole.EXECUTION_AGENT,
        task="Propose sandbox action",
        context=context(),
        tool_permissions=default_permissions_for_role(AgentRole.EXECUTION_AGENT),
        input_refs=("gate",),
    )
    action = proposal()
    decision = SupervisorDecision(
        decision=SupervisorDecisionType.ALLOW_TO_SANDBOX.value,
        reason="Sandbox only",
        proposals=(action,),
        risk_flags=(),
        audit_refs=("audit",),
    )

    result = run_deepseek_multi_agent_contract_preflight(
        context(),
        requests=(request,),
        proposals=(action,),
        supervisor_decision=decision,
    )

    assert result.ok is True
    assert result.reason == "ok"
    assert AgentRole.EXECUTION_AGENT in result.roles_seen
    assert result.proposals_seen == 2
    assert result.blocked_actions == ()


def test_preflight_blocks_live_trading_setup() -> None:
    decision = SupervisorDecision(
        decision="ALLOW_TO_LIVE_TRADING",
        reason="not allowed",
        proposals=(proposal(),),
        risk_flags=(),
        audit_refs=(),
    )

    result = run_deepseek_multi_agent_contract_preflight(
        context(),
        supervisor_decision=decision,
    )

    assert result.ok is False
    assert "live_trading_decision_rejected" in result.blocked_actions


def test_preflight_blocks_gate_bypass_setup() -> None:
    result = run_deepseek_multi_agent_contract_preflight(
        context(),
        proposals=(proposal(required_gates=("BYPASS_GATES",)),),
    )

    assert result.ok is False
    assert "gate_bypass_requested" in result.blocked_actions
