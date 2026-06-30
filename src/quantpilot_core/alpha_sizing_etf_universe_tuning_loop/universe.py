"""Universe and rule-profile logic for P37."""

from __future__ import annotations

from quantpilot_core.alpha_sizing_etf_universe_tuning_loop.contracts import (
    EtfCategory,
    InstrumentTradingRuleProfile,
    InstrumentType,
    TradableInstrument,
    UniverseSelection,
)


T0_ELIGIBLE_ETF_CATEGORIES = {
    EtfCategory.BOND_ETF.value,
    EtfCategory.GOLD_ETF.value,
    EtfCategory.CROSS_BORDER_ETF.value,
    EtfCategory.MONEY_MARKET_ETF.value,
}


def build_instrument_rule_profile(
    instrument: TradableInstrument,
) -> InstrumentTradingRuleProfile:
    """Build deterministic stock or ETF trading rules without broker integration."""

    if instrument.instrument_type == InstrumentType.STOCK.value:
        return InstrumentTradingRuleProfile(
            symbol=instrument.symbol,
            instrument_type=InstrumentType.STOCK.value,
            etf_category=None,
            min_trade_unit=100,
            min_tick=0.01,
            settlement="T+1",
            commission_rate=0.0003,
            stamp_duty_rate=0.001,
            fee_model="stock_commission_plus_sell_stamp_duty",
            evidence_refs=("evidence://p37/rules/stock",),
        )
    if instrument.instrument_type != InstrumentType.ETF.value:
        raise ValueError("unknown_instrument_type")
    if not instrument.etf_category:
        raise ValueError("etf_category_missing")
    if instrument.etf_category not in {category.value for category in EtfCategory}:
        raise ValueError("etf_category_unknown")
    settlement = (
        "T+0"
        if instrument.t0_allowed_declared
        and instrument.etf_category in T0_ELIGIBLE_ETF_CATEGORIES
        else "T+1"
    )
    return InstrumentTradingRuleProfile(
        symbol=instrument.symbol,
        instrument_type=InstrumentType.ETF.value,
        etf_category=instrument.etf_category,
        min_trade_unit=100,
        min_tick=0.001,
        settlement=settlement,
        commission_rate=0.0001,
        stamp_duty_rate=0.0,
        fee_model="etf_commission_no_stock_stamp_duty",
        evidence_refs=("evidence://p37/rules/etf",),
    )


def select_tradable_universe(
    candidates: tuple[TradableInstrument, ...],
) -> UniverseSelection:
    """Accept valid stocks and ETFs while reporting them separately."""

    accepted: list[TradableInstrument] = []
    rejected: dict[str, tuple[str, ...]] = {}
    for candidate in candidates:
        issues = _candidate_issues(candidate)
        if issues:
            rejected[candidate.symbol] = issues
            continue
        accepted.append(candidate)

    stocks = tuple(item for item in accepted if item.instrument_type == InstrumentType.STOCK.value)
    etfs = tuple(item for item in accepted if item.instrument_type == InstrumentType.ETF.value)
    categories = tuple(sorted({item.etf_category for item in etfs if item.etf_category}))
    priority_symbols = tuple(
        item.symbol
        for item in sorted(etfs, key=lambda item: (-item.expected_alpha, item.symbol))
        if item.price > 0
    )
    return UniverseSelection(
        accepted=tuple(sorted(accepted, key=lambda item: (item.instrument_type, item.symbol))),
        rejected=dict(sorted(rejected.items())),
        stock_candidate_count=len(stocks),
        etf_candidate_count=len(etfs),
        etf_categories_present=categories,
        small_capital_priority_symbols=priority_symbols,
    )


def _candidate_issues(candidate: TradableInstrument) -> tuple[str, ...]:
    issues: list[str] = []
    if not candidate.symbol.strip():
        issues.append("symbol_missing")
    if candidate.price <= 0:
        issues.append("price_non_positive")
    if candidate.instrument_type not in {InstrumentType.STOCK.value, InstrumentType.ETF.value}:
        issues.append("unknown_instrument_type")
    if candidate.instrument_type == InstrumentType.ETF.value:
        if not candidate.etf_category:
            issues.append("etf_category_missing")
        elif candidate.etf_category not in {category.value for category in EtfCategory}:
            issues.append("etf_category_unknown")
    return tuple(issues)
