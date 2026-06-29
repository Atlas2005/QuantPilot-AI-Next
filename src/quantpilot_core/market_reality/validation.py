"""Validation helpers for Market Reality Sandbox contracts.

The functions in this module validate contract completeness and safety
boundaries. They do not fetch market data, connect brokers, submit orders,
simulate a full backtest, or replace mature external engines.
"""

from __future__ import annotations

from quantpilot_core.market_reality.contracts import (
    MATURE_EXTERNAL_BOUNDARY_NAMES,
    AccountConstraint,
    CapitalConstraint,
    CostModel,
    FillSimulation,
    InstrumentTradingProfile,
    OrderDraft,
    SandboxRejectionReason,
    SandboxResult,
    SandboxScenario,
    SandboxValidationIssue,
    SlippageModel,
    ValidationSeverity,
)


FORBIDDEN_LIVE_ORDER_TERMS = (
    "live order",
    "broker instruction",
    "submit order",
    "send to broker",
    "place order",
    "execute live",
)


def validate_sandbox_scenario(scenario: SandboxScenario) -> list[SandboxValidationIssue]:
    """Validate a sandbox scenario contract without running a simulator."""

    issues: list[SandboxValidationIssue] = []
    issues.extend(validate_instrument_profile(scenario.instrument))
    issues.extend(validate_account_constraint(scenario.account_constraint))
    issues.extend(validate_capital_constraint(scenario.capital_constraint))
    issues.extend(validate_cost_model(scenario.cost_model))
    issues.extend(validate_slippage_model(scenario.slippage_model))

    constraint = scenario.execution_constraint
    if constraint.lot_size_required and constraint.lot_size <= 0:
        issues.append(
            _issue(
                "lot_size_missing",
                "Lot size must be explicit when lot-size validation is required.",
                SandboxRejectionReason.INVALID_LOT_SIZE,
            )
        )
    if constraint.t_plus_one_required is False and constraint.t_zero_eligible is False:
        issues.append(
            _issue(
                "t_plus_or_t_zero_missing",
                "T+1 or T+0 eligibility must be explicit.",
                SandboxRejectionReason.T_PLUS_ONE_VIOLATION,
            )
        )
    if constraint.price_limit_up is None or constraint.price_limit_down is None:
        issues.append(
            _issue(
                "execution_price_limits_missing",
                "Execution price-limit assumptions must be explicit.",
                SandboxRejectionReason.PRICE_LIMIT_VIOLATION,
            )
        )
    if not constraint.rejected_order_model_required:
        issues.append(
            _issue(
                "rejected_order_model_missing",
                "Rejected-order handling must be explicit.",
                SandboxRejectionReason.PRICE_LIMIT_VIOLATION,
            )
        )

    if not scenario.calendar.external_adapter_boundary.strip():
        issues.append(
            _issue(
                "calendar_adapter_boundary_missing",
                "Trading calendar must document its external adapter boundary.",
                SandboxRejectionReason.ADAPTER_BOUNDARY_MISSING,
            )
        )
    if scenario.data_latency is None or not scenario.data_latency.timestamp_audit_required:
        issues.append(
            _issue(
                "data_latency_assumption_missing",
                "Data latency and timestamp audit assumptions must be explicit.",
                SandboxRejectionReason.DATA_LATENCY_ASSUMPTION_MISSING,
            )
        )
    if scenario.provider_failure is None or not scenario.provider_failure.failure_handling_required:
        issues.append(
            _issue(
                "provider_failure_assumption_missing",
                "Provider failure handling assumptions must be explicit.",
                SandboxRejectionReason.PROVIDER_FAILURE_ASSUMPTION_MISSING,
            )
        )
    if not scenario.timestamp_audit_required:
        issues.append(
            _issue(
                "timestamp_audit_missing",
                "Timestamp audit assumptions must be required.",
                SandboxRejectionReason.DATA_LATENCY_ASSUMPTION_MISSING,
            )
        )
    if not scenario.no_live_execution:
        issues.append(
            _issue(
                "live_execution_not_blocked",
                "Sandbox scenarios must explicitly block live execution.",
                SandboxRejectionReason.LIVE_EXECUTION_FORBIDDEN,
            )
        )
    if not _has_external_adapter_boundary(scenario.external_adapter_boundaries):
        issues.append(
            _issue(
                "external_adapter_boundary_missing",
                "External adapter boundaries must name mature engines or libraries.",
                SandboxRejectionReason.ADAPTER_BOUNDARY_MISSING,
            )
        )
    return issues


def validate_order_draft(
    order: OrderDraft,
    scenario: SandboxScenario,
) -> list[SandboxValidationIssue]:
    """Validate an order draft as sandbox-only, not executable instructions."""

    issues = validate_sandbox_scenario(scenario)
    constraint = scenario.execution_constraint
    instrument = scenario.instrument
    account = scenario.account_constraint
    capital = scenario.capital_constraint
    order_notional = order.quantity * order.limit_price

    if constraint.lot_size_required and order.quantity % constraint.lot_size != 0:
        issues.append(
            _issue(
                "quantity_not_lot_size",
                "Order draft quantity does not satisfy the configured lot size.",
                SandboxRejectionReason.INVALID_LOT_SIZE,
            )
        )
    if order.quantity <= 0:
        issues.append(
            _issue(
                "quantity_non_positive",
                "Order draft quantity must be positive.",
                SandboxRejectionReason.INVALID_LOT_SIZE,
            )
        )
    if instrument.is_suspended:
        issues.append(
            _issue(
                "instrument_suspended",
                "Suspended instruments cannot be tradable in the sandbox.",
                SandboxRejectionReason.SUSPENDED_INSTRUMENT,
            )
        )
    if not account.cash_constraint_explicit or account.available_cash is None:
        issues.append(
            _issue(
                "cash_constraint_missing",
                "Cash availability must be explicit.",
                SandboxRejectionReason.CASH_CONSTRAINT_MISSING,
            )
        )
    elif order_notional > account.available_cash:
        issues.append(
            _issue(
                "insufficient_cash",
                "Order draft notional exceeds available cash.",
                SandboxRejectionReason.INSUFFICIENT_CASH,
            )
        )
    if order_notional > capital.max_order_notional:
        issues.append(
            _issue(
                "max_order_notional_exceeded",
                "Order draft notional exceeds the capital constraint max order notional.",
                SandboxRejectionReason.CAPITAL_CONSTRAINT_VIOLATION,
            )
        )
    if account.cash_constraint_explicit and account.available_cash is not None:
        post_order_cash = account.available_cash - order_notional
        if post_order_cash < capital.min_cash_reserve:
            issues.append(
                _issue(
                    "min_cash_reserve_breached",
                    "Post-order cash would fall below the required cash reserve.",
                    SandboxRejectionReason.CAPITAL_CONSTRAINT_VIOLATION,
                )
            )
        if (
            account.available_cash > 0
            and order_notional / account.available_cash > capital.max_cash_usage_ratio
        ):
            issues.append(
                _issue(
                    "max_cash_usage_ratio_breached",
                    "Order draft exceeds the capital constraint max cash usage ratio.",
                    SandboxRejectionReason.CAPITAL_CONSTRAINT_VIOLATION,
                )
            )
    if not account.can_trade_a_shares or instrument.market not in account.allowed_markets:
        issues.append(
            _issue(
                "account_permission_blocked",
                "Account permissions must explicitly allow the instrument market.",
                SandboxRejectionReason.ACCOUNT_PERMISSION_BLOCKED,
            )
        )
    if constraint.price_limit_up is None or constraint.price_limit_down is None:
        issues.append(
            _issue(
                "price_limit_missing",
                "Price limit up/down assumptions must be explicit.",
                SandboxRejectionReason.PRICE_LIMIT_VIOLATION,
            )
        )
    elif order.limit_price > constraint.price_limit_up or order.limit_price < constraint.price_limit_down:
        issues.append(
            _issue(
                "price_limit_violation",
                "Order draft price is outside explicit price limits.",
                SandboxRejectionReason.PRICE_LIMIT_VIOLATION,
            )
        )
    if order.is_live_order or order.broker_instruction_id is not None:
        issues.append(
            _issue(
                "live_order_forbidden",
                "Order drafts must not represent live orders or broker instructions.",
                SandboxRejectionReason.LIVE_EXECUTION_FORBIDDEN,
            )
        )
    if _contains_forbidden_live_terms(order.sandbox_instruction):
        issues.append(
            _issue(
                "forbidden_live_order_language",
                "Order draft language must not describe live execution or broker routing.",
                SandboxRejectionReason.LIVE_EXECUTION_FORBIDDEN,
            )
        )
    if not order.external_adapter_boundary.strip():
        issues.append(
            _issue(
                "order_adapter_boundary_missing",
                "Order draft must document external adapter boundaries.",
                SandboxRejectionReason.ADAPTER_BOUNDARY_MISSING,
            )
        )
    return issues


def validate_sandbox_result(result: SandboxResult) -> list[SandboxValidationIssue]:
    """Validate a sandbox result does not claim live execution."""

    issues: list[SandboxValidationIssue] = []
    if result.live_execution_claim or result.broker_execution_reference is not None:
        issues.append(
            _issue(
                "sandbox_result_live_execution_claim",
                "Sandbox results must not claim live execution or broker routing.",
                SandboxRejectionReason.LIVE_EXECUTION_FORBIDDEN,
            )
        )
    if not result.external_adapter_boundary.strip():
        issues.append(
            _issue(
                "result_adapter_boundary_missing",
                "Sandbox result must document external adapter boundaries.",
                SandboxRejectionReason.ADAPTER_BOUNDARY_MISSING,
            )
        )
    if result.fill_simulation.rejected and not result.rejection_reasons:
        issues.append(
            _issue(
                "rejection_reason_missing",
                "Rejected sandbox results must carry clear rejection reasons.",
                SandboxRejectionReason.PRICE_LIMIT_VIOLATION,
            )
        )
    issues.extend(validate_fill_simulation(result.fill_simulation))
    return issues


def validate_instrument_profile(
    instrument: InstrumentTradingProfile,
) -> list[SandboxValidationIssue]:
    issues: list[SandboxValidationIssue] = []
    if instrument.is_suspended:
        issues.append(
            _issue(
                "instrument_suspended",
                "Suspended instruments cannot be tradable.",
                SandboxRejectionReason.SUSPENDED_INSTRUMENT,
            )
        )
    if not instrument.st_flag_explicit or not instrument.delisting_risk_explicit:
        issues.append(
            _issue(
                "risk_flags_missing",
                "ST and delisting risk flags must be explicit.",
                SandboxRejectionReason.ST_OR_DELISTING_RISK,
            )
        )
    if instrument.price_limit_up is None or instrument.price_limit_down is None:
        issues.append(
            _issue(
                "instrument_price_limits_missing",
                "Instrument price limit assumptions must be explicit.",
                SandboxRejectionReason.PRICE_LIMIT_VIOLATION,
            )
        )
    if instrument.lot_size <= 0:
        issues.append(
            _issue(
                "instrument_lot_size_missing",
                "Instrument lot size must be explicit.",
                SandboxRejectionReason.INVALID_LOT_SIZE,
            )
        )
    if not instrument.external_adapter_boundary.strip():
        issues.append(
            _issue(
                "instrument_adapter_boundary_missing",
                "Instrument profile must document external adapter boundaries.",
                SandboxRejectionReason.ADAPTER_BOUNDARY_MISSING,
            )
        )
    return issues


def validate_account_constraint(account: AccountConstraint) -> list[SandboxValidationIssue]:
    if account.cash_constraint_explicit and account.available_cash is not None:
        return []
    return [
        _issue(
            "cash_constraint_missing",
            "Cash constraint must be explicit.",
            SandboxRejectionReason.CASH_CONSTRAINT_MISSING,
        )
    ]


def validate_capital_constraint(
    capital_constraint: CapitalConstraint,
) -> list[SandboxValidationIssue]:
    """Validate explicit capital-aware sandbox limits."""

    issues: list[SandboxValidationIssue] = []
    if capital_constraint.max_order_notional <= 0:
        issues.append(
            _issue(
                "max_order_notional_non_positive",
                "Max order notional must be positive.",
                SandboxRejectionReason.CAPITAL_CONSTRAINT_VIOLATION,
            )
        )
    if capital_constraint.max_position_notional <= 0:
        issues.append(
            _issue(
                "max_position_notional_non_positive",
                "Max position notional must be positive.",
                SandboxRejectionReason.CAPITAL_CONSTRAINT_VIOLATION,
            )
        )
    if not 0 < capital_constraint.max_cash_usage_ratio <= 1:
        issues.append(
            _issue(
                "max_cash_usage_ratio_invalid",
                "Max cash usage ratio must be greater than 0 and at most 1.",
                SandboxRejectionReason.CAPITAL_CONSTRAINT_VIOLATION,
            )
        )
    if capital_constraint.min_cash_reserve < 0:
        issues.append(
            _issue(
                "min_cash_reserve_negative",
                "Minimum cash reserve must be non-negative.",
                SandboxRejectionReason.CAPITAL_CONSTRAINT_VIOLATION,
            )
        )
    if not capital_constraint.capital_mode.strip():
        issues.append(
            _issue(
                "capital_mode_missing",
                "Capital mode must be explicit.",
                SandboxRejectionReason.CAPITAL_CONSTRAINT_VIOLATION,
            )
        )
    return issues


def validate_cost_model(cost_model: CostModel) -> list[SandboxValidationIssue]:
    issues: list[SandboxValidationIssue] = []
    for field, value in (
        ("commission_rate", cost_model.commission_rate),
        ("stamp_duty_rate", cost_model.stamp_duty_rate),
        ("transfer_fee_rate", cost_model.transfer_fee_rate),
    ):
        if value < 0:
            issues.append(
                _issue(
                    f"{field}_negative",
                    "Commission, stamp duty, and transfer fee fields must be present and non-negative.",
                    SandboxRejectionReason.COST_MODEL_MISSING,
                )
            )
    if not cost_model.external_adapter_boundary.strip():
        issues.append(
            _issue(
                "cost_adapter_boundary_missing",
                "Cost model must document external adapter boundaries.",
                SandboxRejectionReason.ADAPTER_BOUNDARY_MISSING,
            )
        )
    return issues


def validate_slippage_model(
    slippage_model: SlippageModel,
) -> list[SandboxValidationIssue]:
    issues: list[SandboxValidationIssue] = []
    if not slippage_model.model_name.strip() or slippage_model.slippage_bps < 0:
        issues.append(
            _issue(
                "slippage_model_missing",
                "Slippage model must be explicit and non-negative.",
                SandboxRejectionReason.SLIPPAGE_MODEL_MISSING,
            )
        )
    if not slippage_model.external_adapter_boundary.strip():
        issues.append(
            _issue(
                "slippage_adapter_boundary_missing",
                "Slippage model must document external adapter boundaries.",
                SandboxRejectionReason.ADAPTER_BOUNDARY_MISSING,
            )
        )
    return issues


def validate_fill_simulation(fill: FillSimulation) -> list[SandboxValidationIssue]:
    issues: list[SandboxValidationIssue] = []
    if fill.filled_quantity > fill.requested_quantity:
        issues.append(
            _issue(
                "fill_quantity_exceeds_request",
                "Filled quantity cannot exceed requested quantity.",
                SandboxRejectionReason.PRICE_LIMIT_VIOLATION,
            )
        )
    if fill.rejected and fill.rejection_reason is SandboxRejectionReason.NONE:
        issues.append(
            _issue(
                "fill_rejection_reason_missing",
                "Rejected fills must include a clear SandboxRejectionReason.",
                SandboxRejectionReason.PRICE_LIMIT_VIOLATION,
            )
        )
    if fill.partial_fill and fill.filled_quantity >= fill.requested_quantity:
        issues.append(
            _issue(
                "partial_fill_inconsistent",
                "Partial fills must fill less than requested quantity.",
                SandboxRejectionReason.PRICE_LIMIT_VIOLATION,
            )
        )
    return issues


def rejection_reasons(issues: list[SandboxValidationIssue]) -> tuple[SandboxRejectionReason, ...]:
    """Return unique rejection reasons from validation issues."""

    reasons: list[SandboxRejectionReason] = []
    for issue in issues:
        if issue.rejection_reason not in reasons:
            reasons.append(issue.rejection_reason)
    return tuple(reasons)


def _issue(
    code: str,
    message: str,
    reason: SandboxRejectionReason,
) -> SandboxValidationIssue:
    return SandboxValidationIssue(
        code=code,
        severity=ValidationSeverity.ERROR,
        message=message,
        rejection_reason=reason,
    )


def _has_external_adapter_boundary(boundaries: tuple[str, ...]) -> bool:
    if not boundaries or not all(boundary.strip() for boundary in boundaries):
        return False
    combined = " ".join(boundaries).lower()
    return any(name.lower() in combined for name in MATURE_EXTERNAL_BOUNDARY_NAMES)


def _contains_forbidden_live_terms(text: str) -> bool:
    normalized = text.lower()
    return any(term in normalized for term in FORBIDDEN_LIVE_ORDER_TERMS)
