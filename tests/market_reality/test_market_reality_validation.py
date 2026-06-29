from dataclasses import replace

from quantpilot_core.market_reality import (
    FillSimulation,
    SandboxRejectionReason,
    SandboxResult,
    rejection_reasons,
    validate_capital_constraint,
    validate_order_draft,
    validate_sandbox_result,
    validate_sandbox_scenario,
)
from tests.market_reality.test_market_reality_contracts import (
    valid_order_draft,
    valid_scenario,
)


def issue_codes(issues: object) -> set[str]:
    return {issue.code for issue in issues}


def test_valid_a_share_sandbox_scenario_passes_validation() -> None:
    scenario = valid_scenario()
    order = valid_order_draft()

    assert validate_sandbox_scenario(scenario) == []
    assert validate_order_draft(order, scenario) == []


def test_invalid_lot_size_is_rejected() -> None:
    issues = validate_order_draft(valid_order_draft(quantity=150), valid_scenario())

    assert "quantity_not_lot_size" in issue_codes(issues)
    assert SandboxRejectionReason.INVALID_LOT_SIZE in rejection_reasons(issues)


def test_suspended_instrument_is_rejected() -> None:
    scenario = valid_scenario(
        instrument=replace(valid_scenario().instrument, is_suspended=True)
    )
    issues = validate_order_draft(valid_order_draft(), scenario)

    assert "instrument_suspended" in issue_codes(issues)
    assert SandboxRejectionReason.SUSPENDED_INSTRUMENT in rejection_reasons(issues)


def test_missing_cash_constraint_is_rejected() -> None:
    scenario = valid_scenario(
        account_constraint=replace(
            valid_scenario().account_constraint,
            available_cash=None,
            cash_constraint_explicit=False,
        )
    )
    issues = validate_order_draft(valid_order_draft(), scenario)

    assert "cash_constraint_missing" in issue_codes(issues)
    assert SandboxRejectionReason.CASH_CONSTRAINT_MISSING in rejection_reasons(issues)


def test_invalid_capital_constraint_is_rejected() -> None:
    capital_constraint = replace(
        valid_scenario().capital_constraint,
        max_order_notional=0,
        max_position_notional=0,
        max_cash_usage_ratio=1.5,
        min_cash_reserve=-1,
        capital_mode="",
    )
    issues = validate_capital_constraint(capital_constraint)

    assert "max_order_notional_non_positive" in issue_codes(issues)
    assert "max_position_notional_non_positive" in issue_codes(issues)
    assert "max_cash_usage_ratio_invalid" in issue_codes(issues)
    assert "min_cash_reserve_negative" in issue_codes(issues)
    assert "capital_mode_missing" in issue_codes(issues)
    assert SandboxRejectionReason.CAPITAL_CONSTRAINT_VIOLATION in rejection_reasons(issues)


def test_order_exceeding_max_order_notional_is_rejected() -> None:
    scenario = valid_scenario(
        capital_constraint=replace(
            valid_scenario().capital_constraint,
            max_order_notional=500.0,
        )
    )
    issues = validate_order_draft(valid_order_draft(), scenario)

    assert "max_order_notional_exceeded" in issue_codes(issues)
    assert SandboxRejectionReason.CAPITAL_CONSTRAINT_VIOLATION in rejection_reasons(issues)


def test_order_breaching_min_cash_reserve_is_rejected() -> None:
    scenario = valid_scenario(
        account_constraint=replace(
            valid_scenario().account_constraint,
            available_cash=1050.0,
        ),
        capital_constraint=replace(
            valid_scenario().capital_constraint,
            min_cash_reserve=100.0,
        ),
    )
    issues = validate_order_draft(valid_order_draft(), scenario)

    assert "min_cash_reserve_breached" in issue_codes(issues)
    assert SandboxRejectionReason.CAPITAL_CONSTRAINT_VIOLATION in rejection_reasons(issues)


def test_order_breaching_max_cash_usage_ratio_is_rejected() -> None:
    scenario = valid_scenario(
        account_constraint=replace(
            valid_scenario().account_constraint,
            available_cash=1000.0,
        ),
        capital_constraint=replace(
            valid_scenario().capital_constraint,
            max_cash_usage_ratio=0.5,
        ),
    )
    issues = validate_order_draft(valid_order_draft(), scenario)

    assert "max_cash_usage_ratio_breached" in issue_codes(issues)
    assert SandboxRejectionReason.CAPITAL_CONSTRAINT_VIOLATION in rejection_reasons(issues)


def test_missing_provider_failure_or_data_latency_assumption_is_rejected() -> None:
    missing_latency = validate_sandbox_scenario(valid_scenario(data_latency=None))
    missing_provider = validate_sandbox_scenario(valid_scenario(provider_failure=None))

    assert "data_latency_assumption_missing" in issue_codes(missing_latency)
    assert "provider_failure_assumption_missing" in issue_codes(missing_provider)


def test_rejected_order_has_clear_sandbox_rejection_reason() -> None:
    issues = validate_order_draft(valid_order_draft(quantity=50), valid_scenario())
    reasons = rejection_reasons(issues)

    assert reasons
    assert SandboxRejectionReason.INVALID_LOT_SIZE in reasons


def test_live_execution_and_broker_path_language_is_prohibited() -> None:
    live_order_issues = validate_order_draft(
        valid_order_draft(
            is_live_order=True,
            broker_instruction_id="broker-123",
            sandbox_instruction="submit order and send to broker",
        ),
        valid_scenario(),
    )
    result_issues = validate_sandbox_result(
        SandboxResult(
            scenario_id="r2_valid_a_share_sandbox",
            order_draft=valid_order_draft(),
            fill_simulation=FillSimulation(
                requested_quantity=100,
                filled_quantity=0,
                average_fill_price=None,
                partial_fill=False,
                rejected=True,
                rejection_reason=SandboxRejectionReason.INVALID_LOT_SIZE,
                notes="Rejected in sandbox validation only.",
            ),
            accepted_for_sandbox=False,
            rejection_reasons=(SandboxRejectionReason.INVALID_LOT_SIZE,),
            live_execution_claim=True,
            broker_execution_reference="broker-path",
            audit_timestamp="2026-06-29T10:00:00Z",
            external_adapter_boundary="RQAlpha adapter boundary.",
        )
    )

    assert "live_order_forbidden" in issue_codes(live_order_issues)
    assert "forbidden_live_order_language" in issue_codes(live_order_issues)
    assert "sandbox_result_live_execution_claim" in issue_codes(result_issues)


def test_external_adapter_boundary_is_required() -> None:
    scenario = valid_scenario(external_adapter_boundaries=())
    order = valid_order_draft(external_adapter_boundary="")

    scenario_issues = validate_sandbox_scenario(scenario)
    order_issues = validate_order_draft(order, valid_scenario())

    assert "external_adapter_boundary_missing" in issue_codes(scenario_issues)
    assert "order_adapter_boundary_missing" in issue_codes(order_issues)


def test_market_reality_sandbox_does_not_reinvent_generic_engines() -> None:
    scenario = valid_scenario()
    combined = " ".join(scenario.external_adapter_boundaries).lower()

    assert "rqalpha" in combined
    assert "vectorbt" in combined
    assert "backtrader" in combined
    assert "exchange_calendars" in combined
    assert validate_sandbox_scenario(scenario) == []
