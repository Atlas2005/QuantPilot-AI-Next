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
    compute_industry_weights,
    compute_position_weights,
    normalize_sellable_quantities,
    run_account_profile_preflight,
)


def cash(**overrides):
    values = {
        "currency": "CNY",
        "available_cash": 40_000.0,
        "frozen_cash": 5_000.0,
        "total_equity": 100_000.0,
    }
    values.update(overrides)
    return AccountCashProfile(**values)


def position(**overrides):
    values = {
        "symbol": "600000",
        "quantity": 1000,
        "sellable_quantity": 800,
        "avg_cost": 10.0,
        "market_value": 20_000.0,
        "industry": "Banking",
    }
    values.update(overrides)
    return AccountPosition(**values)


def fee(**overrides):
    values = {
        "commission_rate": 0.0003,
        "min_commission": 5.0,
        "stamp_tax_rate": 0.0005,
        "transfer_fee_rate": 0.00001,
        "slippage_bps": 5.0,
    }
    values.update(overrides)
    return BrokerFeeProfile(**values)


def broker(**overrides):
    values = {
        "broker_name": "offline_fixture_broker",
        "market": "a_share",
        "capabilities": (
            BrokerCapability.A_SHARE_CASH_EQUITY.value,
            BrokerCapability.ETF.value,
        ),
        "permissions": (
            TradePermission.BUY.value,
            TradePermission.SELL.value,
            TradePermission.CANCEL.value,
        ),
    }
    values.update(overrides)
    return BrokerCapabilityProfile(**values)


def limits(**overrides):
    values = {
        "max_single_symbol_weight": 0.4,
        "max_industry_weight": 0.6,
        "max_total_position_weight": 0.8,
        "max_daily_turnover": 50_000.0,
        "max_order_value": 20_000.0,
    }
    values.update(overrides)
    return AccountRiskLimits(**values)


def profile(**overrides):
    values = {
        "account_id": "acct-paper-001",
        "status": AccountStatus.ACTIVE.value,
        "cash": cash(),
        "positions": (
            position(),
            position(
                symbol="000001",
                quantity=500,
                sellable_quantity=500,
                market_value=10_000.0,
                industry="Technology",
            ),
        ),
        "broker_fee": fee(),
        "broker_capability": broker(),
        "risk_limits": limits(),
        "evidence_refs": ("fixture:account-profile",),
    }
    values.update(overrides)
    return AccountProfile(**values)


def codes(result):
    return tuple(flag.code for flag in result.risk_flags)


def test_valid_active_a_share_account_passes() -> None:
    result = run_account_profile_preflight(profile())

    assert result.ok is True
    assert result.reason == "ok"
    assert result.risk_flags == ()
    assert result.normalized_sellable_by_symbol == {"600000": 800, "000001": 500}


def test_missing_evidence_refs_is_warning_not_blocker() -> None:
    result = run_account_profile_preflight(profile(evidence_refs=()))

    assert result.ok is True
    assert "evidence_refs_missing" in codes(result)


def test_negative_available_cash_is_rejected() -> None:
    result = run_account_profile_preflight(profile(cash=cash(available_cash=-1.0)))

    assert "available_cash_negative" in codes(result)


def test_total_equity_not_positive_is_rejected() -> None:
    result = run_account_profile_preflight(profile(cash=cash(total_equity=0.0)))

    assert "total_equity_not_positive" in codes(result)


def test_cash_sum_exceeding_equity_is_rejected_by_default() -> None:
    result = run_account_profile_preflight(
        profile(cash=cash(available_cash=80_000.0, frozen_cash=30_000.0))
    )

    assert "cash_equity_mismatch" in codes(result)


def test_cash_sum_exceeding_equity_can_be_allowed() -> None:
    result = run_account_profile_preflight(
        profile(cash=cash(available_cash=80_000.0, frozen_cash=30_000.0)),
        allow_cash_equity_mismatch=True,
    )

    assert "cash_equity_mismatch" not in codes(result)


def test_duplicate_position_symbol_is_rejected() -> None:
    result = run_account_profile_preflight(
        profile(positions=(position(), position(symbol="600000")))
    )

    assert "duplicate_position_symbol" in codes(result)


def test_sellable_quantity_exceeding_quantity_is_rejected() -> None:
    result = run_account_profile_preflight(
        profile(positions=(position(quantity=100, sellable_quantity=200),))
    )

    assert "position[0]:sellable_exceeds_quantity" in codes(result)


def test_invalid_commission_rate_is_rejected() -> None:
    result = run_account_profile_preflight(profile(broker_fee=fee(commission_rate=0.02)))

    assert "commission_rate_invalid" in codes(result)


def test_invalid_slippage_bps_is_rejected() -> None:
    result = run_account_profile_preflight(profile(broker_fee=fee(slippage_bps=101.0)))

    assert "slippage_bps_invalid" in codes(result)


def test_empty_capabilities_or_permissions_are_rejected() -> None:
    result = run_account_profile_preflight(
        profile(broker_capability=broker(capabilities=(), permissions=()))
    )

    assert "capabilities_empty" in codes(result)
    assert "permissions_empty" in codes(result)


def test_query_only_combined_with_buy_is_rejected_by_default() -> None:
    result = run_account_profile_preflight(
        profile(
            broker_capability=broker(
                permissions=(
                    TradePermission.QUERY_ONLY.value,
                    TradePermission.BUY.value,
                )
            )
        )
    )

    assert "query_only_combined_with_trade" in codes(result)


def test_query_only_combined_with_buy_can_be_allowed() -> None:
    result = run_account_profile_preflight(
        profile(
            broker_capability=broker(
                permissions=(
                    TradePermission.QUERY_ONLY.value,
                    TradePermission.BUY.value,
                )
            )
        ),
        allow_query_only_with_trade=True,
    )

    assert "query_only_combined_with_trade" not in codes(result)


def test_read_only_with_buy_is_rejected() -> None:
    result = run_account_profile_preflight(
        profile(
            status=AccountStatus.READ_ONLY.value,
            broker_capability=broker(permissions=(TradePermission.BUY.value,)),
        )
    )

    assert "read_only_trade_permission_active" in codes(result)


def test_kill_switched_with_sell_is_rejected() -> None:
    result = run_account_profile_preflight(
        profile(
            status=AccountStatus.KILL_SWITCHED.value,
            broker_capability=broker(permissions=(TradePermission.SELL.value,)),
        )
    )

    assert "kill_switched_trade_permission_active" in codes(result)


def test_missing_a_share_cash_equity_capability_is_rejected() -> None:
    result = run_account_profile_preflight(
        profile(broker_capability=broker(capabilities=(BrokerCapability.ETF.value,)))
    )

    assert "a_share_cash_equity_capability_missing" in codes(result)


def test_max_single_symbol_concentration_breach_is_sizing_warning() -> None:
    result = run_account_profile_preflight(
        profile(
            positions=(position(market_value=50_000.0),),
            risk_limits=limits(max_single_symbol_weight=0.4),
        )
    )

    assert "max_single_symbol_weight_breached" in codes(result)
    assert result.ok is True


def test_max_industry_concentration_breach_is_sizing_warning() -> None:
    result = run_account_profile_preflight(
        profile(
            positions=(
                position(symbol="600000", market_value=35_000.0, industry="Banking"),
                position(symbol="601398", market_value=35_000.0, industry="Banking"),
            ),
            risk_limits=limits(max_industry_weight=0.6),
        )
    )

    assert "max_industry_weight_breached" in codes(result)
    assert result.ok is True


def test_max_total_position_weight_breach_is_sizing_warning() -> None:
    result = run_account_profile_preflight(
        profile(
            positions=(
                position(symbol="600000", market_value=40_000.0),
                position(symbol="000001", market_value=45_000.0),
            ),
            risk_limits=limits(max_total_position_weight=0.8),
        )
    )

    assert "max_total_position_weight_breached" in codes(result)
    assert result.ok is True


def test_normalized_sellable_quantities_clamp_to_position_quantity() -> None:
    account = profile(
        positions=(position(symbol="600000", quantity=100, sellable_quantity=150),)
    )

    assert normalize_sellable_quantities(account) == {"600000": 100}


def test_position_and_industry_weights_are_deterministic() -> None:
    account = profile()

    assert compute_position_weights(account) == {"600000": 0.2, "000001": 0.1}
    assert compute_industry_weights(account) == {"Banking": 0.2, "Technology": 0.1}
