"""A-share candidate cost estimates."""

from __future__ import annotations

from quantpilot_core.executable_candidate.contracts import (
    CandidateAssetType,
    CandidateSide,
    ExecutableCandidateCostEstimate,
)


def estimate_a_share_cost(
    side: CandidateSide,
    notional: float,
    commission_rate: float,
    min_commission: float,
    stamp_duty_rate: float,
    slippage_bps: float,
    *,
    asset_type: CandidateAssetType = CandidateAssetType.STOCK,
) -> ExecutableCandidateCostEstimate:
    """Estimate explicit cost components for candidate evaluation only."""

    safe_notional = max(float(notional), 0.0)
    commission = 0.0 if safe_notional == 0 else max(safe_notional * commission_rate, min_commission)
    stamp_duty = 0.0
    if side == CandidateSide.SELL and asset_type == CandidateAssetType.STOCK:
        stamp_duty = safe_notional * stamp_duty_rate
    slippage = safe_notional * slippage_bps / 10_000
    return ExecutableCandidateCostEstimate(
        side=side.value,
        notional=round(safe_notional, 6),
        commission=round(commission, 6),
        stamp_duty=round(stamp_duty, 6),
        slippage=round(slippage, 6),
        total_cost=round(commission + stamp_duty + slippage, 6),
    )
