"""Account profile and broker config preflight validation."""

from __future__ import annotations

from quantpilot_core.account_profile_preflight.contracts import (
    AccountPosition,
    AccountProfile,
    AccountProfilePreflightResult,
    AccountProfileRiskFlag,
    AccountStatus,
    BrokerCapability,
    RiskSeverity,
    TradePermission,
)
from quantpilot_core.account_profile_preflight.limits import (
    compute_industry_weights,
    compute_position_weights,
    normalize_sellable_quantities,
)


def validate_account_profile(
    profile: AccountProfile,
    *,
    allow_cash_equity_mismatch: bool = False,
    allow_query_only_with_trade: bool = False,
) -> tuple[AccountProfileRiskFlag, ...]:
    """Validate account, broker, fee, permission, and concentration constraints."""

    flags: list[AccountProfileRiskFlag] = []
    flags.extend(_validate_identity(profile))
    flags.extend(_validate_cash(profile, allow_cash_equity_mismatch))
    flags.extend(_validate_positions(profile.positions))
    flags.extend(_validate_fees(profile))
    flags.extend(_validate_capabilities_and_permissions(
        profile,
        allow_query_only_with_trade,
    ))
    flags.extend(_validate_risk_limits(profile))
    if profile.cash.total_equity > 0:
        flags.extend(_validate_concentration(profile))
    return tuple(flags)


def run_account_profile_preflight(
    profile: AccountProfile,
    *,
    allow_cash_equity_mismatch: bool = False,
    allow_query_only_with_trade: bool = False,
) -> AccountProfilePreflightResult:
    """Run deterministic R20 preflight without broker or account API access."""

    flags = validate_account_profile(
        profile,
        allow_cash_equity_mismatch=allow_cash_equity_mismatch,
        allow_query_only_with_trade=allow_query_only_with_trade,
    )
    ok = not any(flag.severity == RiskSeverity.CRITICAL.value for flag in flags)
    return AccountProfilePreflightResult(
        ok=ok,
        reason="ok" if ok else ";".join(flag.code for flag in flags),
        account_id=profile.account_id,
        risk_flags=flags,
        normalized_sellable_by_symbol=normalize_sellable_quantities(profile),
        normalized_position_weight_by_symbol=compute_position_weights(profile),
        normalized_industry_weight=compute_industry_weights(profile),
    )


def _validate_identity(profile: AccountProfile) -> list[AccountProfileRiskFlag]:
    flags: list[AccountProfileRiskFlag] = []
    if not profile.account_id.strip():
        flags.append(_critical("account_id_missing", "Account ID must be non-empty."))
    if not _has_evidence(profile.evidence_refs):
        flags.append(_critical("evidence_refs_missing", "Account profile evidence is required."))
    if not profile.broker_capability.broker_name.strip():
        flags.append(_critical("broker_name_missing", "Broker name must be non-empty."))
    if not profile.broker_capability.market.strip():
        flags.append(_critical("market_missing", "Broker market must be non-empty."))
    if profile.status not in {status.value for status in AccountStatus}:
        flags.append(_critical("account_status_invalid", "Account status is unsupported."))
    return flags


def _validate_cash(
    profile: AccountProfile,
    allow_cash_equity_mismatch: bool,
) -> list[AccountProfileRiskFlag]:
    cash = profile.cash
    flags: list[AccountProfileRiskFlag] = []
    if not cash.currency.strip():
        flags.append(_critical("currency_missing", "Cash currency must be non-empty."))
    if cash.available_cash < 0:
        flags.append(_critical("available_cash_negative", "Available cash must be non-negative."))
    if cash.frozen_cash < 0:
        flags.append(_critical("frozen_cash_negative", "Frozen cash must be non-negative."))
    if cash.total_equity <= 0:
        flags.append(_critical("total_equity_not_positive", "Total equity must be positive."))
    if (
        cash.available_cash + cash.frozen_cash > cash.total_equity
        and not allow_cash_equity_mismatch
    ):
        flags.append(
            _critical(
                "cash_equity_mismatch",
                "Available cash plus frozen cash must not exceed total equity.",
            )
        )
    return flags


def _validate_positions(
    positions: tuple[AccountPosition, ...],
) -> list[AccountProfileRiskFlag]:
    flags: list[AccountProfileRiskFlag] = []
    seen_symbols: set[str] = set()
    for index, position in enumerate(positions):
        prefix = f"position[{index}]"
        symbol = position.symbol.strip()
        if not symbol:
            flags.append(_critical(f"{prefix}:symbol_missing", "Position symbol must be non-empty."))
        elif symbol in seen_symbols:
            flags.append(_critical("duplicate_position_symbol", f"Duplicate position: {symbol}."))
        else:
            seen_symbols.add(symbol)
        if position.quantity < 0:
            flags.append(_critical(f"{prefix}:quantity_negative", "Quantity must be non-negative."))
        if position.sellable_quantity < 0:
            flags.append(
                _critical(
                    f"{prefix}:sellable_quantity_negative",
                    "Sellable quantity must be non-negative.",
                )
            )
        if position.sellable_quantity > position.quantity:
            flags.append(
                _critical(
                    f"{prefix}:sellable_exceeds_quantity",
                    "Sellable quantity must not exceed quantity.",
                )
            )
        if position.avg_cost < 0:
            flags.append(_critical(f"{prefix}:avg_cost_negative", "Average cost must be non-negative."))
        if position.market_value < 0:
            flags.append(
                _critical(f"{prefix}:market_value_negative", "Market value must be non-negative.")
            )
    return flags


def _validate_fees(profile: AccountProfile) -> list[AccountProfileRiskFlag]:
    fee = profile.broker_fee
    flags: list[AccountProfileRiskFlag] = []
    if not 0 <= fee.commission_rate <= 0.01:
        flags.append(_critical("commission_rate_invalid", "Commission rate must be in [0, 0.01]."))
    if fee.min_commission < 0:
        flags.append(_critical("min_commission_negative", "Minimum commission must be non-negative."))
    if not 0 <= fee.stamp_tax_rate <= 0.01:
        flags.append(_critical("stamp_tax_rate_invalid", "Stamp tax rate must be in [0, 0.01]."))
    if not 0 <= fee.transfer_fee_rate <= 0.01:
        flags.append(_critical("transfer_fee_rate_invalid", "Transfer fee rate must be in [0, 0.01]."))
    if not 0 <= fee.slippage_bps <= 100:
        flags.append(_critical("slippage_bps_invalid", "Slippage bps must be in [0, 100]."))
    return flags


def _validate_capabilities_and_permissions(
    profile: AccountProfile,
    allow_query_only_with_trade: bool,
) -> list[AccountProfileRiskFlag]:
    broker = profile.broker_capability
    capabilities = set(broker.capabilities)
    permissions = set(broker.permissions)
    flags: list[AccountProfileRiskFlag] = []

    if not capabilities:
        flags.append(_critical("capabilities_empty", "Broker capabilities must not be empty."))
    if not permissions:
        flags.append(_critical("permissions_empty", "Broker permissions must not be empty."))

    has_trade_permission = bool({TradePermission.BUY.value, TradePermission.SELL.value} & permissions)
    if (
        TradePermission.QUERY_ONLY.value in permissions
        and has_trade_permission
        and not allow_query_only_with_trade
    ):
        flags.append(
            _critical(
                "query_only_combined_with_trade",
                "QUERY_ONLY cannot be combined with BUY or SELL by default.",
            )
        )

    if profile.status in {
        AccountStatus.READ_ONLY.value,
        AccountStatus.SUSPENDED.value,
        AccountStatus.KILL_SWITCHED.value,
    } and has_trade_permission:
        flags.append(
            _critical(
                f"{profile.status}_trade_permission_active",
                "Non-active account status must not have BUY or SELL permission.",
            )
        )

    if _is_a_share_market(broker.market) and BrokerCapability.A_SHARE_CASH_EQUITY.value not in capabilities:
        flags.append(
            _critical(
                "a_share_cash_equity_capability_missing",
                "A-share market profile requires A_SHARE_CASH_EQUITY capability.",
            )
        )
    return flags


def _validate_risk_limits(profile: AccountProfile) -> list[AccountProfileRiskFlag]:
    limits = profile.risk_limits
    flags: list[AccountProfileRiskFlag] = []
    if not 0 < limits.max_single_symbol_weight <= 1:
        flags.append(
            _critical(
                "max_single_symbol_weight_invalid",
                "Max single-symbol weight must be in (0, 1].",
            )
        )
    if not 0 < limits.max_industry_weight <= 1:
        flags.append(_critical("max_industry_weight_invalid", "Max industry weight must be in (0, 1]."))
    if not 0 < limits.max_total_position_weight <= 1:
        flags.append(
            _critical(
                "max_total_position_weight_invalid",
                "Max total position weight must be in (0, 1].",
            )
        )
    if limits.max_order_value is not None and limits.max_order_value <= 0:
        flags.append(_critical("max_order_value_invalid", "Max order value must be positive."))
    if limits.max_daily_turnover is not None and limits.max_daily_turnover <= 0:
        flags.append(_critical("max_daily_turnover_invalid", "Max daily turnover must be positive."))
    return flags


def _validate_concentration(profile: AccountProfile) -> list[AccountProfileRiskFlag]:
    limits = profile.risk_limits
    flags: list[AccountProfileRiskFlag] = []
    position_weights = compute_position_weights(profile)
    industry_weights = compute_industry_weights(profile)

    for symbol, weight in position_weights.items():
        if weight > limits.max_single_symbol_weight:
            flags.append(
                _critical(
                    "max_single_symbol_weight_breached",
                    f"{symbol} weight exceeds max_single_symbol_weight.",
                )
            )

    for industry, weight in industry_weights.items():
        if weight > limits.max_industry_weight:
            flags.append(
                _critical(
                    "max_industry_weight_breached",
                    f"{industry} weight exceeds max_industry_weight.",
                )
            )

    total_position_weight = sum(position.market_value for position in profile.positions) / profile.cash.total_equity
    if total_position_weight > limits.max_total_position_weight:
        flags.append(
            _critical(
                "max_total_position_weight_breached",
                "Total position weight exceeds max_total_position_weight.",
            )
        )
    return flags


def _is_a_share_market(market: str) -> bool:
    normalized = market.strip().lower().replace("-", "_")
    return normalized in {"a_share", "ashare", "cn_a_share", "china_a_share"}


def _has_evidence(evidence_refs: tuple[str, ...]) -> bool:
    return any(ref.strip() for ref in evidence_refs)


def _critical(code: str, message: str) -> AccountProfileRiskFlag:
    return AccountProfileRiskFlag(
        code=code,
        severity=RiskSeverity.CRITICAL.value,
        message=message,
    )
