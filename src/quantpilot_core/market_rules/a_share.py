"""Configurable local A-share rule validation."""

from quantpilot_core.market_rules.types import (
    BoardType,
    MarketSide,
    OrderIntent,
    RiskFlag,
    RuleSeverity,
    RuleViolation,
)

FLOAT_TOLERANCE = 1e-8


def validate_order_intent(intent: OrderIntent, profile: dict) -> list[RuleViolation]:
    """Validate a local order intent against a configurable profile."""

    violations: list[RuleViolation] = []
    violations.extend(_validate_quantity(intent, profile))
    violations.extend(_validate_t_plus(intent, profile))
    violations.extend(_validate_price_sanity(intent, profile))
    violations.extend(_validate_price_limit(intent, profile))
    violations.extend(_validate_suspension(intent, profile))
    violations.extend(_validate_liquidity(intent, profile))
    violations.extend(_validate_cost_placeholders(profile))
    return violations


def _violation(
    code: str,
    severity: RuleSeverity,
    message: str,
    rule_name: str,
) -> RuleViolation:
    return RuleViolation(
        code=code,
        severity=severity,
        message=message,
        rule_name=rule_name,
    )


def _validate_quantity(intent: OrderIntent, profile: dict) -> list[RuleViolation]:
    violations: list[RuleViolation] = []
    lot_rules = profile.get("lot_rules", {})
    buy_lot_size = int(lot_rules.get("buy_lot_size", 100))
    buy_lot_increment = int(lot_rules.get("buy_lot_increment", buy_lot_size))

    if intent.quantity <= 0:
        violations.append(
            _violation(
                "quantity_non_positive",
                RuleSeverity.ERROR,
                "Quantity must be positive.",
                "lot_rules",
            )
        )
        return violations

    if intent.side is MarketSide.BUY:
        if intent.quantity < buy_lot_size:
            violations.append(
                _violation(
                    "buy_quantity_below_lot_size",
                    RuleSeverity.ERROR,
                    "Buy quantity is below configured lot size.",
                    "lot_rules",
                )
            )
        if intent.quantity % buy_lot_increment != 0:
            violations.append(
                _violation(
                    "buy_quantity_not_lot_increment",
                    RuleSeverity.ERROR,
                    "Buy quantity does not follow configured lot increment.",
                    "lot_rules",
                )
            )
    elif intent.side is MarketSide.SELL and lot_rules.get("odd_lot_sell_policy") == "deferred":
        violations.append(
            _violation(
                "odd_lot_sell_policy_deferred",
                RuleSeverity.WARNING,
                "Odd-lot sell behavior is deferred in the active profile.",
                "lot_rules",
            )
        )

    return violations


def _validate_t_plus(intent: OrderIntent, profile: dict) -> list[RuleViolation]:
    t_plus_rules = profile.get("t_plus_rules", {})
    if (
        t_plus_rules.get("enabled") is True
        and t_plus_rules.get("sell_same_day_acquired_forbidden") is True
        and intent.side is MarketSide.SELL
        and intent.acquired_today_quantity > 0
    ):
        return [
            _violation(
                "t_plus_same_day_sell_forbidden",
                RuleSeverity.ERROR,
                "Intent includes same-day acquired quantity that should not be sellable under configured T+1 rule.",
                "t_plus_rules",
            )
        ]
    return []


def _validate_price_sanity(intent: OrderIntent, profile: dict) -> list[RuleViolation]:
    violations: list[RuleViolation] = []
    price_limit_rules = profile.get("price_limit_rules", {})

    if intent.price <= 0:
        violations.append(
            _violation(
                "price_non_positive",
                RuleSeverity.ERROR,
                "Price must be positive.",
                "price_sanity",
            )
        )
    if price_limit_rules.get("enabled") is True and intent.previous_close <= 0:
        violations.append(
            _violation(
                "previous_close_non_positive",
                RuleSeverity.ERROR,
                "Previous close must be positive when price-limit check is enabled.",
                "price_sanity",
            )
        )
    return violations


def _validate_price_limit(intent: OrderIntent, profile: dict) -> list[RuleViolation]:
    price_limit_rules = profile.get("price_limit_rules", {})
    if price_limit_rules.get("enabled") is not True:
        return []

    special_cases = price_limit_rules.get("special_cases_deferred", [])
    violations = [
        _violation(
            "price_limit_special_cases_deferred",
            RuleSeverity.WARNING,
            "Special price-limit cases are deferred: " + ", ".join(special_cases),
            "price_limit_rules",
        )
    ]

    limit = _resolve_price_limit(intent, price_limit_rules)
    if limit is None:
        violations.append(
            _violation(
                "price_limit_unknown",
                RuleSeverity.WARNING,
                "No configured price-limit percentage for board/risk flag.",
                "price_limit_rules",
            )
        )
        return violations

    upper = intent.previous_close * (1 + limit)
    lower = intent.previous_close * (1 - limit)
    if intent.price > upper + FLOAT_TOLERANCE:
        violations.append(
            _violation(
                "price_above_limit",
                RuleSeverity.ERROR,
                "Price is above configured upper limit.",
                "price_limit_rules",
            )
        )
    if intent.price < lower - FLOAT_TOLERANCE:
        violations.append(
            _violation(
                "price_below_limit",
                RuleSeverity.ERROR,
                "Price is below configured lower limit.",
                "price_limit_rules",
            )
        )
    return violations


def _resolve_price_limit(intent: OrderIntent, price_limit_rules: dict) -> float | None:
    risk_limits = price_limit_rules.get("risk_flag_limits", {})
    risk_value = risk_limits.get(intent.risk_flag.value)
    if risk_value is not None:
        return float(risk_value)

    board_limits = price_limit_rules.get("board_limits", {})
    board_value = board_limits.get(intent.board.value)
    if board_value is not None:
        return float(board_value)
    return None


def _validate_suspension(intent: OrderIntent, profile: dict) -> list[RuleViolation]:
    suspension_rules = profile.get("suspension_rules", {})
    if suspension_rules.get("block_if_suspended") is True and intent.is_suspended:
        return [
            _violation(
                "symbol_suspended",
                RuleSeverity.ERROR,
                "Intent is blocked because symbol is marked suspended.",
                "suspension_rules",
            )
        ]
    return []


def _validate_liquidity(intent: OrderIntent, profile: dict) -> list[RuleViolation]:
    liquidity_rules = profile.get("liquidity_rules", {})
    if liquidity_rules.get("enabled") is not True or intent.available_volume is None:
        return []

    max_participation_rate = float(liquidity_rules.get("max_participation_rate", 1.0))
    max_quantity = intent.available_volume * max_participation_rate
    if intent.quantity > max_quantity + FLOAT_TOLERANCE:
        return [
            _violation(
                "liquidity_participation_exceeded",
                RuleSeverity.WARNING,
                "Quantity exceeds configured placeholder max participation rate.",
                "liquidity_rules",
            )
        ]
    return []


def _validate_cost_placeholders(profile: dict) -> list[RuleViolation]:
    violations: list[RuleViolation] = []
    fee_rules = profile.get("fee_rules", {})
    slippage_rules = profile.get("slippage_rules", {})

    if fee_rules.get("manual_review_required") is True:
        violations.append(
            _violation(
                "fee_rules_incomplete",
                RuleSeverity.INFO,
                "Fee and stamp-duty rules are placeholders and require manual review.",
                "fee_rules",
            )
        )
    if slippage_rules.get("manual_review_required") is True:
        violations.append(
            _violation(
                "slippage_rules_incomplete",
                RuleSeverity.INFO,
                "Slippage rules are placeholders and require manual review.",
                "slippage_rules",
            )
        )
    return violations

