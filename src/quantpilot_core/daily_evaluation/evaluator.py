"""Deterministic multi-session evaluator over the real candidate daily paper loop."""

from __future__ import annotations

import math
import json
import os
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

from quantpilot_core.data_provider_normalization import canonicalize_a_share_symbol
from quantpilot_core.daily_evaluation.contracts import (
    DAILY_EVALUATION_SCHEMA_VERSION,
    DAILY_EVALUATION_VERSION,
    RealDailyEvaluationConfig,
    RealDailyEvaluationResult,
)
from quantpilot_core.daily_paper_loop.provider_market_input import attempt_payload, load_provider_market_rows, validate_pit_safe_inputs
from quantpilot_core.daily_paper_loop.report import report_digest, write_report_atomic
from quantpilot_core.daily_paper_loop.state import canonical_json, load_daily_state, payload_digest
from quantpilot_core.real_candidate_pipeline import RealCandidatePipelineConfig, run_real_candidate_daily_paper
from quantpilot_core.real_data_provider import (
    ProviderName,
    TradingCalendar,
    TusharePrimaryBaoStockCalendarProvider,
)


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


class EvaluationReportIntegrityError(ValueError):
    """Raised when an existing daily evaluation report cannot be certified."""


NO_TRADE_TAXONOMY: Mapping[str, str] = {
    "missing_d_market_evidence": "no_valid_market_evidence",
    "invalid_d_market_evidence_suspended": "suspension",
    "invalid_d_market_evidence_zero_volume": "no_valid_market_evidence",
    "invalid_d_market_evidence_nonfinite_volume": "no_valid_market_evidence",
    "invalid_d_market_evidence_close": "no_valid_market_evidence",
    "missing_factor_evidence": "factor_evidence_missing_hold",
    "insufficient_factor_evidence": "all_factor_rows_rejected",
    "invalid_factor_evidence": "all_factor_rows_rejected",
    "factor_rejected": "all_factor_rows_rejected",
    "holding_selected_no_duplicate_entry": "held_selected_no_duplicate_buy",
    "holding_selected_no_exit": "held_selected_no_duplicate_buy",
    "no_entry_or_exit_after_pit_filters": "no_selected_candidates",
    "quant_firm_non_actionable_decision": "quant_firm_rejection_or_non_approval",
    "less_than_one_valid_lot": "less_than_one_valid_board_lot",
    "insufficient_cash_below_one_lot": "insufficient_available_cash",
    "invalid_non_positive_sizing_price": "invalid_execution_price",
    "current_position_at_or_above_target": "held_selected_no_duplicate_buy",
    "desired_delta_below_one_board_lot_after_position_cap": "less_than_one_valid_board_lot",
    "insufficient_cash_for_one_board_lot_after_reserve": "insufficient_available_cash",
    "max_position_cap_reduction": "sizing_reduction",
    "board_lot_reduction": "sizing_reduction",
    "cash_reduction": "sizing_reduction",
    "missing_decision_market_data": "no_valid_market_evidence",
    "price_missing_or_non_positive": "invalid_execution_price",
    "symbol_suspended": "suspension",
    "one_price_limit_state_no_realistic_fill": "price_limit_restriction",
    "volume_unavailable_or_zero": "no_fill",
    "quantity_must_be_positive": "less_than_one_valid_board_lot",
    "buy_quantity_below_lot_size": "less_than_one_valid_board_lot",
    "buy_quantity_normalized_to_lot_increment": "less_than_one_valid_board_lot",
    "t_plus_one_sellable_quantity_insufficient": "t_plus_one_sell_restriction",
    "insufficient_position": "insufficient_position",
    "insufficient_cash_after_fee_reserve": "insufficient_available_cash",
    "partial_fill_volume_participation_limit": "execution_shortfall",
    "not_selected_lower_rank": "no_selected_candidates",
    "liquidity_filter_failed": "all_factor_rows_rejected",
    "drawdown_guard_failed": "all_factor_rows_rejected",
    "zero_target_shares": "zero_allocation",
    "target_weight_too_small_for_one_lot": "less_than_one_valid_board_lot",
    "duplicate_order_id": "idempotent_replay",
    "idempotent_replay": "idempotent_replay",
}

MARKET_EVIDENCE_MODES = {"live_market_data", "offline_input_bars", "synthetic_engineering_fixture"}
FUNNEL_COUNT_FIELDS = (
    "declared_universe_count",
    "resolved_universe_count",
    "valid_market_evidence_symbol_count",
    "factor_accepted_count",
    "factor_rejected_count",
    "factor_selected_long_count",
    "rank_dropout_exit_count",
    "selected_candidate_count",
    "selected_long_count",
    "hold_candidate_count",
    "selected_hold_count",
    "selected_exit_count",
    "long_candidate_count",
    "exit_candidate_count",
    "actionable_candidate_count",
    "hold_event_count",
    "quant_firm_approved_entry_count",
    "quant_firm_blocked_entry_count",
    "quant_firm_approved_exit_count",
    "quant_firm_blocked_exit_count",
    "quant_firm_approved_count",
    "quant_firm_rejected_or_blocked_count",
    "positive_allocation_count",
    "zero_allocation_count",
    "buy_order_intent_count",
    "sell_order_intent_count",
    "unique_order_intent_count",
    "order_intent_count",
    "skipped_order_count",
    "unique_fully_filled_order_count",
    "unique_partially_filled_order_count",
    "unique_order_with_any_fill_count",
    "unique_filled_order_count",
    "fill_count",
    "partial_fill_count",
    "no_fill_order_count",
    "no_fill_count",
    "rejected_order_count",
    "rejection_count",
)
QUANT_FIRM_EVIDENCE_FIELDS = (
    "quant_firm_approved_entry_count",
    "quant_firm_blocked_entry_count",
    "quant_firm_approved_exit_count",
    "quant_firm_blocked_exit_count",
    "quant_firm_approved_count",
    "quant_firm_rejected_or_blocked_count",
)


def run_real_daily_evaluation(
    config: RealDailyEvaluationConfig,
    *,
    calendar_provider: Any | None = None,
    bar_provider: Any | None = None,
) -> RealDailyEvaluationResult:
    """Run a bounded consecutive decision-session evaluation through PR #112."""

    mode = _effective_market_mode(config)
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    start, end = _validate_config(config)
    request_digest = evaluation_request_digest(config)
    calendar, bounded_rows, acquisition = _bounded_market_evidence(config, start, end, calendar_provider=calendar_provider, bar_provider=bar_provider)
    decision_sessions = calendar.sessions_between(start, end)
    if not decision_sessions:
        raise ValueError("evaluation range contains no trading sessions")

    manifest = _load_or_create_manifest(output_dir, request_digest, config)
    capital_runs = []
    for capital in _capital_values(config.capital_values):
        capital_runs.append(
            _run_capital(
                config=config,
                request_digest=request_digest,
                output_dir=output_dir,
                capital=capital,
                calendar=calendar,
                decision_sessions=decision_sessions,
                bounded_rows=bounded_rows,
                manifest=manifest,
                market_evidence_mode=mode,
            )
        )

    report = {
        "schema_version": DAILY_EVALUATION_SCHEMA_VERSION,
        "evaluator_version": DAILY_EVALUATION_VERSION,
        "evaluation_request_digest": request_digest,
        "run_config": _run_config_payload(config),
        "session_range": {"start_decision_session": start.isoformat(), "end_decision_session": end.isoformat()},
        "trading_sessions": tuple(session.isoformat() for session in decision_sessions),
        "acquisition_provenance": acquisition,
        "capital_runs": tuple(capital_runs),
        "capital_comparison": _capital_comparison(capital_runs),
        "metric_definitions": _metric_definitions(),
        "data_quality": _data_quality(capital_runs, acquisition),
        "limitations": (
            "evaluation_orchestrates_existing_real_candidate_daily_paper_reports",
            "expected_return_is_fixed_unscaled_sizing_prior_not_calibrated_return",
            "no_deepseek_live_call",
            "no_broker_live_execution",
        ),
    }
    report_path = write_report_atomic(report, output_dir / config.report_filename)
    assert report_path is not None
    return RealDailyEvaluationResult(
        status="completed",
        report=report,
        report_path=report_path,
        evaluation_request_digest=request_digest,
    )


def evaluation_request_digest(config: RealDailyEvaluationConfig) -> str:
    """Stable digest for equivalent evaluation inputs."""

    start, end = _validate_config(config)
    mode = _effective_market_mode(config)
    return payload_digest(
        {
            "evaluator_version": DAILY_EVALUATION_VERSION,
            "strategy_id": config.strategy_id.strip(),
            "date_range": {"start": start.isoformat(), "end": end.isoformat()},
            "symbols": _symbols(config.symbols),
            "offline_calendar_sessions": _calendar_session_payload(config.offline_calendar_sessions),
            "capital_values": _capital_values(config.capital_values),
            "live_market_data": bool(config.live_market_data),
            "market_evidence_mode": mode,
            "provider_mode": mode,
            "max_execution_symbols": int(config.max_execution_symbols),
            "target_symbol_count": int(config.target_symbol_count),
            "input_bars": _canonical_bars(config.input_bars),
            "information_signals": _canonical_information_signals(config.information_signals),
            "information_provenance": _json_ready(config.information_provenance),
            "advisory_provenance": _json_ready(config.advisory_provenance),
            "quant_firm_context": _json_ready(config.quant_firm_context),
        }
    )


def _run_capital(
    *,
    config: RealDailyEvaluationConfig,
    request_digest: str,
    output_dir: Path,
    capital: float,
    calendar: TradingCalendar,
    decision_sessions: tuple[date, ...],
    bounded_rows: tuple[Mapping[str, Any], ...],
    manifest: Mapping[str, Any],
    market_evidence_mode: str,
) -> Mapping[str, Any]:
    capital_dir = output_dir / f"capital_{_capital_label(capital)}"
    reports_dir = capital_dir / "daily_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    state_path = capital_dir / "state.json"
    manifest_capitals = dict(manifest.get("capital_starting_state_hashes", {}) or {})
    starting_hash = manifest_capitals.get(_capital_label(capital)) or load_daily_state(state_path, initial_capital=capital).state_hash
    daily_summaries = []
    daily_reports = []
    for decision in decision_sessions:
        execution = calendar.next_session(decision)
        report_path = reports_dir / f"{decision.isoformat()}.json"
        existing_combined, existing_error = _read_json_for_recovery(report_path)
        available_signals = _signals_available_for_decision(config.information_signals, decision)
        result = run_real_candidate_daily_paper(
            RealCandidatePipelineConfig(
                decision_session=decision.isoformat(),
                symbols=_symbols(config.symbols),
                initial_capital=capital,
                state_path=state_path,
                report_path=None,
                strategy_id=config.strategy_id,
                max_execution_symbols=config.max_execution_symbols,
                target_symbol_count=config.target_symbol_count,
                live_market_data=False,
                input_bars=_rows_through_execution(bounded_rows, execution),
                information_signals=available_signals,
                information_provenance={
                    **dict(config.information_provenance),
                    "evaluation_request_digest": request_digest,
                    "bounded_acquisition_mode": market_evidence_mode,
                    "market_evidence_mode": market_evidence_mode,
                    "available_information_signal_ids": _signal_ids(available_signals),
                    "available_information_signal_count": len(available_signals),
                },
                advisory_provenance={**dict(config.advisory_provenance), "deepseek_live_call": False},
                quant_firm_context=_context_for_decision(config.quant_firm_context, decision),
            )
        )
        combined = _verified_daily_combined_report(
            existing_combined=existing_combined,
            existing_error=existing_error,
            result_combined=result.combined_report,
            report_path=report_path,
            replay_status=result.daily_paper_loop_result.status.value if result.daily_paper_loop_result else "not_run",
        )
        daily = dict(combined.get("daily_paper_loop", {}) or {})
        pipeline = dict(combined.get("candidate_pipeline", {}) or {})
        summary = _daily_summary(pipeline, daily, report_path, output_dir, combined)
        summary = {**summary, "replay_execution_status": result.daily_paper_loop_result.status.value if result.daily_paper_loop_result else "not_run"}
        daily_summaries.append(summary)
        daily_reports.append((pipeline, daily, summary))
    ending_hash = load_daily_state(state_path, initial_capital=capital).state_hash
    funnel = _aggregate_funnel(tuple(summary["funnel"] for summary in daily_summaries))
    no_trade = _aggregate_no_trade(tuple(summary["no_trade_attribution"] for summary in daily_summaries))
    execution_shortfall = _aggregate_execution_shortfall(tuple(summary["execution_shortfall"] for summary in daily_summaries))
    sizing = _aggregate_sizing(tuple(summary["sizing_compression"] for summary in daily_summaries))
    performance = _performance(capital, tuple(daily for _, daily, _ in daily_reports))
    return {
        "initial_capital": capital,
        "state": {
            "state_path": _relative(output_dir, state_path),
            "reports_dir": _relative(output_dir, reports_dir),
            "starting_state_hash": starting_hash,
            "ending_state_hash": ending_hash,
            "evaluation_manifest_ref": _relative(output_dir, output_dir / "evaluation_manifest.json"),
        },
        "daily_summaries": tuple(daily_summaries),
        "funnel": funnel,
        "no_trade_attribution": no_trade,
        "execution_shortfall": execution_shortfall,
        "sizing_compression": sizing,
        "performance": performance,
        "reconciliation_summary": _reconciliation_summary(tuple(daily for _, daily, _ in daily_reports)),
        "provider_data_gaps": _provider_data_gaps(tuple(daily for _, daily, _ in daily_reports)),
    }


def _daily_summary(
    pipeline: Mapping[str, Any],
    daily: Mapping[str, Any],
    report_path: Path,
    output_dir: Path,
    combined: Mapping[str, Any],
) -> Mapping[str, Any]:
    funnel = _daily_funnel(pipeline, daily)
    no_trade = _daily_no_trade(pipeline, daily)
    execution_shortfall = _daily_execution_shortfall(daily)
    sizing = _daily_sizing_compression(pipeline, daily)
    return {
        "decision_session": str(daily.get("decision_session") or pipeline.get("sessions", {}).get("decision")),
        "execution_session": str(daily.get("execution_session") or pipeline.get("sessions", {}).get("execution")),
        "idempotency_status": str(daily.get("idempotency_status", "")),
        "canonical_report_ref": _relative(output_dir, report_path),
        "canonical_report_digest": report_digest(combined),
        "state_hash_before": dict(daily.get("state", {})).get("hash_before"),
        "state_hash_after": dict(daily.get("state", {})).get("hash_after"),
        "selected_symbols": tuple(pipeline.get("selected_symbols", ())),
        "candidate_rank": tuple(
            {"symbol": symbol, "factor_rank": row.get("factor_rank"), "composite_score": row.get("composite_score")}
            for symbol, row in sorted(dict(pipeline.get("evidence", {})).items(), key=lambda item: int(dict(item[1]).get("factor_rank", 10**9)))
        ),
        "funnel": funnel,
        "no_trade_attribution": no_trade,
        "execution_shortfall": execution_shortfall,
        "sizing_compression": sizing,
        "performance_snapshot": {
            "cash": dict(daily.get("ledger_after", {})).get("cash"),
            "market_value": dict(daily.get("ledger_after", {})).get("market_value"),
            "equity": dict(daily.get("ledger_after", {})).get("total_equity"),
            "realized_pnl": dict(daily.get("ledger_after", {})).get("realized_pnl"),
            "unrealized_pnl": dict(daily.get("ledger_after", {})).get("unrealized_pnl"),
            "fee_breakdown": dict(daily.get("fee_breakdown", {})),
        },
        "reconciliation": dict(daily.get("reconciliation_audit", {})),
        "leakage_audit": dict(daily.get("leakage_audit", {})),
    }


def _daily_funnel(pipeline: Mapping[str, Any], daily: Mapping[str, Any]) -> Mapping[str, Any]:
    candidates = tuple(dict(row) for row in dict(pipeline.get("candidates", {})).get("candidates", ()))
    long_count = sum(1 for row in candidates if row.get("direction") == "long")
    exit_count = sum(1 for row in candidates if row.get("direction") == "short")
    events = dict(pipeline.get("candidate_events", {}))
    quant_report = dict(daily.get("quant_firm_report", {}))
    quant_actions = tuple(dict(row) for row in tuple(daily.get("quant_firm_candidate_actions", ()) or ()))
    final_recommendation = str(quant_report.get("final_recommendation", "")).lower()
    approved = final_recommendation in {"buy", "sell", "exit", "mixed", "hold", "approve"} or final_recommendation.startswith("approve")
    allocation_rows = tuple(dict(row) for row in dict(daily.get("allocation_sizing", {}) or {}).get("allocations", ()))
    order_intents = tuple(dict(row) for row in dict(daily.get("order_intents", {}) or {}).get("intents", ()))
    order_ids = _order_ids_from_intents(order_intents)
    buy_order_ids = _order_ids_from_intents(tuple(row for row in order_intents if _intent_side(row) == "buy"))
    sell_order_ids = _order_ids_from_intents(tuple(row for row in order_intents if _intent_side(row) == "sell"))
    skipped = tuple(daily.get("skipped_orders", ()) or ())
    ledger_before = dict(daily.get("ledger_before", {}))
    ledger_after = dict(daily.get("ledger_after", {}))
    fills = tuple(dict(row) for row in tuple(daily.get("fills", ()) or ()))
    partial = tuple(dict(row) for row in tuple(daily.get("partial_fills", ()) or ()))
    no_fills = tuple(dict(row) for row in tuple(daily.get("no_fills", ()) or ()))
    rejections = tuple(dict(row) for row in tuple(daily.get("rejections", ()) or ()))
    outcomes = _outcomes_by_order(daily)
    full_fill_order_ids = {order_id for order_id, row in outcomes.items() if row.get("status") == "filled"}
    partial_order_ids = {order_id for order_id, row in outcomes.items() if row.get("status") == "partial"}
    any_fill_order_ids = (full_fill_order_ids | partial_order_ids) & order_ids
    actionable_candidate_count = long_count + exit_count
    quant_evidence_gap = actionable_candidate_count > 0 and not quant_actions
    rows = {
        "declared_universe_count": len(tuple(dict(pipeline.get("universe", {})).get("supplied", ()) or ())),
        "resolved_universe_count": len(tuple(dict(pipeline.get("universe", {})).get("resolved", ()) or ())),
        "valid_market_evidence_symbol_count": len(tuple(dict(pipeline.get("universe", {})).get("factor_symbols", ()) or ())),
        "factor_accepted_count": len(tuple(pipeline.get("eligible_symbols", ()) or ())),
        "factor_rejected_count": len(dict(pipeline.get("rejected", {}) or {})),
        "factor_selected_long_count": len(tuple(pipeline.get("selected_symbols", ()) or ())),
        "rank_dropout_exit_count": exit_count,
        "selected_candidate_count": len(tuple(pipeline.get("selected_symbols", ()) or ())),
        "selected_long_count": long_count,
        "hold_event_count": len(tuple(events.get("holds", ()) or ())),
        "hold_candidate_count": len(tuple(events.get("holds", ()) or ())),
        "selected_hold_count": len(tuple(events.get("holds", ()) or ())),
        "selected_exit_count": exit_count,
        "long_candidate_count": long_count,
        "exit_candidate_count": exit_count,
        "actionable_candidate_count": actionable_candidate_count,
        "quant_firm_approved_entry_count": sum(1 for row in quant_actions if bool(row.get("approved")) and row.get("requested_action") == "buy"),
        "quant_firm_approved_exit_count": sum(1 for row in quant_actions if bool(row.get("approved")) and row.get("requested_action") == "exit"),
        "quant_firm_blocked_entry_count": sum(1 for row in quant_actions if not bool(row.get("approved")) and row.get("requested_action") == "buy"),
        "quant_firm_blocked_exit_count": sum(1 for row in quant_actions if not bool(row.get("approved")) and row.get("requested_action") == "exit"),
        "quant_firm_candidate_action_gap": "per_candidate_quant_firm_evidence_unavailable" if quant_evidence_gap else None,
        "quant_firm_approved_count": sum(1 for row in quant_actions if bool(row.get("approved"))),
        "quant_firm_rejected_or_blocked_count": sum(1 for row in quant_actions if not bool(row.get("approved"))),
        "positive_allocation_count": sum(1 for row in allocation_rows if int(row.get("target_shares") or 0) > 0),
        "zero_allocation_count": sum(1 for row in allocation_rows if int(row.get("target_shares") or 0) <= 0),
        "buy_order_intent_count": len(buy_order_ids),
        "sell_order_intent_count": len(sell_order_ids),
        "unique_order_intent_count": len(order_ids),
        "order_intent_count": len(order_ids),
        "skipped_order_count": len(skipped),
        "unique_fully_filled_order_count": len(full_fill_order_ids & order_ids),
        "unique_partially_filled_order_count": len(partial_order_ids & order_ids),
        "unique_order_with_any_fill_count": len(any_fill_order_ids),
        "unique_filled_order_count": len(any_fill_order_ids),
        "fill_count": len(fills),
        "partial_fill_count": len(partial),
        "no_fill_order_count": len({order_id for order_id, row in outcomes.items() if row.get("status") in {"deferred", "rejected"}} & order_ids),
        "no_fill_count": len(no_fills),
        "rejected_order_count": len({order_id for order_id, row in outcomes.items() if row.get("status") == "rejected"} & order_ids),
        "rejection_count": len(rejections),
        "positions_before": dict(ledger_before.get("positions", {})),
        "positions_after": dict(ledger_after.get("positions", {})),
    }
    for field in FUNNEL_COUNT_FIELDS:
        rows[field] = int(rows.get(field) or 0)
    return rows


def _daily_no_trade(pipeline: Mapping[str, Any], daily: Mapping[str, Any]) -> Mapping[str, Any]:
    evidence = []
    decision_session = str(daily.get("decision_session") or pipeline.get("sessions", {}).get("decision"))
    execution_session = str(daily.get("execution_session") or pipeline.get("sessions", {}).get("execution"))
    for symbol, reasons in dict(pipeline.get("rejected", {}) or {}).items():
        for reason in tuple(reasons or ()):
            evidence.append(_reason_event(str(reason), "factor_rejected", symbol, {"event_type": "factor_rejected"}, decision_session, execution_session))
    for event_name, rows in dict(pipeline.get("candidate_events", {})).items():
        if event_name in {"entries", "exits"}:
            continue
        for row in tuple(rows or ()):
            payload = dict(row)
            reason = str(payload.get("reason", ""))
            if reason:
                evidence.append(_reason_event(reason, "candidate_pipeline", payload.get("symbol"), {**payload, "event_type": event_name}, decision_session, execution_session))
    no_candidate = dict(pipeline.get("no_candidate", {}))
    if no_candidate.get("active") and no_candidate.get("reason"):
        evidence.append(_reason_event(str(no_candidate["reason"]), "candidate_pipeline", None, {"event_type": "no_candidate"}, decision_session, execution_session))
    for row in tuple(daily.get("quant_firm_candidate_actions", ()) or ()):
        payload = dict(row)
        if not bool(payload.get("approved")):
            evidence.append(_reason_event(str(payload.get("reason_code", "quant_firm_non_actionable_decision")), "quant_firm_candidate_actions", payload.get("symbol"), {**payload, "event_type": "quant_firm_block"}, decision_session, execution_session))
    for row in tuple(dict(daily.get("allocation_sizing", {}) or {}).get("allocations", ()) or ()):
        payload = dict(row)
        if int(payload.get("target_shares") or 0) <= 0:
            reason = _zero_allocation_reason(payload)
            evidence.append(_reason_event(reason, "allocation_sizing", payload.get("symbol"), {**payload, "event_type": "zero_allocation"}, decision_session, execution_session))
    sizing_skip_ids = set()
    for row in tuple(daily.get("sizing_decisions", ()) or ()):
        payload = dict(row)
        if str(payload.get("result_status")) != "skipped":
            continue
        for reason in tuple(payload.get("reason_codes", ()) or ()):
            event = _reason_event(str(reason), "sizing_decisions", payload.get("symbol"), {**payload, "event_type": "sizing_skip"}, decision_session, execution_session)
            sizing_skip_ids.add(event["event_id"])
            evidence.append(event)
    for row in tuple(daily.get("skipped_orders", ()) or ()):
        payload = dict(row)
        event = _reason_event(str(payload.get("reason", "")), "sizing_decisions", payload.get("symbol"), {**payload, "event_type": "sizing_skip"}, decision_session, execution_session)
        if event["event_id"] not in sizing_skip_ids:
            evidence.append(event)
    rejected_ids = {str(dict(row).get("order_id")) for row in tuple(daily.get("rejections", ()) or ()) if dict(row).get("order_id")}
    for row in tuple(daily.get("no_fills", ()) or ()):
        payload = dict(row)
        if str(payload.get("status")) == "rejected" and str(payload.get("order_id")) in rejected_ids:
            continue
        reason = str(payload.get("rejection_or_deferral_reason", ""))
        evidence.append(_reason_event(reason, "execution_outcomes", payload.get("symbol"), {**payload, "event_type": "no_fill_or_rejection"}, decision_session, execution_session))
    for row in tuple(daily.get("rejections", ()) or ()):
        payload = dict(row)
        reason = str(payload.get("rejection_or_deferral_reason", ""))
        evidence.append(_reason_event(reason, "rejections", payload.get("symbol"), {**payload, "event_type": "rejection"}, decision_session, execution_session))
    return _no_trade_report(tuple(item for item in evidence if item["reason_code"]))


def _daily_execution_shortfall(daily: Mapping[str, Any]) -> Mapping[str, Any]:
    evidence = []
    decision_session = str(daily.get("decision_session", ""))
    execution_session = str(daily.get("execution_session", ""))
    final_quantities = _final_order_quantities(daily)
    for order_id, outcome in _outcomes_by_order(daily).items():
        final_quantity = int(final_quantities.get(order_id, 0) or 0)
        filled = int(outcome.get("filled_quantity") or 0)
        if final_quantity <= 0 or filled <= 0 or filled >= final_quantity:
            continue
        payload = {**dict(outcome), "order_id": order_id, "final_order_quantity": final_quantity, "filled_quantity": filled}
        reason = str(payload.get("rejection_or_deferral_reason") or "order_quantity_unfilled")
        evidence.append(_reason_event(reason, "execution_shortfall", payload.get("symbol"), {**payload, "event_type": "order_execution_shortfall"}, decision_session, execution_session))
    return _no_trade_report(tuple(item for item in evidence if item["reason_code"]))


def _reason_event(reason: str, source: str, symbol: Any, evidence: Mapping[str, Any], decision_session: str, execution_session: str) -> Mapping[str, Any]:
    event_type = str(evidence.get("event_type", source))
    candidate_id = evidence.get("candidate_id")
    order_id = evidence.get("order_id")
    return {
        "event_id": payload_digest({"d": decision_session, "x": execution_session, "source": source, "event_type": event_type, "symbol": symbol, "candidate_id": candidate_id, "order_id": order_id, "reason": reason}),
        "decision_session": decision_session,
        "execution_session": execution_session,
        "reason_code": reason,
        "category": _category(reason),
        "source": source,
        "source_stage": source,
        "event_type": event_type,
        "symbol": symbol,
        "candidate_id": candidate_id,
        "order_id": order_id,
        "evidence": _trim_reason_evidence(evidence),
    }


def _no_trade_report(events: tuple[Mapping[str, Any], ...]) -> Mapping[str, Any]:
    by_category: dict[str, int] = {}
    by_reason: dict[str, int] = {}
    unique = {str(event["event_id"]): event for event in events}
    events = tuple(unique[key] for key in sorted(unique))
    for event in events:
        by_category[event["category"]] = by_category.get(event["category"], 0) + 1
        by_reason[event["reason_code"]] = by_reason.get(event["reason_code"], 0) + 1
    total = len(events)
    return {
        "events": events,
        "total_count": total,
        "by_category": _counts_with_percent(by_category, total),
        "by_reason_code": _counts_with_percent(by_reason, total),
        "unclassified_reason_codes": tuple(sorted(reason for reason in by_reason if _category(reason) == "unclassified")),
    }


def _daily_sizing_compression(pipeline: Mapping[str, Any], daily: Mapping[str, Any]) -> Mapping[str, Any]:
    allocation_by_symbol = {
        str(row.get("symbol")): dict(row)
        for row in tuple(dict(daily.get("allocation_sizing", {}) or {}).get("allocations", ()) or ())
    }
    outcome_by_order = _outcomes_by_order(daily)
    rows = []
    for decision in tuple(daily.get("sizing_decisions", ()) or ()):
        decision = dict(decision)
        order_id = str(decision.get("order_id") or "")
        symbol = str(decision.get("symbol"))
        allocation = allocation_by_symbol.get(symbol, {})
        outcome = outcome_by_order.get(order_id, {})
        optimizer_target = int(decision.get("optimizer_target_quantity") or 0)
        final_order = int(decision.get("final_order_quantity") or 0)
        filled = int(outcome.get("filled_quantity") or 0)
        reasons = tuple(str(reason) for reason in decision.get("reason_codes", ()) or ())
        retention_ratio = round(final_order / optimizer_target, 6) if optimizer_target else None
        compression_ratio = round((optimizer_target - final_order) / optimizer_target, 6) if optimizer_target else None
        rows.append(
            {
                "decision_session": daily.get("decision_session"),
                "execution_session": daily.get("execution_session"),
                "symbol": symbol,
                "side": decision.get("side"),
                "order_id": order_id or None,
                "candidate_id": decision.get("candidate_id") or dict(daily.get("order_provenance", {})).get(order_id, {}).get("candidate_id"),
                "result_status": decision.get("result_status"),
                "candidate_score_inputs": _candidate_score_inputs(pipeline, symbol),
                "allocation_raw_score": allocation.get("raw_score"),
                "normalized_score": allocation.get("normalized_score"),
                "target_weight": allocation.get("target_weight"),
                "optimizer_target_shares": optimizer_target,
                "optimizer_target_position_shares": decision.get("optimizer_target_position_shares"),
                "account_portfolio_constrained_target_shares": decision.get("target_after_max_position_cap_shares"),
                "current_position_shares": decision.get("current_position_shares"),
                "t_plus_one_sellable_quantity": decision.get("t_plus_one_sellable_quantity"),
                "t_plus_one_sellable_quantity_status": decision.get("t_plus_one_sellable_quantity_status"),
                "desired_delta_shares": decision.get("desired_delta_shares"),
                "max_position_weight_cap_shares": decision.get("max_position_cap_shares"),
                "max_position_weight_applied_target_shares": decision.get("target_after_max_position_cap_shares"),
                "affordable_quantity_cap_shares": decision.get("affordable_quantity_cap_shares"),
                "cash_applied_quantity_shares": decision.get("quantity_after_cash_constraint_shares"),
                "risk_position_cap_constrained_quantity": decision.get("target_after_max_position_cap_shares"),
                "board_lot_rounded_quantity": decision.get("quantity_after_board_lot_shares"),
                "final_order_quantity": final_order,
                "optimizer_to_order": {
                    "compression_shares": max(optimizer_target - final_order, 0),
                    "retention_ratio": retention_ratio,
                    "compression_ratio": compression_ratio,
                    "reason_codes": reasons,
                },
                "order_to_fill": {
                    "filled_quantity": filled,
                    "unfilled_quantity": max(final_order - filled, 0),
                    "shortfall_reason_code": outcome.get("rejection_or_deferral_reason"),
                    "ordered_fill_ratio": round(filled / final_order, 6) if final_order else None,
                },
                "optimizer_to_order_compression_shares": max(optimizer_target - final_order, 0),
                "optimizer_to_order_retention_ratio": retention_ratio,
                "optimizer_to_order_compression_ratio": compression_ratio,
                "order_to_fill_shortfall": max(final_order - filled, 0),
                "ordered_fill_ratio": round(filled / final_order, 6) if final_order else None,
                "compression_reason_codes": reasons,
            }
        )
    return {
        "examples": tuple(rows),
        "top_compression_reasons": _top_reasons(tuple(reason for row in rows for reason in row["compression_reason_codes"])),
        "largest_compression_examples": tuple(sorted(rows, key=lambda row: int(row["optimizer_to_order_compression_shares"]), reverse=True)[:5]),
    }


def _performance(capital: float, daily_reports: tuple[Mapping[str, Any], ...]) -> Mapping[str, Any]:
    if not daily_reports:
        return {}
    final = dict(daily_reports[-1].get("ledger_after", {}))
    equities = [float(capital)] + [float(dict(report.get("ledger_after", {})).get("total_equity", capital)) for report in daily_reports]
    market_values = [float(dict(report.get("ledger_after", {})).get("market_value", 0.0)) for report in daily_reports]
    fees = _sum_fee_breakdowns(daily_reports)
    fills = tuple(dict(row) for report in daily_reports for row in tuple(report.get("fills", ()) or ()) + tuple(report.get("partial_fills", ()) or ()))
    order_ids = tuple(
        str(dict(intent).get("metadata", {}).get("order_id"))
        for report in daily_reports
        for intent in tuple(dict(report.get("order_intents", {}) or {}).get("intents", ()) or ())
    )
    unique_order_ids = {order_id for order_id in order_ids if order_id and order_id != "None"}
    filled_order_ids = {
        order_id
        for report in daily_reports
        for order_id, outcome in _outcomes_by_order(report).items()
        if outcome.get("status") in {"filled", "partial"}
    } & unique_order_ids
    order_count = len(unique_order_ids)
    fill_count = len(fills)
    net_pnl = round(float(final.get("total_equity", capital)) - float(capital), 6)
    realized = float(final.get("realized_pnl", 0.0))
    unrealized = float(final.get("unrealized_pnl", 0.0))
    active_sessions = sum(1 for report in daily_reports if tuple(report.get("fills", ()) or ()) or tuple(report.get("partial_fills", ()) or ()))
    end_equities = equities[1:]
    exposure_rates = [round(mv / eq, 6) if eq else 0.0 for mv, eq in zip(market_values, end_equities)]
    closed_sell_fills = tuple(row for row in fills if str(dict(row).get("side")) == "sell")
    return {
        "initial_capital": float(capital),
        "final_cash": final.get("cash"),
        "final_market_value": final.get("market_value"),
        "final_equity": final.get("total_equity"),
        "gross_pnl": {"value": round(net_pnl + float(fees["total_cost"]), 6), "data_gap_reason": None} if _fee_components_available(daily_reports) else {"value": None, "data_gap_reason": "not all canonical fee components are available"},
        "explicit_fees": {"components": fees, "component_availability": _fee_component_availability(daily_reports)},
        "explicit_slippage_cost": {"value": fees["slippage_cost"], "data_gap_reason": None} if _fee_components_available(daily_reports, keys=("slippage_cost",)) else {"value": None, "data_gap_reason": "slippage cost component unavailable"},
        "net_pnl": net_pnl,
        "total_return": round(net_pnl / float(capital), 6),
        "realized_pnl": realized,
        "unrealized_pnl": unrealized,
        "maximum_drawdown": _maximum_drawdown(equities),
        "unique_order_intent_count": order_count,
        "order_count": order_count,
        "fill_record_count": fill_count,
        "filled_order_count": len(filled_order_ids),
        "fill_count": fill_count,
        "completed_buy_sell_trade_count": {"value": None, "data_gap_reason": "exact entry/exit round-trip identity unavailable"},
        "fill_rate": round(len(filled_order_ids) / order_count, 6) if order_count else None,
        "turnover": round(_turnover_notional(daily_reports) / float(capital), 6),
        "average_exposure": round(sum(exposure_rates) / len(exposure_rates), 6) if exposure_rates else 0.0,
        "maximum_exposure": max(exposure_rates) if exposure_rates else 0.0,
        "trading_session_count": len(daily_reports),
        "active_trading_session_count": active_sessions,
        "no_trade_session_count": len(daily_reports) - active_sessions,
        "no_trade_session_rate": round((len(daily_reports) - active_sessions) / len(daily_reports), 6),
        "average_holding_period": _average_holding_period(daily_reports, closed_sell_fills),
        "win_rate_closed_realized_trades": {"value": None, "data_gap_reason": "exact entry/exit round-trip identity unavailable"},
        "profit_factor_closed_realized_trades": {"value": None, "data_gap_reason": "exact entry/exit round-trip identity unavailable"},
        "formula_notes": {
            "net_pnl": "final_equity - initial_capital",
            "gross_pnl": "net_pnl + explicit fee_breakdown.total_cost only when canonical fee components are available",
            "total_return": "net_pnl / initial_capital",
            "maximum_drawdown": "minimum daily end-equity drawdown from prior peak",
            "turnover": "sum non-overlapping fill outcome gross_value / initial_capital",
        },
    }


def _capital_comparison(capital_runs: list[Mapping[str, Any]]) -> Mapping[str, Any]:
    ranks_by_capital = {
        str(run["initial_capital"]): tuple((row["decision_session"], tuple((item["symbol"], item["factor_rank"]) for item in row["candidate_rank"])) for row in run["daily_summaries"])
        for run in capital_runs
    }
    first = next(iter(ranks_by_capital.values()), ())
    return {
        "candidate_identity_rank_consistent": all(value == first for value in ranks_by_capital.values()),
        "candidate_ranks_by_capital": ranks_by_capital,
        "rows": tuple(
            {
                "initial_capital": run["initial_capital"],
                "selected_candidate_count": run["funnel"]["totals"].get("selected_candidate_count", 0),
                "order_count": run["performance"]["order_count"],
                "fill_count": run["performance"]["fill_count"],
                "below_one_lot_skips": _category_count(run["no_trade_attribution"], "less_than_one_valid_board_lot"),
                "insufficient_cash_skips": _category_count(run["no_trade_attribution"], "insufficient_available_cash"),
                "turnover": run["performance"]["turnover"],
                "fees": run["performance"]["explicit_fees"]["components"]["total_cost"],
                "net_pnl": run["performance"]["net_pnl"],
                "return": run["performance"]["total_return"],
                "maximum_drawdown": run["performance"]["maximum_drawdown"],
                "no_trade_rate": run["performance"]["no_trade_session_rate"],
                "final_equity": run["performance"]["final_equity"],
            }
            for run in capital_runs
        ),
    }


def _bounded_market_evidence(
    config: RealDailyEvaluationConfig,
    start: date,
    end: date,
    *,
    calendar_provider: Any | None,
    bar_provider: Any | None,
) -> tuple[TradingCalendar, tuple[Mapping[str, Any], ...], Mapping[str, Any]]:
    mode = _effective_market_mode(config)
    if mode == "live_market_data":
        real_calendar_provider = calendar_provider or TusharePrimaryBaoStockCalendarProvider()
        calendar_result = real_calendar_provider.fetch_calendar_with_provenance(start - timedelta(days=160), end + timedelta(days=10))
        calendar = calendar_result.calendar
        if not calendar.is_session(start) or not calendar.is_session(end):
            raise ValueError("start/end decision sessions must be real loaded trading sessions")
        factor_start = calendar.shift_session(start, -60)
        final_execution = calendar.next_session(end)
        cached_calendar_provider = _CachedCalendarProvider(calendar_result)
        loaded = load_provider_market_rows(
            decision_session=end,
            calendar_start=start - timedelta(days=140),
            calendar_end=end + timedelta(days=10),
            symbols=_symbols(config.symbols),
            bar_start_session=factor_start,
            bar_end_session=final_execution,
            calendar_provider=cached_calendar_provider,
            bar_provider=bar_provider,
            max_symbol_cap=config.max_execution_symbols,
            cap_error_message="--live-market-data supports at most 6 explicit symbols",
        )
        warmup_sessions = calendar.sessions_between(factor_start, start)
        return loaded.calendar, loaded.rows, {
            "mode": "live_market_data",
            "bounded_once_per_evaluation": True,
            "warmup_start_session": factor_start.isoformat(),
            "earliest_decision_factor_session_count": len(warmup_sessions),
            "calendar": loaded.calendar_provenance,
            "market": loaded.market_data_provenance,
        }
    if config.offline_calendar_sessions:
        calendar = TradingCalendar(tuple(date.fromisoformat(value) for value in config.offline_calendar_sessions), ProviderName.BAOSTOCK)
    else:
        calendar = _synthetic_fixture_calendar(start, end)
    if not calendar.is_session(start) or not calendar.is_session(end):
        raise ValueError("offline evaluation start/end must be trading sessions in the offline calendar")
    rows = _canonical_bars(config.input_bars) if config.input_bars else _offline_bounded_bars(calendar, _symbols(config.symbols), start, end)
    if config.input_bars:
        off_calendar = tuple(row for row in rows if not calendar.is_session(date.fromisoformat(str(row["date"]))))
        if off_calendar:
            first = off_calendar[0]
            raise ValueError(f"offline_input_bars contain off-calendar bar: {first['symbol']} {first['date']}")
    factor_start = calendar.shift_session(start, -60)
    warmup_sessions = calendar.sessions_between(factor_start, start)
    return calendar, tuple(_canonical_bar(row) for row in rows if calendar.is_session(date.fromisoformat(str(row["date"])))), {
        "mode": mode,
        "calendar_sessions": calendar.to_iso_strings(),
        "bounded_once_per_evaluation": True,
        "warmup_start_session": factor_start.isoformat(),
        "earliest_decision_factor_session_count": len(warmup_sessions),
        "network_calls": 0,
        "deepseek_live_call": False,
        "symbol_count": len(config.symbols),
    }


class _CachedCalendarProvider:
    def __init__(self, result: Any) -> None:
        self._result = result

    def fetch_calendar_with_provenance(self, start_date: date, end_date: date) -> Any:
        return self._result


def _synthetic_fixture_calendar(start: date, end: date) -> TradingCalendar:
    sessions: list[date] = []
    cursor = start - timedelta(days=120)
    while cursor <= end + timedelta(days=10):
        if cursor.weekday() < 5:
            sessions.append(cursor)
        cursor += timedelta(days=1)
    return TradingCalendar(tuple(sessions), ProviderName.BAOSTOCK)


def _aggregate_funnel(funnels: tuple[Mapping[str, Any], ...]) -> Mapping[str, Any]:
    totals = {key: sum(int(funnel.get(key) or 0) for funnel in funnels) for key in FUNNEL_COUNT_FIELDS}
    availability = {
        key: {
            "available_session_count": sum(
                1
                for funnel in funnels
                if key in funnel and (key not in QUANT_FIRM_EVIDENCE_FIELDS or not funnel.get("quant_firm_candidate_action_gap"))
            ),
            "session_count": len(funnels),
        }
        for key in FUNNEL_COUNT_FIELDS
    }
    quant_gap_count = sum(1 for funnel in funnels if funnel.get("quant_firm_candidate_action_gap"))
    rates = {
        "market_evidence_per_resolved_universe": _rate(totals.get("valid_market_evidence_symbol_count", 0), totals.get("resolved_universe_count", 0)),
        "factor_acceptance_rate": _rate(totals.get("factor_accepted_count", 0), totals.get("factor_accepted_count", 0) + totals.get("factor_rejected_count", 0)),
        "factor_selection_rate": _validated_rate("factor_selection_rate", totals.get("factor_selected_long_count", 0), totals.get("factor_accepted_count", 0)),
        "selection_rate": _validated_rate("selection_rate", totals.get("factor_selected_long_count", 0), totals.get("factor_accepted_count", 0)),
        "quant_firm_approval_rate": _rate(totals.get("quant_firm_approved_count", 0), totals.get("quant_firm_approved_count", 0) + totals.get("quant_firm_rejected_or_blocked_count", 0)),
        "positive_allocation_rate": _rate(totals.get("positive_allocation_count", 0), totals.get("positive_allocation_count", 0) + totals.get("zero_allocation_count", 0)),
        "entry_order_rate": None if quant_gap_count else _validated_rate("entry_order_rate", totals.get("buy_order_intent_count", 0), totals.get("quant_firm_approved_entry_count", 0)),
        "exit_order_rate": None if quant_gap_count else _validated_rate("exit_order_rate", totals.get("sell_order_intent_count", 0), totals.get("quant_firm_approved_exit_count", 0)),
        "filled_order_rate": _validated_rate("filled_order_rate", totals.get("unique_order_with_any_fill_count", 0), totals.get("unique_order_intent_count", 0)),
    }
    return {
        "totals": totals,
        "availability": availability,
        "rates": rates,
        "rate_data_gap_reasons": {"entry_order_rate": "per_candidate_quant_firm_evidence_unavailable", "exit_order_rate": "per_candidate_quant_firm_evidence_unavailable"} if quant_gap_count else {},
        "data_gaps": {"quant_firm_candidate_action_gap_session_count": quant_gap_count},
    }


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _validated_rate(name: str, numerator: int, denominator: int) -> float | None:
    numerator = int(numerator or 0)
    denominator = int(denominator or 0)
    if denominator <= 0:
        if numerator > 0:
            raise ValueError(f"{name} invariant violation: numerator {numerator} exceeds unavailable denominator {denominator}")
        return None
    if numerator > denominator:
        raise ValueError(f"{name} invariant violation: numerator {numerator} exceeds denominator {denominator}")
    return _rate(numerator, denominator)


def _aggregate_no_trade(items: tuple[Mapping[str, Any], ...]) -> Mapping[str, Any]:
    events = tuple(event for item in items for event in tuple(item.get("events", ()) or ()))
    return _no_trade_report(events)


def _aggregate_execution_shortfall(items: tuple[Mapping[str, Any], ...]) -> Mapping[str, Any]:
    events = tuple(event for item in items for event in tuple(item.get("events", ()) or ()))
    return _no_trade_report(events)


def _aggregate_sizing(items: tuple[Mapping[str, Any], ...]) -> Mapping[str, Any]:
    examples = tuple(example for item in items for example in tuple(item.get("examples", ()) or ()))
    return {
        "examples": examples,
        "top_compression_reasons": _top_reasons(tuple(reason for row in examples for reason in row["compression_reason_codes"])),
        "largest_compression_examples": tuple(sorted(examples, key=lambda row: int(row["optimizer_to_order_compression_shares"]), reverse=True)[:10]),
    }


def _validate_config(config: RealDailyEvaluationConfig) -> tuple[date, date]:
    try:
        start = date.fromisoformat(str(config.start_decision_session))
        end = date.fromisoformat(str(config.end_decision_session))
    except ValueError as exc:
        raise ValueError("start/end decision sessions must use YYYY-MM-DD") from exc
    if start > end:
        raise ValueError("start_decision_session must be before or equal to end_decision_session")
    if not str(config.strategy_id).strip():
        raise ValueError("strategy_id must be non-empty")
    if not config.symbols:
        raise ValueError("symbols must be non-empty")
    _symbols(config.symbols)
    if not 1 <= int(config.max_execution_symbols) <= 6:
        raise ValueError("max_execution_symbols must be between 1 and 6")
    if not 1 <= int(config.target_symbol_count) <= int(config.max_execution_symbols):
        raise ValueError("target_symbol_count must be between 1 and max_execution_symbols")
    _capital_values(config.capital_values)
    _effective_market_mode(config)
    return start, end


def _effective_market_mode(config: RealDailyEvaluationConfig) -> str:
    if config.live_market_data:
        mode = "live_market_data"
    elif config.input_bars:
        if not config.offline_calendar_sessions:
            raise ValueError("input_bars require explicit offline_calendar_sessions")
        mode = "offline_input_bars"
    else:
        mode = "synthetic_engineering_fixture"
    requested = str(config.provider_mode or "auto")
    if requested == "offline_fixture":
        raise ValueError("provider_mode must be auto or the derived market evidence mode")
    if requested not in {"auto", mode}:
        allowed = ", ".join(sorted({"auto", mode}))
        raise ValueError(f"provider_mode must be one of: {allowed}")
    return mode


def _capital_values(values: Iterable[float]) -> tuple[float, ...]:
    result = tuple(sorted(set(round(float(value), 6) for value in values)))
    if not result or any(value <= 0 or not math.isfinite(value) for value in result):
        raise ValueError("capital_values must be positive finite numbers")
    return result


def _symbols(symbols: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(dict.fromkeys(canonicalize_a_share_symbol(symbol) for symbol in symbols)))


def _rows_through_execution(rows: tuple[Mapping[str, Any], ...], execution: date) -> tuple[Mapping[str, Any], ...]:
    return tuple(row for row in rows if date.fromisoformat(str(row["date"])) <= execution)


def _signals_available_for_decision(signals: tuple[Any, ...], decision: date) -> tuple[Any, ...]:
    cutoff = datetime(decision.year, decision.month, decision.day, 15, 0, tzinfo=SHANGHAI_TZ)
    available = []
    for signal in signals:
        row = dict(signal)
        timestamp = _aware_signal_time(row)
        if timestamp <= cutoff:
            available.append(row)
    return _canonical_information_signals(tuple(available))


def _context_for_decision(context: Mapping[str, Any], decision: date) -> Mapping[str, Any]:
    validate_pit_safe_inputs(context, decision)
    return context


def _aware_signal_time(signal: Mapping[str, Any]) -> datetime:
    if "signal" not in signal or "available_at" not in signal:
        raise ValueError("information_signals must use the canonical structured PIT envelope")
    parsed = datetime.fromisoformat(str(signal["available_at"]))
    if parsed.tzinfo is None:
        raise ValueError("information signal available_at must be timezone-aware")
    return parsed.astimezone(SHANGHAI_TZ)


def _offline_bounded_bars(
    calendar: TradingCalendar,
    symbols: tuple[str, ...],
    start: date,
    end: date,
) -> tuple[Mapping[str, Any], ...]:
    factor_start = calendar.shift_session(start, -60)
    execution_end = calendar.next_session(end)
    sessions = calendar.sessions_between(factor_start, execution_end)
    rows: list[Mapping[str, Any]] = []
    for symbol_index, symbol in enumerate(symbols):
        base = 9.0 + symbol_index * 3.0
        previous_close = base
        for index, session in enumerate(sessions):
            drift = (len(symbols) - symbol_index) * 0.006
            wave = math.sin(index / 5.0 + symbol_index) * 0.03
            close = round(base * (1.0 + drift * index + wave), 4)
            rows.append(
                {
                    "symbol": symbol,
                    "date": session.isoformat(),
                    "open": round(close * 0.995, 4),
                    "high": round(close * 1.015, 4),
                    "low": round(close * 0.985, 4),
                    "close": close,
                    "previous_close": previous_close,
                    "volume": float(120_000 + symbol_index * 25_000 + index * 100),
                    "amount": round(close * (120_000 + symbol_index * 25_000 + index * 100), 6),
                    "is_suspended": False,
                    "provider": "synthetic_engineering_fixture",
                }
            )
            previous_close = close
    return tuple(rows)


def _canonical_bar(row: Mapping[str, Any]) -> Mapping[str, Any]:
    trade_date = row.get("date", row.get("trade_date"))
    if isinstance(trade_date, date):
        trade_date = trade_date.isoformat()
    return {
        "symbol": canonicalize_a_share_symbol(row["symbol"]),
        "date": date.fromisoformat(str(trade_date)).isoformat(),
        "open": float(row["open"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "close": float(row["close"]),
        "previous_close": None if row.get("previous_close") is None else float(row["previous_close"]),
        "volume": float(row.get("volume", 0.0)),
        "amount": None if row.get("amount") is None else float(row.get("amount")),
        "is_suspended": bool(row.get("is_suspended", False)),
        "provider": str(row.get("provider", "input")),
    }


def _canonical_bars(rows: Iterable[Mapping[str, Any]]) -> tuple[Mapping[str, Any], ...]:
    deduped: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in rows:
        payload = _canonical_bar(row)
        key = (str(payload["symbol"]), str(payload["date"]))
        if key in deduped and dict(deduped[key]) != dict(payload):
            raise ValueError(f"conflicting offline bar rows for {key[0]} on {key[1]}")
        deduped[key] = payload
    return tuple(deduped[key] for key in sorted(deduped, key=lambda item: (item[1], item[0])))


def _canonical_information_signals(signals: tuple[Any, ...]) -> tuple[Any, ...]:
    rows = tuple(_json_ready(signal) for signal in signals)
    by_identity: dict[str, tuple[str, Any]] = {}
    for index, signal in enumerate(rows):
        if not isinstance(signal, Mapping):
            raise ValueError("information_signals must use structured PIT envelopes")
        _aware_signal_time(signal)
        identity = signal.get("source_event_id") or signal.get("signal_id") or signal.get("id")
        if not identity:
            identity = payload_digest(signal)
        identity = str(identity)
        digest = payload_digest(signal)
        existing = by_identity.get(identity)
        if existing is not None and existing[0] != digest:
            raise ValueError(f"conflicting information signal payload for identity: {identity}")
        by_identity[identity] = (digest, signal)
    return tuple(row for _identity, (_digest, row) in sorted(by_identity.items(), key=lambda item: item[0]))


def _signal_ids(signals: tuple[Any, ...]) -> tuple[str, ...]:
    values = []
    for signal in signals:
        row = dict(signal)
        values.append(str(row.get("source_event_id") or row.get("signal_id") or row.get("id") or payload_digest(row)))
    return tuple(sorted(values))


def _calendar_session_payload(sessions: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(date.fromisoformat(str(value)).isoformat() for value in sorted(set(sessions)))


def _load_or_create_manifest(output_dir: Path, request_digest: str, config: RealDailyEvaluationConfig) -> Mapping[str, Any]:
    path = output_dir / "evaluation_manifest.json"
    existing = _read_json(path)
    if existing is not None:
        if existing.get("evaluation_request_digest") != request_digest:
            raise ValueError("evaluation manifest belongs to a different request digest")
        return existing
    payload = {
        "schema_version": DAILY_EVALUATION_SCHEMA_VERSION,
        "evaluator_version": DAILY_EVALUATION_VERSION,
        "evaluation_request_digest": request_digest,
        "capital_starting_state_hashes": {
            _capital_label(capital): load_daily_state(output_dir / f"capital_{_capital_label(capital)}" / "state.json", initial_capital=capital).state_hash
            for capital in _capital_values(config.capital_values)
        },
    }
    _write_json_atomic(payload, path)
    return payload


def _read_json(path: Path) -> Mapping[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _read_json_for_recovery(path: Path) -> tuple[Mapping[str, Any] | None, str | None]:
    if not path.exists():
        return None, "missing"
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except json.JSONDecodeError:
        return None, "malformed_json"


def _verified_daily_combined_report(
    *,
    existing_combined: Mapping[str, Any] | None,
    existing_error: str | None,
    result_combined: Mapping[str, Any] | None,
    report_path: Path,
    replay_status: str,
) -> Mapping[str, Any]:
    if result_combined is None:
        if existing_combined is None:
            raise EvaluationReportIntegrityError("daily report recovery has neither result nor existing report")
        return existing_combined
    if replay_status != "idempotent_replay":
        write_report_atomic(result_combined, report_path)
        return result_combined
    if existing_combined is not None:
        mismatch = _daily_report_parity_mismatch(existing_combined, result_combined)
        if not mismatch:
            write_report_atomic(existing_combined, report_path)
            return existing_combined
        raise EvaluationReportIntegrityError(f"existing daily report failed replay parity: {mismatch}")
    write_report_atomic(result_combined, report_path)
    return result_combined


def _daily_report_parity_mismatch(existing: Mapping[str, Any], replay: Mapping[str, Any]) -> tuple[str, ...]:
    mismatches: list[str] = []
    existing_daily = dict(existing.get("daily_paper_loop", {}) or {})
    replay_daily = dict(replay.get("daily_paper_loop", {}) or {})
    existing_pipeline = dict(existing.get("candidate_pipeline", {}) or {})
    replay_pipeline = dict(replay.get("candidate_pipeline", {}) or {})
    for field in ("decision_session", "execution_session"):
        if existing_daily.get(field) != replay_daily.get(field):
            mismatches.append(field)
    if existing_pipeline.get("pipeline_request_digest") != replay_pipeline.get("pipeline_request_digest"):
        mismatches.append("pipeline_request_digest")
    existing_state = dict(existing_daily.get("state", {}) or {})
    replay_state = dict(replay_daily.get("state", {}) or {})
    for field in ("hash_before", "hash_after"):
        if existing_state.get(field) != replay_state.get(field):
            mismatches.append(f"state.{field}")
    existing_snapshot = dict(dict(existing_daily.get("information_provenance", {}) or {}).get("candidate_pipeline_snapshot", {}) or {})
    replay_snapshot = dict(dict(replay_daily.get("information_provenance", {}) or {}).get("candidate_pipeline_snapshot", {}) or {})
    if existing_snapshot.get("pipeline_request_digest") != replay_snapshot.get("pipeline_request_digest"):
        mismatches.append("snapshot.pipeline_request_digest")
    if payload_digest(existing_snapshot.get("candidate_pipeline_report")) != payload_digest(replay_snapshot.get("candidate_pipeline_report")):
        mismatches.append("snapshot.candidate_pipeline_report")
    if payload_digest(existing_pipeline) != payload_digest(replay_pipeline):
        mismatches.append("candidate_pipeline")
    if payload_digest(_substantive_daily_report_payload(existing)) != payload_digest(_substantive_daily_report_payload(replay)):
        mismatches.append("substantive_daily_report")
    return tuple(mismatches)


def _substantive_daily_report_payload(combined: Mapping[str, Any]) -> Mapping[str, Any]:
    return _strip_replay_only_fields(_json_ready(combined))


def _strip_replay_only_fields(value: Any) -> Any:
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            if key in {"idempotency_status", "replay_execution_status"}:
                continue
            if key == "path" or str(key).endswith("_path") or str(key).endswith("_ref"):
                continue
            result[key] = _strip_replay_only_fields(item)
        return result
    if isinstance(value, (tuple, list)):
        return tuple(_strip_replay_only_fields(item) for item in value)
    return value


def _write_json_atomic(payload: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(_json_ready(payload), sort_keys=True, indent=2, ensure_ascii=True))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, path)


def _run_config_payload(config: RealDailyEvaluationConfig) -> Mapping[str, Any]:
    mode = _effective_market_mode(config)
    return {
        "strategy_id": config.strategy_id,
        "symbols": _symbols(config.symbols),
        "capital_values": _capital_values(config.capital_values),
        "live_market_data": bool(config.live_market_data),
        "market_evidence_mode": mode,
        "provider_mode": mode,
        "offline_calendar_sessions": _calendar_session_payload(config.offline_calendar_sessions),
        "max_execution_symbols": int(config.max_execution_symbols),
        "target_symbol_count": int(config.target_symbol_count),
    }


def _category(reason: str) -> str:
    if reason.startswith("hold_no_decision_"):
        suffix = reason.removeprefix("hold_no_decision_")
        if suffix in {"missing_factor_evidence", "insufficient_factor_evidence", "factor_rejected", "invalid_factor_evidence"}:
            return "factor_evidence_missing_hold"
    return NO_TRADE_TAXONOMY.get(reason, "unclassified")


def _zero_allocation_reason(row: Mapping[str, Any]) -> str:
    limitations = tuple(str(value) for value in row.get("limitations", ()) or ())
    if any("too small" in value.lower() and "one configured lot" in value.lower() for value in limitations):
        return "target_weight_too_small_for_one_lot"
    if int(row.get("target_shares") or 0) <= 0:
        return "zero_target_shares"
    return "zero_allocation"


def _counts_with_percent(counts: Mapping[str, int], total: int) -> Mapping[str, Mapping[str, float | int]]:
    return {
        key: {"count": int(value), "percentage": round(int(value) / total, 6) if total else 0.0}
        for key, value in sorted(counts.items())
    }


def _top_reasons(reasons: tuple[str, ...]) -> tuple[Mapping[str, Any], ...]:
    counts: dict[str, int] = {}
    for reason in reasons:
        counts[str(reason)] = counts.get(str(reason), 0) + 1
    return tuple({"reason_code": reason, "count": count} for reason, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _candidate_score_inputs(pipeline: Mapping[str, Any], symbol: str) -> Mapping[str, Any]:
    evidence = dict(dict(pipeline.get("evidence", {})).get(symbol, {}) or {})
    return {
        "factor_rank": evidence.get("factor_rank"),
        "composite_score": evidence.get("composite_score"),
        "factor_evidence": evidence.get("factor_evidence"),
    }


def _trim_reason_evidence(evidence: Mapping[str, Any]) -> Mapping[str, Any]:
    return _strip_sensitive_bar_fields(_json_ready(evidence))


def _strip_sensitive_bar_fields(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _strip_sensitive_bar_fields(item) for key, item in value.items() if key != "previous_close"}
    if isinstance(value, (tuple, list)):
        return tuple(_strip_sensitive_bar_fields(item) for item in value)
    return value


def _sum_fee_breakdowns(daily_reports: tuple[Mapping[str, Any], ...]) -> Mapping[str, float]:
    keys = ("commission", "transaction_tax", "transfer_or_exchange_fee", "slippage_cost", "total_cost")
    totals = {key: 0.0 for key in keys}
    for report in daily_reports:
        fees = dict(report.get("fee_breakdown", {}) or {})
        for key in keys:
            totals[key] = round(totals[key] + float(fees.get(key, 0.0)), 6)
    return totals


def _fee_component_availability(daily_reports: tuple[Mapping[str, Any], ...]) -> Mapping[str, bool]:
    keys = ("commission", "transaction_tax", "transfer_or_exchange_fee", "slippage_cost", "total_cost")
    return {key: all(key in dict(report.get("fee_breakdown", {}) or {}) for report in daily_reports) for key in keys}


def _fee_components_available(daily_reports: tuple[Mapping[str, Any], ...], *, keys: tuple[str, ...] = ("commission", "transaction_tax", "transfer_or_exchange_fee", "slippage_cost", "total_cost")) -> bool:
    availability = _fee_component_availability(daily_reports)
    return all(bool(availability.get(key)) for key in keys)


def _maximum_drawdown(equities: list[float]) -> float:
    peak = None
    max_dd = 0.0
    for equity in equities:
        peak = equity if peak is None else max(peak, equity)
        if peak and peak > 0:
            max_dd = min(max_dd, round((equity - peak) / peak, 6))
    return max_dd


def _order_ids_from_intents(order_intents: tuple[Mapping[str, Any], ...]) -> set[str]:
    return {
        str(dict(intent).get("metadata", {}).get("order_id"))
        for intent in order_intents
        if dict(intent).get("metadata", {}).get("order_id")
    }


def _intent_side(intent: Mapping[str, Any]) -> str:
    return str(dict(intent).get("side", "")).lower()


def _final_order_quantities(daily: Mapping[str, Any]) -> Mapping[str, int]:
    quantities: dict[str, int] = {}
    for decision in tuple(daily.get("sizing_decisions", ()) or ()):
        row = dict(decision)
        order_id = str(row.get("order_id") or "")
        if order_id:
            quantities[order_id] = int(row.get("final_order_quantity") or 0)
    for intent in tuple(dict(daily.get("order_intents", {}) or {}).get("intents", ()) or ()):
        row = dict(intent)
        order_id = str(dict(row.get("metadata", {}) or {}).get("order_id") or "")
        if order_id and order_id not in quantities:
            quantities[order_id] = int(row.get("target_shares") or 0)
    return quantities


def _outcomes_by_order(daily: Mapping[str, Any]) -> Mapping[str, Mapping[str, Any]]:
    full: dict[str, dict[str, Any]] = {}
    partial: dict[str, dict[str, Any]] = {}
    no_fill: dict[str, dict[str, Any]] = {}
    for row in tuple(daily.get("fills", ()) or ()):
        payload = dict(row)
        order_id = str(payload.get("order_id") or "")
        if not order_id:
            continue
        full[order_id] = {**payload, "status": "filled", "filled_quantity": int(payload.get("filled_quantity") or 0), "gross_value": float(payload.get("gross_value", 0.0) or 0.0)}
    for row in tuple(daily.get("partial_fills", ()) or ()):
        payload = dict(row)
        order_id = str(payload.get("order_id") or "")
        if not order_id or order_id in full:
            continue
        current = partial.setdefault(order_id, {**payload, "status": "partial", "filled_quantity": 0, "gross_value": 0.0})
        current["filled_quantity"] = int(current.get("filled_quantity", 0)) + int(payload.get("filled_quantity") or 0)
        current["gross_value"] = round(float(current.get("gross_value", 0.0)) + float(payload.get("gross_value", 0.0)), 6)
        if payload.get("rejection_or_deferral_reason"):
            current["rejection_or_deferral_reason"] = payload.get("rejection_or_deferral_reason")
    for row in tuple(daily.get("no_fills", ()) or ()) + tuple(daily.get("rejections", ()) or ()):
        payload = dict(row)
        order_id = str(payload.get("order_id") or "")
        if not order_id or order_id in full or order_id in partial:
            continue
        no_fill.setdefault(order_id, {**payload, "filled_quantity": 0, "gross_value": 0.0})
    final_quantities = _final_order_quantities(daily)
    grouped = {**no_fill, **partial, **full}
    for order_id, outcome in tuple(grouped.items()):
        final_quantity = int(final_quantities.get(order_id, 0) or 0)
        if final_quantity and int(outcome.get("filled_quantity") or 0) > final_quantity:
            raise EvaluationReportIntegrityError(
                f"order outcome integrity violation: filled quantity exceeds final order quantity for {order_id}"
            )
    return dict(sorted(grouped.items()))


def _turnover_notional(daily_reports: tuple[Mapping[str, Any], ...]) -> float:
    total = 0.0
    for report in daily_reports:
        for outcome in _outcomes_by_order(report).values():
            total = round(total + float(outcome.get("gross_value", 0.0)), 6)
    return total


def _average_holding_period(daily_reports: tuple[Mapping[str, Any], ...], sell_fills: tuple[Mapping[str, Any], ...]) -> Mapping[str, Any]:
    return {"value": None, "data_gap_reason": "exact entry/exit round-trip identity unavailable"}


def _reconciliation_summary(daily_reports: tuple[Mapping[str, Any], ...]) -> Mapping[str, Any]:
    statuses = tuple(str(dict(report.get("reconciliation_audit", {})).get("status")) for report in daily_reports)
    return {"all_passed": all(status == "passed" for status in statuses), "statuses": statuses}


def _provider_data_gaps(daily_reports: tuple[Mapping[str, Any], ...]) -> tuple[Mapping[str, Any], ...]:
    gaps = []
    for report in daily_reports:
        provenance = dict(report.get("market_data_provenance", {}) or {})
        if provenance.get("factor_rows_excluded_after_decision") is None:
            gaps.append({"decision_session": report.get("decision_session"), "gap": "factor_exclusion_count_unavailable"})
    return tuple(gaps)


def _data_quality(capital_runs: list[Mapping[str, Any]], acquisition: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "bounded_acquisition": bool(acquisition.get("bounded_once_per_evaluation")),
        "all_reconciliations_passed": all(run["reconciliation_summary"]["all_passed"] for run in capital_runs),
        "unexpected_unclassified_reasons": tuple(
            sorted(
                {
                    reason
                    for run in capital_runs
                    for source in (run["no_trade_attribution"], run["execution_shortfall"])
                    for reason in tuple(source.get("unclassified_reason_codes", ()) or ())
                }
            )
        ),
    }


def _metric_definitions() -> Mapping[str, str]:
    return {
        "net_pnl": "final_equity - initial_capital when there are no external cash flows",
        "gross_pnl": "net_pnl + canonical fee_breakdown.total_cost",
        "total_return": "net_pnl / initial_capital",
        "maximum_drawdown": "minimum end-equity drawdown from prior peak over evaluated sessions",
        "turnover": "sum filled gross_value / initial_capital",
        "fill_rate": "filled or partial-filled order count / order intent count",
        "no_trade_session_rate": "sessions with no fills / trading_session_count",
    }


def _category_count(no_trade: Mapping[str, Any], category: str) -> int:
    return int(dict(dict(no_trade.get("by_category", {})).get(category, {}) or {}).get("count", 0))


def _relative(base: Path, path: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.name


def _capital_label(capital: float) -> str:
    return str(int(capital)) if float(capital).is_integer() else str(capital).replace(".", "_")


def _json_ready(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _json_ready(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (tuple, list, set, frozenset)):
        return tuple(_json_ready(item) for item in value)
    if isinstance(value, (date,)):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    try:
        canonical_json(value)
        return value
    except TypeError:
        return str(value)
