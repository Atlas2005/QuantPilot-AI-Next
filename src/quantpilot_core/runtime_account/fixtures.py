"""Deterministic offline fixtures for account-aware runtime tests."""

from __future__ import annotations

from quantpilot_core.runtime_account.contracts import (
    AccountCapabilities,
    BrokerFeeProfile,
    FeeProfileProvenance,
    RuntimeFeeModel,
)


def default_account_capabilities(**overrides: object) -> AccountCapabilities:
    """Build deterministic offline account capabilities."""

    return AccountCapabilities(**overrides)


def engineering_fallback_fee_profile(**overrides: object) -> BrokerFeeProfile:
    """Build the explicit deterministic fee fallback used in offline tests."""

    base = BrokerFeeProfile(
        profile_id="engineering-fallback-a-share-v1",
        provenance=FeeProfileProvenance.ENGINEERING_FALLBACK,
        default_buy=RuntimeFeeModel(
            commission_rate=0.0003,
            min_commission=5.0,
            stamp_duty_rate=0.0,
            transfer_fee_rate=0.0,
            exchange_fee_rate=0.0,
            slippage_bps=5.0,
        ),
        default_sell=RuntimeFeeModel(
            commission_rate=0.0003,
            min_commission=5.0,
            stamp_duty_rate=0.0005,
            transfer_fee_rate=0.0,
            exchange_fee_rate=0.0,
            slippage_bps=5.0,
        ),
        instrument_side_overrides={
            "etf": {
                "buy": RuntimeFeeModel(
                    commission_rate=0.0002,
                    min_commission=1.0,
                    stamp_duty_rate=0.0,
                    transfer_fee_rate=0.0,
                    exchange_fee_rate=0.0,
                    slippage_bps=3.0,
                ),
                "sell": RuntimeFeeModel(
                    commission_rate=0.0002,
                    min_commission=1.0,
                    stamp_duty_rate=0.0,
                    transfer_fee_rate=0.0,
                    exchange_fee_rate=0.0,
                    slippage_bps=3.0,
                ),
            }
        },
        notes=("Deterministic engineering fallback for offline tests; not broker truth.",),
    )
    if not overrides:
        return base
    return BrokerFeeProfile(**{**base.__dict__, **overrides})
