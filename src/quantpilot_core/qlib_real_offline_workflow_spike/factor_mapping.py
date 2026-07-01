"""Map P36/P37/P40 concepts into Qlib-style factor candidates."""

from __future__ import annotations

from quantpilot_core.qlib_real_offline_workflow_spike.contracts import (
    QlibFactorCandidate,
)


REQUIRED_FACTOR_NAMES = (
    "momentum_proxy",
    "volatility_proxy",
    "liquidity_proxy",
    "cost_drag_proxy",
    "etf_category_proxy",
    "capital_fit_proxy",
    "ai_shadow_preference_proxy",
)


def build_qlib_factor_candidates() -> tuple[QlibFactorCandidate, ...]:
    """Create deterministic factor candidates for later Qlib workflow use."""

    return (
        _factor("momentum_proxy", "P40 alpha shadow preference", ("close",), "stock_and_etf", "positive"),
        _factor("volatility_proxy", "P36 drawdown and price path realism", ("high", "low", "close"), "stock_and_etf", "negative"),
        _factor("liquidity_proxy", "P39 provider sample volume quality", ("volume",), "stock_and_etf", "positive"),
        _factor("cost_drag_proxy", "P40 cost-aware replay adjustment", ("close", "volume"), "stock_and_etf", "negative"),
        _factor("etf_category_proxy", "P37 explicit ETF category rules", ("etf_category",), "etf_only", "category_dependent"),
        _factor("capital_fit_proxy", "P36/P38 small-capital suitability", ("close", "volume"), "stock_and_etf", "positive"),
        _factor("ai_shadow_preference_proxy", "P40 deterministic AI shadow decision", ("close", "volume", "etf_category"), "stock_and_etf", "positive"),
    )


def _factor(
    name: str,
    source: str,
    fields: tuple[str, ...],
    scope: str,
    direction: str,
) -> QlibFactorCandidate:
    return QlibFactorCandidate(
        name=name,
        source_concept=source,
        required_fields=fields,
        instrument_scope=scope,
        leakage_control_note="uses only same-day or prior local sample fields; no future label leakage",
        expected_direction=direction,
        known_limitations=("small_sample_proxy_only", "not_a_real_qlib_backtest_result"),
    )
