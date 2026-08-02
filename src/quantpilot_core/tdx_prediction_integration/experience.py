"""Thin orchestration for the after-close -> TDX -> review experience.

This module deliberately does not select stocks, call an LLM, collect quotes, or
place orders.  It composes artifacts emitted by those existing subsystems.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from quantpilot_core.daily_paper_loop.state import payload_digest
from quantpilot_core.order_intent import OrderIntent, OrderIntentProposal, OrderIntentSide
from quantpilot_core.paper_trading import PaperFillCostAssumptions, PaperFillSimulator
from quantpilot_core.real_data_provider import NormalizedIntradayBar
from quantpilot_core.tdx_prediction_integration.contracts import (
    CachedDeepSeekEvidence,
    CandidateEvidence,
    PredictionContext,
    PredictionState,
)


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
EXPERIENCE_PLAN_SCHEMA_VERSION = "tdx_next_day_experience_plan_v1"
EXPERIENCE_REVIEW_SCHEMA_VERSION = "tdx_experience_review_v1"
VISIBLE_OUTCOME_STATES = frozenset(
    {
        PredictionState.ENTRY.value,
        PredictionState.EXIT.value,
        PredictionState.INVALIDATED.value,
    }
)


def build_next_day_experience_plan_v1(
    production_report: Mapping[str, Any],
    *,
    active_shadow_report: Mapping[str, Any] | None = None,
    top_n: int = 10,
    generated_at: str | None = None,
) -> Mapping[str, Any]:
    """Slice the ordered production candidates and attach existing AI evidence."""

    if top_n <= 0:
        raise ValueError("top_n must be positive")
    daily = _daily_report(production_report)
    pipeline = _candidate_pipeline_report(production_report)
    raw_candidates = _ordered_candidates(daily, pipeline)
    decision_session = str(
        daily.get("decision_session")
        or dict(pipeline.get("sessions", {}) or {}).get("decision")
        or ""
    )
    target_session = str(
        daily.get("execution_session")
        or dict(pipeline.get("sessions", {}) or {}).get("execution")
        or ""
    )
    if not decision_session or not target_session:
        raise ValueError("production report is missing decision/execution sessions")
    generated = generated_at or datetime.now(SHANGHAI_TZ).isoformat()
    _parse_timestamp(generated)

    quant_firm = dict(daily.get("quant_firm_report", {}) or {})
    embedded_shadow = dict(daily.get("ai_shadow_report", {}) or {})
    active_shadow = dict(active_shadow_report or {})
    normalized_roles = _normalized_ai_roles(embedded_shadow, active_shadow)
    report_digest = payload_digest(production_report)
    candidate_ids = tuple(
        str(dict(candidate.get("metadata", {}) or {}).get("candidate_id", candidate.get("symbol", "")))
        for candidate in raw_candidates[:top_n]
    )
    plan_id = "tdx-plan-" + payload_digest(
        {
            "decision_session": decision_session,
            "target_session": target_session,
            "candidate_ids": candidate_ids,
            "production_report_digest": report_digest,
        }
    )[:24]

    candidates: list[Mapping[str, Any]] = []
    for position, candidate in enumerate(raw_candidates[:top_n], start=1):
        symbol = str(candidate.get("symbol", "")).strip()
        if not symbol:
            continue
        metadata = dict(candidate.get("metadata", {}) or {})
        rank = _optional_int(metadata.get("factor_rank"))
        if rank is None:
            rank = _pipeline_rank(pipeline, symbol) or position
        quant_score = _optional_float(
            metadata.get(
                "factor_composite_score_raw",
                metadata.get("factor_composite_score"),
            )
        )
        direction = str(candidate.get("direction", "neutral")).lower()
        research = _research_committee_for_symbol(quant_firm, symbol)
        information = _information_agent_for_symbol(quant_firm, symbol)
        stance, stance_provenance = _candidate_stance(
            direction=direction,
            quant_firm=quant_firm,
            research=research,
        )
        deepseek_stance, deepseek_stance_provenance = _deepseek_stance_for_symbol(
            normalized_roles, symbol
        )
        ai_conclusion = _ai_conclusion(
            quant_firm=quant_firm,
            embedded_shadow=embedded_shadow,
            active_shadow=active_shadow,
            roles=normalized_roles,
            research=research,
            information=information,
        )
        candidate_timestamp = str(
            candidate.get("timestamp")
            or metadata.get("pit_cutoff")
            or f"{decision_session}T15:00:00+08:00"
        )
        data_asof = str(
            metadata.get("pit_cutoff")
            or f"{decision_session}T15:00:00+08:00"
        )
        _parse_timestamp(candidate_timestamp)
        _parse_timestamp(data_asof)
        evidence_refs = tuple(
            dict.fromkeys(
                (
                    f"candidate:{metadata.get('candidate_id', symbol)}",
                    f"production_report:{report_digest}",
                    *(
                        f"deepseek_role:{role['role']}"
                        for role in normalized_roles
                    ),
                )
            )
        )
        candidates.append(
            {
                "symbol": symbol,
                "name": _candidate_name(candidate, metadata),
                "candidate_rank": rank,
                "quant_score": quant_score,
                "quant_score_semantics": (
                    "existing_factor_composite_score"
                    if quant_score is not None
                    else "not_emitted_by_existing_production_candidate"
                ),
                "candidate_confidence": _optional_float(candidate.get("confidence")),
                "direction": direction,
                "ai_conclusion": ai_conclusion,
                "stance": stance,
                "stance_provenance": stance_provenance,
                "deepseek_stance": deepseek_stance,
                "deepseek_stance_provenance": deepseek_stance_provenance,
                "key_reasons": _key_reasons(
                    metadata, quant_firm, research, information, normalized_roles
                ),
                "risks": _risks(
                    candidate, quant_firm, research, information, normalized_roles
                ),
                "invalidation": {
                    "price": None,
                    "conditions": (
                        "existing intraday lifecycle invalidation price is fixed when ENTRY starts",
                        "INVALIDATED is emitted on price breach or strong downside evidence",
                    ),
                },
                "next_day_observation_plan": (
                    "monitor completed intraday feature bars only",
                    "treat deterministic timing as EXPERIMENTAL SHADOW",
                    "observe ENTRY/HOLD/WEAKENING/EXIT/INVALIDATED transitions",
                    "use cached after-close AI context; never call DeepSeek per tick",
                    "manual decision and execution only; no broker order is placed",
                ),
                "provenance": {
                    "experience_plan_id": plan_id,
                    "candidate_id": metadata.get("candidate_id"),
                    "strategy_id": candidate.get("strategy_id", metadata.get("strategy_id")),
                    "production_candidate_id": daily.get("production_candidate_id"),
                    "production_candidate_version": daily.get("production_candidate_version"),
                    "production_report_digest": report_digest,
                    "evidence_refs": evidence_refs,
                    "source": "real_candidate_pipeline_existing_order",
                },
                "timestamps": {
                    "candidate_timestamp": candidate_timestamp,
                    "data_asof": data_asof,
                    "ai_evidence_asofs": tuple(
                        str(role["data_asof"])
                        for role in normalized_roles
                        if role.get("data_asof")
                    ),
                    "plan_generated_at": generated,
                    "target_session": target_session,
                },
            }
        )

    return {
        "schema_version": EXPERIENCE_PLAN_SCHEMA_VERSION,
        "plan_id": plan_id,
        "generated_at": generated,
        "decision_session": decision_session,
        "target_session": target_session,
        "data_asof": f"{decision_session}T15:00:00+08:00",
        "evidence_timestamps": tuple(
            dict.fromkeys(
                (
                    f"{decision_session}T15:00:00+08:00",
                    *(
                        str(role["data_asof"])
                        for role in normalized_roles
                        if role.get("data_asof")
                    ),
                    generated,
                )
            )
        ),
        "top_n_requested": int(top_n),
        "candidate_count": len(candidates),
        "symbols": [candidate["symbol"] for candidate in candidates],
        "candidates": candidates,
        "ai_analysis": {
            "quant_firm_final_recommendation": quant_firm.get("final_recommendation"),
            "research_committee_reused": any(
                _research_committee_for_symbol(quant_firm, candidate["symbol"])
                for candidate in candidates
            ),
            "information_agent_reused": any(
                _information_agent_for_symbol(quant_firm, candidate["symbol"])
                for candidate in candidates
            ),
            "embedded_ai_shadow": embedded_shadow,
            "active_shadow_mode": active_shadow.get("mode", "not_supplied"),
            "active_shadow_physical_model_calls": int(
                active_shadow.get("physical_model_calls", 0) or 0
            ),
            "active_shadow_cache_hits": int(active_shadow.get("cache_hits", 0) or 0),
            "roles": normalized_roles,
            "per_tick_deepseek_calls_permitted": False,
        },
        "source_components_reused": (
            "production_candidate manifest binding",
            "real_candidate_pipeline existing candidate order",
            "daily_paper_loop candidate normalization",
            "quant_firm deterministic committee and seven-desk contracts",
            "continuous_paper ActiveShadowRunner cached/event-triggered advisory",
        ),
        "limitations": (
            "plan preserves the existing production candidate universe and order; it does not select from full A-share",
            "a missing quant_score remains null rather than being invented",
            "AI conclusions are advisory context and do not mutate production execution",
            "immediate experience is evidence collection, not statistical validation",
        ),
        "broker_or_order_api_calls": False,
    }


def prediction_context_from_experience_plan(
    plan: Mapping[str, Any],
) -> PredictionContext:
    """Convert the immutable after-close plan into causal intraday priors."""

    if plan.get("schema_version") != EXPERIENCE_PLAN_SCHEMA_VERSION:
        raise ValueError("unsupported experience plan schema")
    plan_id = str(plan.get("plan_id", ""))
    candidates: dict[str, CandidateEvidence] = {}
    for raw in _mapping_sequence(plan.get("candidates", ())):
        symbol = str(raw.get("symbol", ""))
        timestamps = dict(raw.get("timestamps", {}) or {})
        data_asof = str(timestamps.get("data_asof") or plan.get("data_asof") or "")
        _parse_timestamp(data_asof)
        confidence = _bounded_probability(raw.get("candidate_confidence"), 0.5)
        quant_score = _optional_float(raw.get("quant_score"))
        provenance = dict(raw.get("provenance", {}) or {})
        candidates[symbol] = CandidateEvidence(
            symbol=symbol,
            decision_session=str(plan.get("decision_session", "")),
            data_asof=data_asof,
            confidence=confidence,
            factor_composite_score=(
                _bounded_probability(quant_score, confidence)
                if quant_score is not None
                else confidence
            ),
            evidence_refs=tuple(str(item) for item in provenance.get("evidence_refs", ())),
            source="tdx_next_day_experience_plan_v1",
            name=(str(raw.get("name")) if raw.get("name") not in (None, "") else None),
            candidate_rank=_optional_int(raw.get("candidate_rank")),
            quant_score=quant_score,
            deepseek_stance=str(raw.get("deepseek_stance", "neutral")),
            deepseek_stance_provenance=str(
                raw.get("deepseek_stance_provenance", "not_structured")
            ),
            after_close_ai_stance=str(raw.get("stance", "neutral")),
            stance_provenance=str(raw.get("stance_provenance", "not_available")),
            experience_plan_id=plan_id,
        )
    roles = _mapping_sequence(dict(plan.get("ai_analysis", {}) or {}).get("roles", ()))
    generated_at = str(plan.get("generated_at") or plan.get("data_asof") or "")
    _parse_timestamp(generated_at)
    deepseek = tuple(
        CachedDeepSeekEvidence(
            symbol=(str(role["symbol"]) if role.get("symbol") else None),
            data_asof=str(role.get("data_asof") or generated_at),
            role=str(role.get("role", "unknown")),
            confidence=_bounded_probability(role.get("confidence"), 0.0),
            summary=str(role.get("summary", "")),
            evidence_refs=tuple(str(item) for item in role.get("evidence_refs", ())),
            risk_flag_count=len(tuple(role.get("risk_notes", ()) or ())),
            source=str(role.get("source", "existing_after_close_ai_evidence")),
        )
        for role in roles
        if str(role.get("summary", "")).strip()
    )
    return PredictionContext(
        candidates=candidates,
        deepseek_evidence=deepseek,
        deepseek_live_calls_enabled=False,
    )


def experience_plan_symbols(plan: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            str(candidate.get("symbol", ""))
            for candidate in _mapping_sequence(plan.get("candidates", ()))
            if str(candidate.get("symbol", "")).strip()
        )
    )


def build_end_of_day_experience_review_v1(
    plan: Mapping[str, Any],
    signal_records: Sequence[Mapping[str, Any]],
    bars: Sequence[NormalizedIntradayBar],
    *,
    paper_state: Mapping[str, Any] | None = None,
    order_quantity: int = 100,
    cost_assumptions: PaperFillCostAssumptions | None = None,
) -> Mapping[str, Any]:
    """Resolve prior visible signals against strictly later completed bars."""

    if order_quantity <= 0 or order_quantity % 100:
        raise ValueError("order_quantity must be a positive 100-share lot")
    planned_symbols = set(experience_plan_symbols(plan))
    by_symbol: dict[str, list[NormalizedIntradayBar]] = defaultdict(list)
    for bar in bars:
        if bar.symbol in planned_symbols and bar.interval_minutes == 1 and not bar.partial:
            by_symbol[bar.symbol].append(bar)
    for rows in by_symbol.values():
        rows.sort(key=lambda item: (item.end, item.start))

    visible = _deduplicated_visible_signals(signal_records, planned_symbols)
    outcome_rows: list[Mapping[str, Any]] = []
    assumptions = cost_assumptions or PaperFillCostAssumptions()
    for signal in visible:
        if str(signal.get("state", "")) not in VISIBLE_OUTCOME_STATES:
            continue
        outcome_rows.append(
            _signal_outcome(
                signal,
                by_symbol.get(str(signal.get("symbol", "")), ()),
                order_quantity=order_quantity,
                cost_assumptions=assumptions,
            )
        )

    manual_associations = _manual_fill_associations(paper_state, visible)
    per_symbol: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for outcome in outcome_rows:
        per_symbol[str(outcome["symbol"])].append(outcome)
    last_state_by_symbol: dict[str, Mapping[str, Any]] = {}
    for signal in visible:
        last_state_by_symbol[str(signal["symbol"])] = signal
    open_signals = [
        {
            "signal_id": signal.get("signal_id"),
            "symbol": symbol,
            "state": signal.get("state"),
            "decision_timestamp": signal.get("decision_timestamp", signal.get("timestamp")),
        }
        for symbol, signal in sorted(last_state_by_symbol.items())
        if str(signal.get("state"))
        in {
            PredictionState.ENTRY.value,
            PredictionState.HOLD.value,
            PredictionState.WEAKENING.value,
        }
    ]
    hit_rates = {str(horizon): _hit_rate(outcome_rows, horizon) for horizon in (5, 15, 30)}
    deterministic = [
        outcome
        for outcome in outcome_rows
        if outcome.get("prediction_provider") == "deterministic_baseline"
    ]
    combined = [
        outcome
        for outcome in outcome_rows
        if _stance_agrees_with_timing(outcome)
    ]
    return {
        "schema_version": EXPERIENCE_REVIEW_SCHEMA_VERSION,
        "experience_plan_id": plan.get("plan_id"),
        "target_session": plan.get("target_session"),
        "candidates_monitored": sorted(planned_symbols),
        "candidate_count": len(planned_symbols),
        "signals_generated": len(visible),
        "outcome_signal_count": len(outcome_rows),
        "hit_rates": hit_rates,
        "per_symbol_outcomes": dict(sorted(per_symbol.items())),
        "outcomes": outcome_rows,
        "after_cost_simulated_profit": round(
            sum(
                float(outcome["simulated_after_cost_result"])
                for outcome in outcome_rows
                if outcome.get("simulated_after_cost_result") is not None
            ),
            6,
        ),
        "deterministic_timing_performance": _performance_summary(deterministic),
        "deepseek_stance_performance": _deepseek_stance_performance(outcome_rows),
        "combined_candidate_plus_timing_performance": _performance_summary(combined),
        "unresolved_signals": [
            outcome for outcome in outcome_rows if outcome["resolution_status"] != "resolved"
        ],
        "open_signals": open_signals,
        "manual_fill_associations": manual_associations,
        "no_lookahead_audit": {
            "passed": all(bool(outcome["strictly_future_bars_only"]) for outcome in outcome_rows),
            "rule": "decision uses the completed bar at/before cutoff; outcomes use only bars with end > decision timestamp",
        },
        "cost_semantics": (
            "one-way observational A-share paper cost from existing PaperFillSimulator; "
            "ENTRY uses buy costs and EXIT/INVALIDATED use sell costs. Same-day ENTRY "
            "round trips are not claimed executable because A-share T+1 still applies."
        ),
        "statistical_significance_claimed": False,
        "deepseek_live_calls": False,
        "broker_or_order_api_calls": False,
    }


def _signal_outcome(
    signal: Mapping[str, Any],
    bars: Sequence[NormalizedIntradayBar],
    *,
    order_quantity: int,
    cost_assumptions: PaperFillCostAssumptions,
) -> Mapping[str, Any]:
    symbol = str(signal.get("symbol", ""))
    timestamp_text = str(signal.get("decision_timestamp") or signal.get("timestamp") or "")
    decision_time = _parse_timestamp(timestamp_text)
    prior = [bar for bar in bars if bar.end <= decision_time]
    future = [bar for bar in bars if bar.end > decision_time]
    decision_price = _optional_float(signal.get("decision_price"))
    if decision_price is None and prior:
        decision_price = float(prior[-1].close)
    state = str(signal.get("state", ""))
    direction = 1.0 if state == PredictionState.ENTRY.value else -1.0
    returns: dict[int, float | None] = {}
    correctness: dict[int, bool | None] = {}
    prices: dict[int, float | None] = {}
    for horizon in (5, 15, 30):
        price = float(future[horizon - 1].close) if len(future) >= horizon else None
        prices[horizon] = price
        value = (
            price / decision_price - 1.0
            if price is not None and decision_price is not None and decision_price > 0
            else None
        )
        returns[horizon] = round(value, 8) if value is not None else None
        correctness[horizon] = (
            bool(direction * value > 0) if value is not None else None
        )
    excursion_window = future[:30]
    signed_highs: list[float] = []
    signed_lows: list[float] = []
    if decision_price is not None and decision_price > 0:
        for bar in excursion_window:
            if direction > 0:
                signed_highs.append(float(bar.high) / decision_price - 1.0)
                signed_lows.append(float(bar.low) / decision_price - 1.0)
            else:
                signed_highs.append(1.0 - float(bar.low) / decision_price)
                signed_lows.append(1.0 - float(bar.high) / decision_price)
    simulated_cost: float | None = None
    after_cost: float | None = None
    if decision_price is not None and prices[30] is not None:
        simulated_cost = _one_way_paper_cost(
            symbol,
            state,
            decision_price,
            order_quantity,
            cost_assumptions,
        )
        gross_directional = direction * (float(prices[30]) - decision_price) * order_quantity
        after_cost = round(gross_directional - simulated_cost, 6)
    stance = str(signal.get("deepseek_stance", "neutral"))
    provenance = {
        "signal_id": signal.get("signal_id"),
        "prediction_provider": signal.get("prediction_provider"),
        "prediction_provider_requested": signal.get("prediction_provider_requested"),
        "provider_qualified": signal.get("provider_qualified"),
        "provider_fallback": signal.get("provider_fallback"),
        "source_components": list(signal.get("source_components", ()) or ()),
        "evidence_refs": list(signal.get("evidence_refs", ()) or ()),
        "experience_plan_id": signal.get("experience_plan_id"),
        "shadow_status": signal.get("shadow_status", "EXPERIMENTAL SHADOW"),
    }
    return {
        "signal_id": signal.get("signal_id"),
        "symbol": symbol,
        "candidate_rank": _optional_int(signal.get("candidate_rank")),
        "after_close_quant_score": _optional_float(signal.get("after_close_quant_score")),
        "decision_timestamp": timestamp_text,
        "state": state,
        "state_label_zh": signal.get("state_label_zh"),
        "prediction_provider": signal.get("prediction_provider"),
        "signal_provenance": provenance,
        "deepseek_stance": stance,
        "deepseek_stance_provenance": signal.get("deepseek_stance_provenance"),
        "after_close_ai_stance": signal.get("after_close_ai_stance", "neutral"),
        "stance_provenance": signal.get("stance_provenance"),
        "decision_price": decision_price,
        "return_5m": returns[5],
        "return_15m": returns[15],
        "return_30m": returns[30],
        "correct_5m": correctness[5],
        "correct_15m": correctness[15],
        "correct_30m": correctness[30],
        "deepseek_correct_5m": _stance_correct(stance, returns[5]),
        "deepseek_correct_15m": _stance_correct(stance, returns[15]),
        "deepseek_correct_30m": _stance_correct(stance, returns[30]),
        "maximum_favourable_excursion": (
            round(max(signed_highs), 8) if signed_highs else None
        ),
        "maximum_adverse_excursion": (
            round(min(signed_lows), 8) if signed_lows else None
        ),
        "excursion_window_bars": len(excursion_window),
        "simulated_cost": simulated_cost,
        "simulated_after_cost_result": after_cost,
        "resolution_status": (
            "resolved"
            if all(value is not None for value in returns.values())
            else "unresolved"
        ),
        "strictly_future_bars_only": all(bar.end > decision_time for bar in future),
    }


def _one_way_paper_cost(
    symbol: str,
    state: str,
    decision_price: float,
    quantity: int,
    assumptions: PaperFillCostAssumptions,
) -> float:
    side = (
        OrderIntentSide.BUY
        if state == PredictionState.ENTRY.value
        else OrderIntentSide.SELL
    )
    intent = OrderIntent(
        symbol=symbol,
        side=side,
        target_shares=quantity,
        reason=f"tdx_experience_outcome:{state}",
        source_agent="tdx_experience_review_v1",
        confidence=1.0,
        strategy_id="tdx_prediction_engine_v1",
        run_label="tdx_experience_review_v1",
    )
    proposal = OrderIntentProposal(
        intents=(intent,),
        proposal_source="exec2",
        advisory_only=True,
        run_label="tdx_experience_review_v1",
    )
    result = PaperFillSimulator(assumptions).simulate(
        proposal,
        {symbol: decision_price},
    )
    if len(result.filled_trades) != 1:
        raise RuntimeError("existing paper cost simulator rejected experience outcome")
    return round(float(result.filled_trades[0].total_cost), 6)


def _daily_report(report: Mapping[str, Any]) -> Mapping[str, Any]:
    nested = report.get("daily_paper_loop")
    return nested if isinstance(nested, Mapping) else report


def _candidate_pipeline_report(report: Mapping[str, Any]) -> Mapping[str, Any]:
    nested = report.get("candidate_pipeline")
    return nested if isinstance(nested, Mapping) else {}


def _ordered_candidates(
    daily: Mapping[str, Any],
    pipeline: Mapping[str, Any],
) -> tuple[Mapping[str, Any], ...]:
    for key in ("quant_firm_input_candidate_report", "candidate_report"):
        report = daily.get(key)
        if isinstance(report, Mapping):
            rows = _mapping_sequence(report.get("candidates", ()))
            if rows:
                return rows
    nested = pipeline.get("candidates")
    if isinstance(nested, Mapping):
        return _mapping_sequence(nested.get("candidates", ()))
    return ()


def _candidate_name(candidate: Mapping[str, Any], metadata: Mapping[str, Any]) -> str | None:
    for value in (
        candidate.get("name"),
        metadata.get("name"),
        metadata.get("stock_name"),
        metadata.get("display_name"),
    ):
        if value not in (None, ""):
            return str(value)
    return None


def _pipeline_rank(pipeline: Mapping[str, Any], symbol: str) -> int | None:
    evidence = pipeline.get("evidence")
    if isinstance(evidence, Mapping) and isinstance(evidence.get(symbol), Mapping):
        return _optional_int(evidence[symbol].get("factor_rank"))
    return None


def _normalized_ai_roles(
    embedded_shadow: Mapping[str, Any],
    active_shadow: Mapping[str, Any],
) -> tuple[Mapping[str, Any], ...]:
    roles: list[Mapping[str, Any]] = []
    active_roles = active_shadow.get("roles")
    if isinstance(active_roles, Mapping):
        for role, payload in active_roles.items():
            if not isinstance(payload, Mapping) or payload.get("status") in {"abstain", "abstained"}:
                continue
            roles.append(
                {
                    "role": str(role),
                    "summary": str(payload.get("advisory_summary", payload.get("summary", ""))),
                    "confidence": _bounded_probability(payload.get("confidence"), 0.0),
                    "risk_notes": tuple(str(item) for item in payload.get("risk_notes", ())),
                    "evidence_refs": tuple(str(item) for item in payload.get("evidence_used", ())),
                    "source": "continuous_paper.ActiveShadowRunner",
                    "symbol": payload.get("symbol"),
                    "data_asof": payload.get("generated_at", payload.get("pit_timestamp")),
                    "stance": payload.get("stance", payload.get("direction")),
                }
            )
    for payload in embedded_shadow.get("specialist_desk_outputs", ()) or ():
        if not isinstance(payload, Mapping) or payload.get("status") != "accepted":
            continue
        roles.append(
            {
                "role": str(payload.get("role", "unknown")),
                "summary": str(payload.get("summary", "")),
                "confidence": _bounded_probability(payload.get("confidence"), 0.0),
                "risk_notes": (),
                "evidence_refs": (str(payload.get("evidence_digest", "")),),
                "source": "quant_firm.build_shadow_committee_report",
                "symbol": payload.get("symbol"),
                "data_asof": payload.get("pit_timestamp"),
                "stance": payload.get("stance", payload.get("direction")),
            }
        )
    return tuple(roles)


def _research_committee_for_symbol(
    quant_firm: Mapping[str, Any], symbol: str
) -> Mapping[str, Any]:
    for item in _walk_mappings(quant_firm):
        if (
            str(item.get("target", "")) == symbol
            and "committee_stance" in item
            and "dominant_thesis" in item
        ):
            return item
    return {}


def _information_agent_for_symbol(
    quant_firm: Mapping[str, Any], symbol: str
) -> Mapping[str, Any]:
    for item in _walk_mappings(quant_firm):
        if (
            str(item.get("target", "")) == symbol
            and "aggregate_bias" in item
            and "signals" in item
        ):
            return item
    return {}


def _walk_mappings(value: Any) -> Sequence[Mapping[str, Any]]:
    output: list[Mapping[str, Any]] = []
    if isinstance(value, Mapping):
        output.append(value)
        for nested in value.values():
            output.extend(_walk_mappings(nested))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for nested in value:
            output.extend(_walk_mappings(nested))
    return output


def _candidate_stance(
    *,
    direction: str,
    quant_firm: Mapping[str, Any],
    research: Mapping[str, Any],
) -> tuple[str, str]:
    research_stance = str(research.get("committee_stance", "")).lower()
    if research_stance in {"bull", "bullish"}:
        return "bullish", "existing_research_committee"
    if research_stance in {"bear", "bearish"}:
        return "bearish", "existing_research_committee"
    if research_stance in {"neutral", "mixed"}:
        return "neutral", "existing_research_committee"
    final = str(quant_firm.get("final_recommendation", ""))
    if final == "approve_offline_shadow_cycle":
        if direction == "long":
            return "bullish", "candidate_direction_plus_existing_quant_firm_approval"
        if direction == "short":
            return "bearish", "candidate_direction_plus_existing_quant_firm_approval"
    return "neutral", "existing_ai_evidence_not_symbol_directional"


def _deepseek_stance_for_symbol(
    roles: Sequence[Mapping[str, Any]], symbol: str
) -> tuple[str, str]:
    for role in roles:
        if role.get("symbol") not in (None, "", symbol):
            continue
        raw = str(role.get("stance", "")).strip().lower()
        if raw in {"bull", "bullish", "positive", "buy", "long"}:
            return "bullish", f"structured_deepseek_role:{role.get('role')}"
        if raw in {"bear", "bearish", "negative", "sell", "short"}:
            return "bearish", f"structured_deepseek_role:{role.get('role')}"
        if raw in {"neutral", "mixed", "hold", "review"}:
            return "neutral", f"structured_deepseek_role:{role.get('role')}"
    return "neutral", "no_structured_directional_deepseek_stance"


def _ai_conclusion(
    *,
    quant_firm: Mapping[str, Any],
    embedded_shadow: Mapping[str, Any],
    active_shadow: Mapping[str, Any],
    roles: Sequence[Mapping[str, Any]],
    research: Mapping[str, Any],
    information: Mapping[str, Any],
) -> Mapping[str, Any]:
    committee = dict(quant_firm.get("committee_decision", {}) or {})
    shadow_decision = dict(embedded_shadow.get("shadow_committee_decision", {}) or {})
    return {
        "quant_firm_final_recommendation": quant_firm.get("final_recommendation"),
        "quant_firm_committee_rationale": committee.get("rationale"),
        "research_committee_stance": research.get("committee_stance"),
        "research_committee_thesis": research.get("dominant_thesis"),
        "information_agent_bias": information.get("aggregate_bias"),
        "information_agent_score": information.get("aggregate_score"),
        "ai_shadow_decision": shadow_decision.get("decision"),
        "active_shadow_mode": active_shadow.get("mode", "not_supplied"),
        "deepseek_role_summaries": tuple(
            {"role": role.get("role"), "summary": role.get("summary")}
            for role in roles
        ),
        "advisory_only": True,
    }


def _key_reasons(
    metadata: Mapping[str, Any],
    quant_firm: Mapping[str, Any],
    research: Mapping[str, Any],
    information: Mapping[str, Any],
    roles: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    values: list[str] = []
    factor_evidence = metadata.get("factor_evidence")
    if isinstance(factor_evidence, Mapping):
        values.extend(f"{key}:{value}" for key, value in factor_evidence.items())
    committee = quant_firm.get("committee_decision")
    if isinstance(committee, Mapping) and committee.get("rationale"):
        values.append(str(committee["rationale"]))
    if research.get("dominant_thesis"):
        values.append(str(research["dominant_thesis"]))
    if information.get("aggregate_bias"):
        values.append(
            f"information_agent_bias:{information.get('aggregate_bias')}:"
            f"{information.get('aggregate_score')}"
        )
    for signal in information.get("signals", ()) or ():
        if isinstance(signal, Mapping):
            values.extend(str(item) for item in signal.get("evidence", ()) or ())
    values.extend(str(role.get("summary")) for role in roles if role.get("summary"))
    if not values:
        values.append("existing production candidate retained in supplied order")
    return tuple(dict.fromkeys(values))[:8]


def _risks(
    candidate: Mapping[str, Any],
    quant_firm: Mapping[str, Any],
    research: Mapping[str, Any],
    information: Mapping[str, Any],
    roles: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    values = [f"existing_candidate_risk_score:{candidate.get('risk_score')}"]
    if research.get("risk_thesis"):
        values.append(str(research["risk_thesis"]))
    values.extend(str(item) for item in information.get("conflicts", ()) or ())
    values.extend(str(item) for item in information.get("limitations", ()) or ())
    values.extend(str(item) for item in quant_firm.get("limitations", ()) or ())
    values.extend(
        str(note)
        for role in roles
        for note in (role.get("risk_notes", ()) or ())
    )
    return tuple(dict.fromkeys(values))[:8]


def _deduplicated_visible_signals(
    signals: Sequence[Mapping[str, Any]], planned_symbols: set[str]
) -> tuple[Mapping[str, Any], ...]:
    visible_states = {
        PredictionState.ENTRY.value,
        PredictionState.HOLD.value,
        PredictionState.WEAKENING.value,
        PredictionState.EXIT.value,
        PredictionState.INVALIDATED.value,
    }
    output: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    last_state: dict[str, str] = {}
    ordered = sorted(
        (signal for signal in signals if isinstance(signal, Mapping)),
        key=lambda item: (
            str(item.get("decision_timestamp", item.get("timestamp", ""))),
            str(item.get("symbol", "")),
        ),
    )
    for signal in ordered:
        symbol = str(signal.get("symbol", ""))
        state = str(signal.get("state", ""))
        signal_id = str(
            signal.get("signal_id")
            or f"{symbol}:{signal.get('decision_timestamp', signal.get('timestamp'))}:{state}"
        )
        if symbol not in planned_symbols or state not in visible_states or signal_id in seen:
            continue
        if last_state.get(symbol) == state:
            continue
        seen.add(signal_id)
        last_state[symbol] = state
        output.append(signal)
    return tuple(output)


def _manual_fill_associations(
    state: Mapping[str, Any] | None,
    signals: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    if not state:
        return []
    known = {str(signal.get("signal_id")): signal for signal in signals}
    execution = dict(state.get("execution_state", {}) or {})
    account = dict(execution.get("account", {}) or {})
    output = []
    for trade in account.get("trade_log", ()) or ():
        if not isinstance(trade, Mapping):
            continue
        metadata = dict(trade.get("metadata", {}) or {})
        signal_id = str(metadata.get("signal_id", ""))
        if signal_id not in known:
            continue
        output.append(
            {
                "signal_id": signal_id,
                "symbol": trade.get("symbol"),
                "side": trade.get("side"),
                "quantity": trade.get("quantity"),
                "actual_fill_price": trade.get("fill_price"),
                "trade_date": metadata.get("trade_date"),
                "paper_trade_total_cost": trade.get("total_cost"),
                "source": "daily_paper_loop.execution_state.account.trade_log",
            }
        )
    return output


def _performance_summary(outcomes: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    return {
        "signal_count": len(outcomes),
        "hit_rates": {str(horizon): _hit_rate(outcomes, horizon) for horizon in (5, 15, 30)},
        "after_cost_simulated_profit": round(
            sum(
                float(outcome["simulated_after_cost_result"])
                for outcome in outcomes
                if outcome.get("simulated_after_cost_result") is not None
            ),
            6,
        ),
        "status": "EXPERIMENTAL SHADOW",
    }


def _deepseek_stance_performance(
    outcomes: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    return {
        "eligible_signal_count": sum(
            str(outcome.get("deepseek_stance")) in {"bullish", "bearish"}
            for outcome in outcomes
        ),
        "hit_rates": {
            str(horizon): _hit_rate(outcomes, horizon, prefix="deepseek_correct_")
            for horizon in (5, 15, 30)
        },
        "neutral_stance_excluded": True,
    }


def _hit_rate(
    outcomes: Sequence[Mapping[str, Any]],
    horizon: int,
    *,
    prefix: str = "correct_",
) -> Mapping[str, Any]:
    field = f"{prefix}{horizon}m"
    values = [outcome.get(field) for outcome in outcomes if outcome.get(field) is not None]
    return {
        "evaluated": len(values),
        "hits": sum(bool(value) for value in values),
        "hit_rate": round(sum(bool(value) for value in values) / len(values), 6) if values else None,
    }


def _stance_agrees_with_timing(outcome: Mapping[str, Any]) -> bool:
    stance = str(
        outcome.get("after_close_ai_stance")
        or outcome.get("deepseek_stance", "neutral")
    )
    state = str(outcome.get("state", ""))
    return (stance == "bullish" and state == PredictionState.ENTRY.value) or (
        stance == "bearish"
        and state in {PredictionState.EXIT.value, PredictionState.INVALIDATED.value}
    )


def _stance_correct(stance: str, raw_return: float | None) -> bool | None:
    if raw_return is None or stance not in {"bullish", "bearish"}:
        return None
    return raw_return > 0 if stance == "bullish" else raw_return < 0


def _mapping_sequence(value: Any) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid experience timestamp: {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=SHANGHAI_TZ)
    return parsed.astimezone(SHANGHAI_TZ)


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bounded_probability(value: Any, default: float) -> float:
    parsed = _optional_float(value)
    if parsed is None:
        parsed = float(default)
    return max(0.0, min(1.0, parsed))
