"""Report builder for P37 alpha, sizing, and ETF universe tuning."""

from __future__ import annotations

from quantpilot_core.alpha_sizing_etf_universe_tuning_loop.contracts import (
    AlphaSignalQuality,
    AlphaSizingEtfUniverseReport,
    InstrumentType,
    SizingContext,
    TradableInstrument,
)
from quantpilot_core.alpha_sizing_etf_universe_tuning_loop.sizing import (
    recommend_sizing_candidates,
)
from quantpilot_core.alpha_sizing_etf_universe_tuning_loop.tuning import (
    tune_alpha_sizing_candidates,
)
from quantpilot_core.alpha_sizing_etf_universe_tuning_loop.universe import (
    select_tradable_universe,
)

def build_alpha_sizing_etf_universe_report(
    candidates: tuple[TradableInstrument, ...],
    alpha_quality_by_symbol: dict[str, AlphaSignalQuality],
    *,
    available_cash: float,
    sizing_context: SizingContext | None = None,
    safety_barrier_percent: float = 140.0,
) -> AlphaSizingEtfUniverseReport:
    """Build the P37 value-oriented ETF and sizing tuning report."""

    universe = select_tradable_universe(candidates)
    sizing_candidates = recommend_sizing_candidates(
        universe.accepted,
        available_cash=available_cash,
        sizing_context=sizing_context,
    )
    decisions = tune_alpha_sizing_candidates(sizing_candidates, alpha_quality_by_symbol)
    includes_both = universe.stock_candidate_count > 0 and universe.etf_candidate_count > 0
    etf_improves = any(
        decision.recommended_action == "prefer_etf_for_small_capital" for decision in decisions
    )
    sizing_reduces_zero_trade = any(candidate.zero_trade_risk_reduced for candidate in sizing_candidates)
    cost_ok = all(decision.cost_after_fill_score >= 0.50 for decision in decisions)
    barrier = min(round(safety_barrier_percent, 4), 140.0)
    return AlphaSizingEtfUniverseReport(
        includes_stocks_and_etfs=includes_both,
        stock_candidate_count=universe.stock_candidate_count,
        etf_candidate_count=universe.etf_candidate_count,
        etf_categories_present=universe.etf_categories_present,
        etfs_improve_small_capital_tradability=etf_improves,
        sizing_reduces_zero_trade_risk=sizing_reduces_zero_trade,
        cost_after_fill_acceptable=cost_ok,
        safety_barrier_percent=barrier,
        next_improvement_target=_next_target(universe, decisions, cost_ok),
        universe=universe,
        sizing_candidates=sizing_candidates,
        tuning_decisions=decisions,
        evidence_refs=_evidence_refs(universe.accepted),
    )


def _next_target(universe, decisions, cost_ok: bool) -> str:
    if universe.etf_candidate_count == 0:
        return "ETF universe"
    if any(decision.recommended_action == "improve_alpha" for decision in decisions):
        return "alpha quality"
    if any(decision.recommended_action == "increase_position_size" for decision in decisions):
        return "sizing"
    if not cost_ok:
        return "cost model"
    if not any(decision.accepted for decision in decisions):
        return "daily loop realism"
    return "daily loop realism"


def _evidence_refs(instruments: tuple[TradableInstrument, ...]) -> tuple[str, ...]:
    refs: list[str] = []
    for instrument in instruments:
        refs.extend(instrument.evidence_refs)
        if instrument.instrument_type == InstrumentType.ETF.value:
            refs.append("evidence://p37/etf-universe")
    return tuple(sorted(set(refs)))
