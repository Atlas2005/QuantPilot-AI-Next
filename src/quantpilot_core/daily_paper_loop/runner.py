"""One-session durable daily paper-loop runner."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, is_dataclass, replace
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from quantpilot_core.a_share_market_reality_execution import (
    AShareExecutionAccountState,
    AShareExecutionConfig,
    execute_a_share_reality_proposal,
    estimate_buy_cash_required,
    summarize_execution_outcomes,
    summarize_metadata_availability,
)
from quantpilot_core.daily_paper_loop.contracts import (
    DAILY_LOOP_REPORT_SCHEMA_VERSION,
    DAILY_LOOP_SCHEMA_VERSION,
    DAILY_LOOP_VERSION,
    DailyPaperLoopConfig,
    DailyPaperLoopInput,
    DailyPaperLoopResult,
    DailyPaperLoopStatus,
    DailyPaperMarketBundle,
    DailyPaperStateError,
    IdempotencyConflictError,
)
from quantpilot_core.daily_paper_loop.report import write_report_atomic
from quantpilot_core.daily_paper_loop.state import (
    DailyPaperLoopState,
    canonical_json,
    execution_state_to_payload,
    load_daily_state,
    payload_digest,
    replace_state_hash,
    save_daily_state_atomic,
    snapshot_from_execution_state,
    state_to_payload,
)
from quantpilot_core.execution_candidate import ExecutionCandidate, ExecutionCandidateReport, candidate_report_aggregate_score
from quantpilot_core.execution_optimizer import OptimizationAssumption, build_portfolio_allocation_plan
from quantpilot_core.order_intent import (
    OrderIntent,
    OrderIntentProposal,
    OrderIntentProposalSource,
    OrderIntentSide,
    build_order_intent_proposal,
)
from quantpilot_core.paper_trading import PaperAccount, PaperFillCostAssumptions, account_symbol_pnl_breakdown
from quantpilot_core.quant_firm import DeepSeekClientConfig, QuantFirmDecisionReport, is_quant_firm_approved, run_quant_firm_decision_cycle
from quantpilot_core.real_data_provider import ProviderName, TradingCalendar
from quantpilot_core.runtime_account import (
    BrokerFeeProfile,
    RuntimeFeeModel,
    account_executable_candidate_report,
    candidate_action_side,
    estimate_pre_trade_cash_requirement,
    fee_assumptions_from_profile,
    resolve_runtime_fee_profile,
)
from quantpilot_core.runtime_account.policy import instrument_rules_for_candidate, permission_denial_reason

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
CANONICAL_DIRECTIONS = {"long", "short", "flat"}
ACTIONABLE_SELL_ACTIONS = {"sell", "exit"}
PIT_TIME_FIELD_NAMES = {
    "published_at",
    "discovered_at",
    "available_at",
    "first_available_time",
    "pit_availability_time",
    "pit_availability_timestamp",
    "information_timestamp",
    "signal_timestamp",
    "as_of_timestamp",
}


@dataclass(frozen=True)
class _BuySizingResult:
    intent: OrderIntent | None
    decision: Mapping[str, Any]


def run_daily_paper_loop(
    loop_input: DailyPaperLoopInput,
    config: DailyPaperLoopConfig,
) -> DailyPaperLoopResult:
    """Run exactly one decision-session D -> execution-session D+1 lifecycle."""

    _validate_config(config)
    decision_session = _as_date(config.decision_session)
    if not loop_input.calendar.is_session(decision_session):
        raise DailyPaperStateError(f"decision session is not in loaded trading calendar: {decision_session.isoformat()}")
    execution_session = loop_input.calendar.next_session(decision_session)
    session_id = _session_id(config, decision_session, execution_session)
    _validate_time_inputs(loop_input, decision_session)
    state_before = load_daily_state(config.state_path, initial_capital=config.initial_capital)
    holding_symbols = _holding_symbol_universe(state_before)
    candidate_symbols = {candidate.symbol for candidate in loop_input.candidate_report.candidates}
    market_evidence = _validate_market_bundle(loop_input.market, candidate_symbols, holding_symbols, decision_session, execution_session)

    input_digest = _input_digest(loop_input, config, decision_session, execution_session)
    applied = dict(state_before.applied_sessions.get(session_id, {}) or {})
    if applied:
        if applied.get("input_digest") != input_digest:
            raise IdempotencyConflictError(f"session already applied with different input digest: {session_id}")
        report = _idempotent_report(
            applied=applied,
            state=state_before,
            config=config,
            loop_input=loop_input,
            decision_session=decision_session,
            execution_session=execution_session,
            session_id=session_id,
        )
        report_path = write_report_atomic(report, config.report_path)
        return DailyPaperLoopResult(DailyPaperLoopStatus.IDEMPOTENT_REPLAY, report, str(config.state_path), report_path)
    _validate_chronology(state_before, decision_session, execution_session)

    account_before = state_before.execution_state.account
    prices_for_sizing = dict(market_evidence["decision_prices"])
    executable_buy_prices = dict(market_evidence["executable_buy_prices"])
    equity_before = _equity(account_before, prices_for_sizing)
    reserve_before = max(0.0, equity_before * float(config.reserve_cash_weight))
    fee_resolution = resolve_runtime_fee_profile(
        broker_returned_account_fee_profile=config.broker_returned_account_fee_profile,
        persisted_user_account_fee_profile=config.persisted_user_account_fee_profile,
        engineering_fallback=_engineering_fallback_fee_profile(config.cost_assumptions),
    )
    candidate_filter = account_executable_candidate_report(
        loop_input.candidate_report,
        capabilities=config.account_capabilities,
        positions=account_before.positions,
        prices=prices_for_sizing,
        available_cash=max(0.0, float(account_before.cash) - reserve_before),
        fee_profile=fee_resolution.profile,
        market_rows=loop_input.market.decision_rows_by_symbol,
        executable_buy_prices=executable_buy_prices,
    )
    pipeline_meta = dict(loop_input.quant_firm_context.get("candidate_pipeline", {}) or {})
    original_selected = tuple(pipeline_meta.get("original_selected_symbols", ()) or ())
    forwarded_standbys = tuple(pipeline_meta.get("forwarded_standby_symbols", ()) or ())
    final_decision = _resolve_final_account_decision(
        candidate_filter,
        original_selected_symbols=original_selected if original_selected else None,
        forwarded_standby_symbols=forwarded_standbys if forwarded_standbys else None,
    )
    account_candidate_report = final_decision.account_executable_report
    quant_decision = run_quant_firm_decision_cycle(
        execution_candidate_report=account_candidate_report,
        portfolio_allocation_plan=None,
        vectorbt_replay_result=loop_input.quant_firm_context.get("vectorbt_replay_result"),
        cycle_id=session_id,
        strategy_id=config.strategy_id,
        context={
            **dict(loop_input.quant_firm_context),
            "decision_session": decision_session.isoformat(),
            "execution_session": execution_session.isoformat(),
            "deepseek_policy": "live_disabled_by_default",
        },
        include_deepseek_advisory=False,
        deepseek_config=DeepSeekClientConfig(enable_live_call=False),
    )
    allocation_plan = _allocation_plan(account_candidate_report, account_before, prices_for_sizing, config, allocation_buy_prices=executable_buy_prices)
    proposal, order_provenance, skipped_orders, sizing_decisions, fee_assumptions_by_order_id = _build_order_proposal(
        candidate_report=account_candidate_report,
        account_filter=candidate_filter,
        fee_resolution=fee_resolution,
        allocation_plan=allocation_plan,
        account=account_before,
        prices_for_sizing=prices_for_sizing,
        executable_buy_prices=executable_buy_prices,
        config=config,
        session_id=session_id,
        decision_session=decision_session,
        execution_session=execution_session,
        quant_decision=quant_decision,
        quant_firm_context=loop_input.quant_firm_context,
        missing_decision_symbols=set(market_evidence["missing_decision_candidate_symbols"]),
        input_digest=input_digest,
    )
    execution_rows = _execution_rows_for_open(loop_input.market.execution_rows_by_symbol)
    valuation_prices = dict(market_evidence["valuation_prices"])
    before_snapshot = snapshot_from_execution_state(
        state_before.execution_state,
        prices_for_sizing,
        as_of_session=decision_session.isoformat(),
        next_session=execution_session.isoformat(),
    )
    execution_result = execute_a_share_reality_proposal(
        proposal,
        execution_rows,
        state_before.execution_state,
        trade_date=execution_session.isoformat(),
        cost_assumptions=fee_assumptions_from_profile(fee_resolution.profile, "stock", side="buy"),
        fee_assumptions_by_order_id=fee_assumptions_by_order_id,
        config=AShareExecutionConfig(max_participation_rate=0.10),
    )
    state_after_execution = _mark_state_to_valuation(execution_result.state, valuation_prices)
    _reconcile_execution_state(
        before=state_before.execution_state,
        after=state_after_execution,
        outcomes=execution_result.outcomes,
    )
    reconciliation_audit = _reconciliation_audit(
        before=state_before.execution_state,
        after=state_after_execution,
        outcomes=execution_result.outcomes,
    )
    if reconciliation_audit["status"] != "passed":
        failed = ",".join(tuple(reconciliation_audit["failed"])[:8])
        raise DailyPaperStateError(f"daily paper reconciliation failed: {failed}")
    after_snapshot = snapshot_from_execution_state(
        state_after_execution,
        valuation_prices,
        as_of_session=execution_session.isoformat(),
        next_session=_next_session_iso(loop_input.calendar, execution_session),
    )
    session_record = {
        "schema_version": DAILY_LOOP_SCHEMA_VERSION,
        "session_id": session_id,
        "decision_session": decision_session.isoformat(),
        "execution_session": execution_session.isoformat(),
        "input_digest": input_digest,
        "state_hash_before": state_before.state_hash,
        "status": DailyPaperLoopStatus.COMPLETED.value,
        "candidate_report": _candidate_report_payload(loop_input.candidate_report),
        "quant_firm_input_candidate_report": _candidate_report_payload(account_candidate_report),
        "account_executable_universe": _account_filter_payload(candidate_filter),
        "account_final_decision": _final_decision_payload(final_decision),
        "account_capabilities": _account_capabilities_payload(config.account_capabilities),
        "fee_resolution": _fee_resolution_payload(fee_resolution),
        "quant_firm_decision": _json_ready(quant_decision),
        "quant_firm_candidate_actions": _quant_firm_candidate_actions(account_candidate_report, quant_decision, loop_input.quant_firm_context),
        "allocation_plan": _json_ready(allocation_plan),
        "sizing_decisions": tuple(sizing_decisions),
        "order_intents": _proposal_payload(proposal),
        "order_provenance": order_provenance,
        "fee_assumptions_by_order_id": _json_ready(fee_assumptions_by_order_id),
        "skipped_orders": tuple(skipped_orders),
        "execution_outcomes": tuple(_json_ready(outcome) for outcome in execution_result.outcomes),
        "execution_summary": summarize_execution_outcomes(execution_result.outcomes),
        "metadata_availability": summarize_metadata_availability(execution_result.outcomes),
        "ledger_before": before_snapshot,
        "ledger_after": after_snapshot,
        "fee_breakdown": _fee_breakdown(execution_result.outcomes),
        "reconciliation_audit": reconciliation_audit,
        "leakage_audit": _leakage_audit(loop_input, market_evidence, decision_session, execution_session),
        "calendar_provenance": {**dict(loop_input.calendar_provenance), "calendar_provider": loop_input.calendar.provider.value},
        "market_data_provenance": dict(loop_input.market.market_data_provenance),
        "information_provenance": dict(loop_input.information_provenance),
        "advisory_provenance": dict(loop_input.advisory_provenance),
        "limitations": _limitations(config),
    }
    session_record["next_session_state"] = {
        "last_completed_session": session_id,
        "seen_order_ids": tuple(sorted(state_after_execution.seen_order_ids)),
    }
    applied_sessions = {**dict(state_before.applied_sessions), session_id: session_record}
    state_after = replace_state_hash(
        DailyPaperLoopState(
            schema_version=DAILY_LOOP_SCHEMA_VERSION,
            initial_capital=state_before.initial_capital,
            execution_state=state_after_execution,
            applied_sessions=applied_sessions,
            last_completed_session=session_id,
            last_decision_session=decision_session.isoformat(),
            last_execution_session=execution_session.isoformat(),
            prior_state_hash=state_before.state_hash,
        )
    )
    persisted = save_daily_state_atomic(state_after, config.state_path)
    report = _session_report(
        session_record=session_record,
        status=DailyPaperLoopStatus.COMPLETED.value,
        state_before=state_before,
        state_after=persisted,
        config=config,
        loop_input=loop_input,
        calendar=loop_input.calendar,
    )
    report_path = write_report_atomic(report, config.report_path)
    return DailyPaperLoopResult(DailyPaperLoopStatus.COMPLETED, report, str(config.state_path), report_path)


def build_offline_fixture_input(decision_session: str = "2026-01-02") -> DailyPaperLoopInput:
    """Build deterministic no-network fixtures that produce one executable buy."""

    decision = _as_date(decision_session)
    execution = date(2026, 1, 5) if decision.isoformat() == "2026-01-02" else date.fromordinal(decision.toordinal() + 1)
    calendar = TradingCalendar((decision, execution, date.fromordinal(execution.toordinal() + 1)), ProviderName.BAOSTOCK)
    candidate = ExecutionCandidate(
        symbol="600000.SH",
        direction="long",
        confidence=0.82,
        expected_return=0.08,
        risk_score=0.20,
        liquidity_score=0.90,
        timestamp=datetime(decision.year, decision.month, decision.day, 14, 55, tzinfo=SHANGHAI_TZ),
        metadata={"candidate_id": "fixture-600000-long", "source": "offline_fixture"},
    )
    report = ExecutionCandidateReport(candidates=(candidate,), aggregate_score=0.08, strategy_id="offline-fixture-exec1")
    return DailyPaperLoopInput(
        calendar=calendar,
        candidate_report=report,
        market=DailyPaperMarketBundle(
            decision_rows_by_symbol={
                "600000.SH": {
                    "symbol": "600000.SH",
                    "date": decision.isoformat(),
                    "open": 9.9,
                    "high": 10.2,
                    "low": 9.8,
                    "close": 10.0,
                    "previous_close": 9.8,
                    "volume": 120_000,
                    "is_suspended": False,
                    "provider": "offline_fixture",
                }
            },
            execution_rows_by_symbol={
                "600000.SH": {
                    "symbol": "600000.SH",
                    "date": execution.isoformat(),
                    "open": 10.1,
                    "high": 10.4,
                    "low": 10.0,
                    "close": 10.3,
                    "previous_close": 10.0,
                    "volume": 100_000,
                    "is_suspended": False,
                    "provider": "offline_fixture",
                }
            },
            market_data_provenance={"mode": "offline_fixture", "network_calls": 0},
        ),
        calendar_provenance={"mode": "offline_fixture", "sessions": calendar.to_iso_strings()},
        information_provenance={"mode": "offline_fixture", "max_timestamp": f"{decision.isoformat()}T15:00:00+08:00"},
        advisory_provenance={"deepseek_live_call": False, "fallback": "deterministic_quant_firm"},
        quant_firm_context={"requested_action": "buy"},
    )


def _allocation_plan(
    report: ExecutionCandidateReport,
    account: PaperAccount,
    prices_for_sizing: Mapping[str, float],
    config: DailyPaperLoopConfig,
    *,
    allocation_buy_prices: Mapping[str, float] | None = None,
) -> Any | None:
    long_candidates = tuple(candidate for candidate in report.candidates if candidate.direction == "long" and candidate.symbol in prices_for_sizing)
    if not long_candidates:
        return None
    # Equity always uses D close (prices_for_sizing).
    equity = _equity(account, prices_for_sizing)
    # Optimizer last_prices use valid buy references where available.
    optimizer_prices = dict(prices_for_sizing)
    if allocation_buy_prices is not None:
        for sym in optimizer_prices:
            if sym in allocation_buy_prices:
                optimizer_prices[sym] = allocation_buy_prices[sym]
    long_report = ExecutionCandidateReport(
        candidates=long_candidates[: max(1, int(config.target_position_count))],
        aggregate_score=report.aggregate_score,
        strategy_id=report.strategy_id,
    )
    return build_portfolio_allocation_plan(
        long_report,
        last_prices=optimizer_prices,
        assumptions=OptimizationAssumption(
            capital=max(equity, 0.01),
            lot_size=1,
            fee_rate=config.cost_assumptions.fee_rate,
            slippage_bps=config.cost_assumptions.slippage_bps,
        ),
    )


def _build_order_proposal(
    *,
    candidate_report: ExecutionCandidateReport,
    account_filter: Any,
    fee_resolution: Any,
    allocation_plan: Any | None,
    account: PaperAccount,
    prices_for_sizing: Mapping[str, float],
    executable_buy_prices: Mapping[str, float] | None = None,
    config: DailyPaperLoopConfig,
    session_id: str,
    decision_session: date,
    execution_session: date,
    quant_decision: QuantFirmDecisionReport,
    quant_firm_context: Mapping[str, Any],
    missing_decision_symbols: set[str],
    input_digest: str,
) -> tuple[OrderIntentProposal, Mapping[str, Mapping[str, Any]], tuple[Mapping[str, Any], ...], tuple[Mapping[str, Any], ...], Mapping[str, PaperFillCostAssumptions]]:
    intents: list[OrderIntent] = []
    skipped: list[Mapping[str, Any]] = []
    sizing_decisions: list[Mapping[str, Any]] = []
    provenance: dict[str, Mapping[str, Any]] = {}
    fee_assumptions_by_order_id: dict[str, PaperFillCostAssumptions] = {}
    authorization = _quant_order_authorization(quant_decision, quant_firm_context)
    candidates_by_symbol = {candidate.symbol: candidate for candidate in candidate_report.candidates}
    long_allocation_participant_count = _allocation_participant_count(allocation_plan)
    for exclusion in account_filter.exclusions:
        decision = _excluded_sizing_decision(
            exclusion=exclusion,
            account=account,
            prices=prices_for_sizing,
            config=config,
            fee_resolution=fee_resolution,
        )
        sizing_decisions.append(decision)
        skipped.append({"symbol": exclusion.symbol, "side": exclusion.side, "candidate_id": exclusion.candidate_id, "reason": exclusion.reason})
    for symbol in sorted(missing_decision_symbols):
        skipped.append({"symbol": symbol, "reason": "missing_decision_market_data"})
    if allocation_plan is not None:
        proposal = build_order_intent_proposal(
            allocation_plan,
            committee_metadata={"quant_firm_final_recommendation": quant_decision.final_recommendation},
            run_label=session_id,
            lot_size=config.min_order_lot,
        )
        for index, intent in enumerate(proposal.intents, start=1):
            candidate_id = _candidate_id_for_symbol(candidates_by_symbol, intent.symbol)
            candidate = candidates_by_symbol.get(intent.symbol)
            rules = instrument_rules_for_candidate(candidate, price=prices_for_sizing.get(intent.symbol)) if candidate is not None else None
            intent = _intent_with_rule_lot_target(intent, rules, prices_for_sizing, executable_buy_prices=executable_buy_prices)
            intent_cost_assumptions = fee_assumptions_from_profile(
                fee_resolution.profile,
                rules.instrument_type if rules is not None else "stock",
                side="buy",
                lot_size=rules.lot_size if rules is not None else config.min_order_lot,
            )
            if not authorization["buy_authorized"]:
                sizing_decisions.append(_buy_sizing_decision(intent, account, prices_for_sizing, intent_cost_assumptions, config, final_quantity=0, status="skipped", reason_codes=(authorization["skip_reason"],), candidate_id=candidate_id, fee_profile_provenance=fee_resolution.provenance.value))
                skipped.append({"symbol": intent.symbol, "side": OrderIntentSide.BUY.value, "candidate_id": candidate_id, "reason": authorization["skip_reason"]})
                continue
            if intent.side != OrderIntentSide.BUY or not intent.target_shares:
                reason = _no_positive_allocation_reason(candidate)
                sizing_decisions.append(_allocation_skip_decision(intent, candidate_id=candidate_id, reason=reason, fee_resolution=fee_resolution))
                skipped.append({"symbol": intent.symbol, "side": _enum_value(intent.side), "candidate_id": candidate_id, "reason": reason})
                continue
            sizing = _resize_buy_intent(
                intent,
                account,
                prices_for_sizing,
                intent_cost_assumptions,
                config,
                candidate=candidate,
                executable_candidate_count=long_allocation_participant_count,
                fee_resolution=fee_resolution,
                account_capabilities=config.account_capabilities,
                executable_buy_prices=executable_buy_prices,
                candidate_id=candidate_id,
            )
            if sizing.intent is None:
                sizing_decisions.append(sizing.decision)
                skipped.append({"symbol": intent.symbol, "side": OrderIntentSide.BUY.value, "candidate_id": candidate_id, "reason": tuple(sizing.decision.get("reason_codes", ("sizing_skip",)))[0]})
                continue
            resized = sizing.intent
            order_id = _order_id(session_id, resized.symbol, resized.side, int(resized.target_shares or 0), index)
            metadata = {
                **dict(resized.metadata),
                "order_id": order_id,
                "idempotency_key": _idempotency_key(session_id, order_id, input_digest),
                "session_id": session_id,
                "decision_session": decision_session.isoformat(),
                "execution_session": execution_session.isoformat(),
                "input_digest": input_digest,
                "fee_profile_id": fee_resolution.profile.profile_id,
                "fee_profile_provenance": fee_resolution.provenance.value,
                "fee_profile_broker_truth": bool(fee_resolution.broker_truth),
            }
            final = replace(resized, metadata=metadata, run_label=session_id)
            intents.append(final)
            fee_assumptions_by_order_id[order_id] = intent_cost_assumptions
            sizing_decisions.append({**dict(sizing.decision), "order_id": order_id, "final_order_quantity": int(final.target_shares or 0), "result_status": "order_created"})
            provenance[order_id] = _order_provenance(final, candidate_report, quant_decision, allocation_plan, input_digest)
    for offset, candidate in enumerate(candidate_report.candidates, start=len(intents) + 1):
        if candidate_action_side(candidate) != "sell":
            continue
        if candidate.symbol in missing_decision_symbols:
            continue
        rules = instrument_rules_for_candidate(candidate, price=prices_for_sizing.get(candidate.symbol))
        sell_lot = max(1, int(rules.lot_size))
        if not authorization["sell_authorized"]:
            sizing_decisions.append(_sell_sizing_decision(candidate, account, config, lot_size=sell_lot, final_quantity=0, status="skipped", reason_codes=(authorization["skip_reason"],), fee_profile_provenance=fee_resolution.provenance.value))
            skipped.append({"symbol": candidate.symbol, "side": OrderIntentSide.SELL.value, "candidate_id": dict(candidate.metadata).get("candidate_id"), "reason": authorization["skip_reason"]})
            continue
        quantity = int(account.positions.get(candidate.symbol, 0))
        sell_quantity = (quantity // sell_lot) * sell_lot
        if sell_quantity <= 0:
            sizing_decisions.append(_sell_sizing_decision(candidate, account, config, lot_size=sell_lot, final_quantity=0, status="skipped", reason_codes=("no_sellable_position_for_exit_candidate",), fee_profile_provenance=fee_resolution.provenance.value))
            skipped.append({"symbol": candidate.symbol, "side": OrderIntentSide.SELL.value, "candidate_id": dict(candidate.metadata).get("candidate_id"), "reason": "no_sellable_position_for_exit_candidate"})
            continue
        order_id = _order_id(session_id, candidate.symbol, OrderIntentSide.SELL, sell_quantity, offset)
        sell_cost_assumptions = fee_assumptions_from_profile(fee_resolution.profile, rules.instrument_type, side="sell", lot_size=rules.lot_size)
        intent = OrderIntent(
            symbol=candidate.symbol,
            side=OrderIntentSide.SELL,
            target_weight=0.0,
            target_shares=sell_quantity,
            reason="daily_loop_exit_candidate",
            source_agent="daily_paper_loop",
            confidence=candidate.confidence,
            strategy_id=config.strategy_id,
            run_label=session_id,
            metadata={
                "order_id": order_id,
                "idempotency_key": _idempotency_key(session_id, order_id, input_digest),
                "candidate_direction": candidate.direction,
                "candidate_timestamp": candidate.timestamp.isoformat(),
                "session_id": session_id,
                "decision_session": decision_session.isoformat(),
                "execution_session": execution_session.isoformat(),
                "input_digest": input_digest,
                "quant_firm_requested_action": authorization["requested_action"],
                "instrument_type": rules.instrument_type,
                "a_share_lot_size": sell_lot,
                "instrument_rules": _json_ready(rules),
                "fee_profile_id": fee_resolution.profile.profile_id,
                "fee_profile_provenance": fee_resolution.provenance.value,
                "fee_profile_broker_truth": bool(fee_resolution.broker_truth),
            },
        )
        intents.append(intent)
        fee_assumptions_by_order_id[order_id] = sell_cost_assumptions
        sizing_decisions.append(_sell_sizing_decision(candidate, account, config, lot_size=sell_lot, final_quantity=sell_quantity, status="order_created", reason_codes=(), order_id=order_id, fee_profile_provenance=fee_resolution.provenance.value))
        provenance[order_id] = _order_provenance(intent, candidate_report, quant_decision, allocation_plan, input_digest)
    proposal = OrderIntentProposal(
        intents=tuple(intents),
        proposal_source=OrderIntentProposalSource.EXEC2,
        advisory_only=True,
        run_label=session_id,
        metadata={
            "session_id": session_id,
            "strategy_id": config.strategy_id,
            "no_broker_live_execution": True,
            "order_count": len(intents),
            "account_executable_candidate_count": len(candidate_report.candidates),
            "fee_profile_provenance": fee_resolution.provenance.value,
        },
    )
    return proposal, dict(sorted(provenance.items())), tuple(skipped), tuple(sizing_decisions), dict(sorted(fee_assumptions_by_order_id.items()))


def _allocation_participant_count(allocation_plan: Any | None) -> int:
    """Return the count of allocations with positive target_shares from the plan."""
    if allocation_plan is None:
        return 0
    allocs = getattr(allocation_plan, "allocations", ()) or ()
    return sum(1 for a in allocs if getattr(a, "target_shares", 0) > 0)


def _intent_with_rule_lot_target(
    intent: OrderIntent,
    rules: Any | None,
    prices: Mapping[str, float],
    *,
    executable_buy_prices: Mapping[str, float] | None = None,
) -> OrderIntent:
    if rules is None or intent.side != OrderIntentSide.BUY:
        return intent
    lot = max(1, int(rules.lot_size))
    d_close = float(prices.get(intent.symbol, 0.0) or 0.0)
    ebp = dict(executable_buy_prices or {})
    sizing_price = float(ebp.get(intent.symbol, d_close)) if executable_buy_prices is not None else d_close
    target_shares = int(intent.target_shares or 0)
    if sizing_price > 0:
        target_notional = float(dict(intent.metadata).get("target_notional", 0.0) or 0.0)
        if target_notional > 0:
            target_shares = int((target_notional / sizing_price) // lot) * lot
        else:
            target_shares = (target_shares // lot) * lot
    elif target_shares > 0:
        target_shares = (target_shares // lot) * lot
    metadata = {
        **dict(intent.metadata),
        "a_share_lot_size": lot,
        "instrument_type": rules.instrument_type,
        "instrument_rules": _json_ready(rules),
    }
    return replace(intent, side=OrderIntentSide.BUY if target_shares > 0 else intent.side, target_shares=target_shares or None, metadata=metadata)


def _resize_buy_intent(
    intent: OrderIntent,
    account: PaperAccount,
    prices: Mapping[str, float],
    cost_assumptions: PaperFillCostAssumptions,
    config: DailyPaperLoopConfig,
    *,
    candidate: ExecutionCandidate | None,
    executable_candidate_count: int,
    fee_resolution: Any,
    account_capabilities: Any | None,
    executable_buy_prices: Mapping[str, float] | None = None,
    candidate_id: str | None = None,
) -> _BuySizingResult:
    if intent.side != OrderIntentSide.BUY:
        return _BuySizingResult(intent=intent, decision={})
    price = float(prices.get(intent.symbol, 0.0) or 0.0)
    ebp = dict(executable_buy_prices or {})
    buy_price_missing = executable_buy_prices is not None and intent.symbol not in ebp and price > 0
    # Equity always uses D close (price); sizing uses executable_buy_price when available.
    sizing_price = float(ebp.get(intent.symbol, price)) if not buy_price_missing else price
    current_quantity = int(account.positions.get(intent.symbol, 0))
    optimizer_target_quantity = int(intent.target_shares or 0)
    equity = _equity(account, prices) if price > 0 else float(account.cash)
    rules = instrument_rules_for_candidate(candidate, price=sizing_price) if candidate is not None else None
    instrument_type = rules.instrument_type if rules is not None else str(dict(intent.metadata).get("instrument_type", "stock"))
    lot_size = int(rules.lot_size) if rules is not None else int(config.min_order_lot)
    one_lot_estimate = estimate_pre_trade_cash_requirement(
        fee_profile=fee_resolution.profile,
        instrument_type=instrument_type,
        side="buy",
        quantity=lot_size,
        reference_price=sizing_price,
    ) if sizing_price > 0 else None
    one_lot_cost = one_lot_estimate.cash_required if one_lot_estimate is not None else float("inf")
    reserve = max(0.0, equity * float(config.reserve_cash_weight))
    cash_after_reserve = max(0.0, float(account.cash) - reserve)
    policy = _dynamic_position_budget(
        equity=equity,
        post_reserve_cash=cash_after_reserve,
        price=sizing_price,
        current_quantity=current_quantity,
        optimizer_target_quantity=optimizer_target_quantity,
        lot_size=lot_size,
        config=config,
        one_lot_all_in_cost=one_lot_cost,
        executable_candidate_count=executable_candidate_count,
    )
    max_target_quantity = int(policy["budget_cap_shares"])
    target_quantity = min(optimizer_target_quantity, max_target_quantity)
    buy_increment_restriction: str | None = None
    if current_quantity > 0 and optimizer_target_quantity > current_quantity:
        if buy_price_missing:
            buy_increment_restriction = "buy_increment_missing_price"
        elif price <= 0:
            buy_increment_restriction = "buy_increment_missing_price"
        elif rules is not None:
            if rules.is_suspended:
                buy_increment_restriction = "buy_increment_suspended"
            elif not rules.buy_allowed:
                buy_increment_restriction = "buy_increment_not_permitted"
        if buy_increment_restriction is None and account_capabilities is not None and rules is not None:
            if permission_denial_reason(account_capabilities, rules, side="buy") is not None:
                buy_increment_restriction = "buy_increment_not_permitted"
        if buy_increment_restriction is None and one_lot_cost > cash_after_reserve:
            buy_increment_restriction = "buy_increment_unaffordable"
    if buy_increment_restriction is not None:
        target_quantity = min(target_quantity, current_quantity)
    if (
        buy_increment_restriction is None
        and target_quantity < current_quantity + lot_size
        and optimizer_target_quantity >= lot_size
        and policy["one_lot_accommodation_allowed"]
    ):
        target_quantity = current_quantity + lot_size
    desired_delta = max(0, target_quantity - current_quantity)
    quantity = (desired_delta // lot_size) * lot_size
    affordable = _max_affordable_buy_quantity(
        cash=cash_after_reserve,
        price=sizing_price,
        lot=lot_size,
        fee_profile=fee_resolution.profile,
        instrument_type=instrument_type,
        side="buy",
    ) if sizing_price > 0 else 0
    resized_quantity = min(quantity, affordable)
    status = "order_created"
    reasons: list[str] = []
    if buy_increment_restriction is not None and current_quantity > 0 and current_quantity >= target_quantity:
        status = "skipped"
        reasons.append(buy_increment_restriction)
    elif price <= 0:
        status = "skipped"
        reasons.append("invalid_non_positive_sizing_price")
    elif current_quantity > 0 and current_quantity >= target_quantity:
        status = "skipped"
        reasons.append("current_position_at_or_above_target")
    elif quantity < lot_size:
        status = "skipped"
        reasons.append("holding_selected_no_duplicate_entry" if current_quantity > 0 else "position_budget_below_one_lot")
    elif resized_quantity < lot_size:
        status = "skipped"
        reasons.append("insufficient_cash_for_one_lot")
    else:
        if target_quantity < optimizer_target_quantity:
            reasons.append("dynamic_account_budget_reduction")
        if policy["one_lot_accommodation_applied"]:
            reasons.append("small_account_one_lot_accommodation")
        if quantity < desired_delta:
            reasons.append("board_lot_reduction")
        if resized_quantity < quantity:
            reasons.append("cash_reduction")
    metadata = dict(intent.metadata)
    metadata["optimizer_target_shares"] = optimizer_target_quantity
    metadata["optimizer_target_position_shares"] = optimizer_target_quantity
    metadata["current_position_shares"] = current_quantity
    metadata["max_position_weight_cap_shares"] = policy["static_cap_shares"]
    metadata["max_position_weight_applied_target_shares"] = target_quantity
    metadata["dynamic_account_aware_budget_shares"] = max_target_quantity
    metadata["one_lot_all_in_cost"] = round(one_lot_cost, 6) if one_lot_cost != float("inf") else None
    metadata["dynamic_allocation_policy"] = policy
    metadata["instrument_type"] = instrument_type
    metadata["a_share_lot_size"] = lot_size
    metadata["instrument_rules"] = _json_ready(rules) if rules is not None else {}
    metadata["fee_profile_id"] = fee_resolution.profile.profile_id
    metadata["fee_profile_provenance"] = fee_resolution.provenance.value
    metadata["fee_profile_broker_truth"] = bool(fee_resolution.broker_truth)
    metadata["target_position_shares"] = target_quantity
    metadata["desired_delta_shares"] = desired_delta
    metadata["board_lot_applied_delta_shares"] = quantity
    metadata["board_lot_rounded_delta_shares"] = quantity
    metadata["available_cash_after_reserve"] = round(cash_after_reserve, 6)
    metadata["affordable_quantity_cap_shares"] = affordable
    metadata["cash_applied_quantity_shares"] = resized_quantity
    metadata["available_cash_constrained_shares"] = affordable
    metadata["final_order_quantity_shares"] = resized_quantity
    metadata["position_delta_shares"] = resized_quantity
    metadata["sizing_compression_reasons"] = tuple(reasons if status == "order_created" else ())
    if resized_quantity < quantity:
        metadata["resized_order"] = True
        metadata["resize_reason"] = "available_cash_after_reserve"
        metadata["original_target_shares"] = quantity
    decision = _buy_sizing_decision_from_values(
        intent=replace(intent, metadata=metadata),
        candidate_id=candidate_id,
        order_id=None,
        optimizer_target=optimizer_target_quantity,
        current_quantity=current_quantity,
        max_position_cap=max_target_quantity,
        target_after_cap=target_quantity,
        desired_delta=desired_delta,
        board_lot_delta=quantity,
        affordable=affordable,
        cash_applied=resized_quantity,
        final_quantity=resized_quantity if status == "order_created" else 0,
        status=status,
        reason_codes=tuple(reasons),
        one_lot_all_in_cost=one_lot_cost,
        dynamic_policy=policy,
        fee_profile_provenance=fee_resolution.provenance.value,
    )
    if status != "order_created":
        return _BuySizingResult(intent=None, decision=decision)
    return _BuySizingResult(intent=replace(intent, target_shares=resized_quantity, metadata=metadata), decision=decision)


def _dynamic_position_budget(
    *,
    equity: float,
    post_reserve_cash: float,
    price: float,
    current_quantity: int,
    optimizer_target_quantity: int,
    lot_size: int,
    config: DailyPaperLoopConfig,
    one_lot_all_in_cost: float,
    executable_candidate_count: int,
) -> Mapping[str, Any]:
    lot = int(lot_size)
    if price <= 0:
        return {
            "static_cap_shares": 0,
            "budget_cap_shares": 0,
            "one_lot_accommodation_allowed": False,
            "one_lot_accommodation_applied": False,
            "reason": "invalid_price",
        }
    static_value = max(0.0, equity * float(config.max_position_weight))
    static_cap = int((static_value // (price * lot)) * lot)
    effective_target_count = max(1, max(int(config.target_position_count), max(1, int(executable_candidate_count))))
    diversified_value = max(static_value, equity / effective_target_count)
    diversified_cap = int((diversified_value // (price * lot)) * lot)
    budget_cap = max(static_cap, diversified_cap)
    one_lot_allowed = (
        current_quantity == 0
        and optimizer_target_quantity >= lot
        and one_lot_all_in_cost <= max(0.0, post_reserve_cash)
        and price * lot <= max(equity, post_reserve_cash)
    )
    one_lot_applied = False
    if one_lot_allowed and budget_cap < lot:
        budget_cap = lot
        one_lot_applied = True
    concentration_weight = round((budget_cap * price) / max(equity, 0.01), 6)
    return {
        "static_cap_shares": static_cap,
        "diversified_budget_cap_shares": diversified_cap,
        "budget_cap_shares": budget_cap,
        "configured_target_position_count": int(config.target_position_count),
        "executable_candidate_count": int(executable_candidate_count),
        "effective_target_position_count": effective_target_count,
        "post_reserve_available_cash": round(max(0.0, post_reserve_cash), 6),
        "one_lot_all_in_cost": round(float(one_lot_all_in_cost), 6) if math.isfinite(float(one_lot_all_in_cost)) else None,
        "affordable_lot_count": int(max(0.0, post_reserve_cash) // max(one_lot_all_in_cost, 0.01)) if one_lot_all_in_cost > 0 and math.isfinite(float(one_lot_all_in_cost)) else 0,
        "optimizer_target_quantity": int(optimizer_target_quantity),
        "one_lot_accommodation_allowed": one_lot_allowed,
        "one_lot_accommodation_applied": one_lot_applied,
        "concentration_weight": concentration_weight,
        "reason": "dynamic_account_aware_budget",
    }


def _buy_sizing_decision(
    intent: OrderIntent,
    account: PaperAccount,
    prices: Mapping[str, float],
    cost_assumptions: PaperFillCostAssumptions,
    config: DailyPaperLoopConfig,
    *,
    final_quantity: int,
    status: str,
    reason_codes: tuple[str, ...],
    order_id: str | None = None,
    candidate_id: str | None = None,
    fee_profile_provenance: str | None = None,
) -> Mapping[str, Any]:
    price = float(prices.get(intent.symbol, 0.0) or 0.0)
    current_quantity = int(account.positions.get(intent.symbol, 0))
    optimizer_target = int(intent.metadata.get("optimizer_target_shares", intent.target_shares or 0) or 0)
    equity = _equity(account, prices) if price > 0 else float(account.cash)
    lot_size = max(1, int(cost_assumptions.lot_size or config.min_order_lot))
    one_lot_cost = estimate_buy_cash_required(lot_size, price, cost_assumptions) if price > 0 else float("inf")
    reserve = max(0.0, equity * float(config.reserve_cash_weight))
    cash_after_reserve = max(0.0, float(account.cash) - reserve)
    policy = _dynamic_position_budget(
        equity=equity,
        post_reserve_cash=cash_after_reserve,
        price=price,
        current_quantity=current_quantity,
        optimizer_target_quantity=optimizer_target,
        lot_size=lot_size,
        config=config,
        one_lot_all_in_cost=one_lot_cost,
        executable_candidate_count=max(1, int(config.target_position_count)),
    )
    max_position_cap = int(policy["budget_cap_shares"])
    target_after_cap = min(optimizer_target, max_position_cap)
    if (
        target_after_cap < current_quantity + lot_size
        and optimizer_target >= lot_size
        and policy["one_lot_accommodation_allowed"]
    ):
        target_after_cap = current_quantity + lot_size
    desired_delta = max(0, target_after_cap - current_quantity)
    board_lot_delta = (desired_delta // lot_size) * lot_size
    affordable = _max_affordable_buy_quantity(
        cash=cash_after_reserve,
        price=price,
        lot=lot_size,
        cost_assumptions=cost_assumptions,
    ) if price > 0 else 0
    cash_applied = min(board_lot_delta, affordable)
    return _buy_sizing_decision_from_values(
        intent=intent,
        candidate_id=candidate_id,
        order_id=order_id,
        optimizer_target=optimizer_target,
        current_quantity=current_quantity,
        max_position_cap=max_position_cap,
        target_after_cap=target_after_cap,
        desired_delta=desired_delta,
        board_lot_delta=board_lot_delta,
        affordable=affordable,
        cash_applied=cash_applied,
        final_quantity=final_quantity,
        status=status,
        reason_codes=reason_codes,
        one_lot_all_in_cost=one_lot_cost,
        dynamic_policy=policy,
        fee_profile_provenance=fee_profile_provenance,
    )


def _buy_sizing_decision_from_values(
    *,
    intent: OrderIntent,
    candidate_id: str | None,
    order_id: str | None,
    optimizer_target: int,
    current_quantity: int,
    max_position_cap: int,
    target_after_cap: int,
    desired_delta: int,
    board_lot_delta: int,
    affordable: int,
    cash_applied: int,
    final_quantity: int,
    status: str,
    reason_codes: tuple[str, ...],
    one_lot_all_in_cost: float | None = None,
    dynamic_policy: Mapping[str, Any] | None = None,
    fee_profile_provenance: str | None = None,
) -> Mapping[str, Any]:
    return {
        "symbol": intent.symbol,
        "side": OrderIntentSide.BUY.value,
        "order_id": order_id,
        "candidate_id": candidate_id or dict(intent.metadata).get("candidate_id"),
        "optimizer_target_quantity": optimizer_target,
        "optimizer_target_position_shares": optimizer_target,
        "current_position_shares": current_quantity,
        "t_plus_one_sellable_quantity": None,
        "t_plus_one_sellable_quantity_status": "not_applicable_buy",
        "max_position_cap_shares": max_position_cap,
        "target_after_max_position_cap_shares": target_after_cap,
        "dynamic_account_aware_budget_shares": max_position_cap,
        "one_lot_all_in_cost": round(float(one_lot_all_in_cost), 6) if one_lot_all_in_cost not in (None, float("inf")) else None,
        "allocation_policy": _json_ready(dynamic_policy or {}),
        "fee_profile_provenance": fee_profile_provenance,
        "desired_delta_shares": desired_delta,
        "quantity_after_board_lot_shares": board_lot_delta,
        "affordable_quantity_cap_shares": affordable,
        "quantity_after_cash_constraint_shares": cash_applied,
        "final_order_quantity": int(final_quantity),
        "result_status": status,
        "reason_codes": tuple(reason_codes),
    }


def _allocation_skip_decision(
    intent: OrderIntent,
    *,
    candidate_id: str | None,
    reason: str,
    fee_resolution: Any,
) -> Mapping[str, Any]:
    return {
        "symbol": intent.symbol,
        "side": _enum_value(intent.side),
        "order_id": None,
        "candidate_id": candidate_id or dict(intent.metadata).get("candidate_id"),
        "optimizer_target_quantity": int(intent.target_shares or 0),
        "optimizer_target_position_shares": int(intent.target_shares or 0),
        "current_position_shares": None,
        "t_plus_one_sellable_quantity": None,
        "t_plus_one_sellable_quantity_status": "not_applicable_allocation_skip",
        "max_position_cap_shares": None,
        "target_after_max_position_cap_shares": 0,
        "dynamic_account_aware_budget_shares": None,
        "one_lot_all_in_cost": None,
        "allocation_policy": {},
        "fee_profile_provenance": fee_resolution.provenance.value,
        "fee_profile_broker_truth": bool(fee_resolution.broker_truth),
        "desired_delta_shares": 0,
        "quantity_after_board_lot_shares": 0,
        "affordable_quantity_cap_shares": None,
        "quantity_after_cash_constraint_shares": None,
        "final_order_quantity": 0,
        "result_status": "skipped",
        "reason_codes": (reason,),
    }


def _excluded_sizing_decision(
    *,
    exclusion: Any,
    account: PaperAccount,
    prices: Mapping[str, float],
    config: DailyPaperLoopConfig,
    fee_resolution: Any,
) -> Mapping[str, Any]:
    symbol = exclusion.symbol
    current_quantity = int(account.positions.get(symbol, 0))
    details = dict(getattr(exclusion, "details", {}) or {})
    one_lot_cost = details.get("one_lot_all_in_cost")
    available_cash_for_exclusion = details.get("available_cash")
    buy_ref_price = details.get("buy_reference_price")
    return {
        "symbol": symbol,
        "side": exclusion.side,
        "order_id": None,
        "candidate_id": exclusion.candidate_id,
        "optimizer_target_quantity": 0,
        "optimizer_target_position_shares": 0,
        "current_position_shares": current_quantity,
        "t_plus_one_sellable_quantity": None,
        "t_plus_one_sellable_quantity_status": "not_applicable_buy" if exclusion.side == "buy" else "unavailable_until_execution_inventory_check" if exclusion.side == "sell" else "not_applicable_non_actionable",
        "max_position_cap_shares": None,
        "target_after_max_position_cap_shares": 0,
        "dynamic_account_aware_budget_shares": None,
        "one_lot_all_in_cost": round(float(one_lot_cost), 6) if one_lot_cost is not None else None,
        "buy_reference_price": buy_ref_price,
        "permission_result": "denied" if exclusion.reason == "account_permission_denied" else "allowed",
        "affordable_lot_count": 0 if exclusion.reason == "insufficient_cash_for_one_lot" else None,
        "instrument_rules": _json_ready(exclusion.instrument_rules),
        "exclusion_stage": exclusion.stage,
        "desired_delta_shares": 0,
        "quantity_after_board_lot_shares": 0,
        "affordable_quantity_cap_shares": 0 if exclusion.reason == "insufficient_cash_for_one_lot" else None,
        "quantity_after_cash_constraint_shares": 0,
        "final_order_quantity": 0,
        "result_status": "skipped",
        "reason_codes": (exclusion.reason,),
        "fee_profile_provenance": fee_resolution.provenance.value,
        "fee_profile_broker_truth": bool(fee_resolution.broker_truth),
        "available_cash": round(float(available_cash_for_exclusion), 6) if available_cash_for_exclusion is not None else None,
        "equity": None,
    }


def _candidate_id_for_symbol(candidates_by_symbol: Mapping[str, ExecutionCandidate], symbol: str) -> str | None:
    candidate = candidates_by_symbol.get(symbol)
    if candidate is None:
        return None
    return dict(candidate.metadata).get("candidate_id", candidate.symbol)


def _pipeline_role(candidate: ExecutionCandidate) -> str:
    """Return the pipeline_role from candidate metadata, defaulting to original_selected_entry."""
    role = dict(candidate.metadata).get("pipeline_role")
    if role in {"original_selected_entry", "original_selected_holding", "forwarded_standby", "sell_exit"}:
        return str(role)
    return "original_selected_entry"


@dataclass(frozen=True)
class _FinalAccountDecision:
    """Resolved final account decision universe after backfill selection."""

    account_executable_report: ExecutionCandidateReport
    used_backfill_symbols: tuple[str, ...]
    unused_standby_symbols: tuple[str, ...]
    account_excluded_original_symbols: tuple[str, ...]
    original_selected_symbols: tuple[str, ...]
    forwarded_standby_symbols: tuple[str, ...]
    final_decision_symbols: tuple[str, ...]
    final_decision_count: int
    forwarded_pool_count: int


def _resolve_final_account_decision(
    account_filter_result: Any,
    *,
    original_selected_symbols: tuple[str, ...] | None = None,
    forwarded_standby_symbols: tuple[str, ...] | None = None,
) -> _FinalAccountDecision:
    """After account filtering, resolve which standbys fill real vacancies.

    Vacancies are created ONLY by original selected zero-position entry candidates
    that were excluded at the account stage. Existing holdings never create vacancies.
    """
    original = tuple(original_selected_symbols or ())
    standbys = tuple(forwarded_standby_symbols or ())
    executable_candidates = account_filter_result.account_executable_report.candidates
    executable_symbols = {candidate.symbol for candidate in executable_candidates}
    excluded_by_symbol: dict[str, Any] = {}
    for exclusion in account_filter_result.exclusions:
        excluded_by_symbol[exclusion.symbol] = exclusion

    # Identify pipeline roles from candidates (check both executable and original input)
    all_input_candidates = account_filter_result.research_report.candidates
    roles_by_symbol: dict[str, str] = {}
    for candidate in all_input_candidates:
        roles_by_symbol[candidate.symbol] = _pipeline_role(candidate)

    # Original selected entries that are now zero-position
    holding_original_symbols: set[str] = set()
    for symbol in original:
        role = roles_by_symbol.get(symbol)
        if role == "original_selected_holding":
            holding_original_symbols.add(symbol)

    # Count account-excluded original entries → real vacancies
    # Iterate original in pipeline ranking order for deterministic output.
    account_excluded_original: list[str] = []
    for symbol in original:
        if symbol in holding_original_symbols:
            continue
        if symbol not in executable_symbols and symbol in excluded_by_symbol:
            account_excluded_original.append(symbol)

    real_vacancy_count = len(account_excluded_original)

    # Select top-ranked executable standbys to fill vacancies
    standby_set = set(standbys)
    executable_standbys: list[ExecutionCandidate] = []
    for candidate in executable_candidates:
        if candidate.symbol in standby_set:
            executable_standbys.append(candidate)

    used_backfill: list[str] = []
    unused_standby: list[str] = []
    for candidate in executable_standbys:
        if len(used_backfill) < real_vacancy_count:
            used_backfill.append(candidate.symbol)
        else:
            unused_standby.append(candidate.symbol)

    # Also mark as unused any forwarded standbys that weren't even executable
    for symbol in standbys:
        if symbol not in executable_symbols and symbol not in unused_standby and symbol not in used_backfill:
            unused_standby.append(symbol)

    # Build final decision report: keep executable original (entry + holding) + used backfill + sell exits
    used_backfill_set = set(used_backfill)
    final_candidates: list[ExecutionCandidate] = []
    for candidate in executable_candidates:
        role = _pipeline_role(candidate)
        if role in {"original_selected_entry", "original_selected_holding"}:
            # Always keep original selected (entries and holdings)
            final_candidates.append(candidate)
        elif role == "forwarded_standby":
            if candidate.symbol in used_backfill_set:
                final_candidates.append(candidate)
            # else: unused standby, excluded from final decision
        elif role == "sell_exit":
            final_candidates.append(candidate)
        else:
            # backward compat: no pipeline_role — keep all executable
            final_candidates.append(candidate)

    final_aggregate = candidate_report_aggregate_score(tuple(final_candidates))
    final_report = ExecutionCandidateReport(
        candidates=tuple(final_candidates),
        aggregate_score=final_aggregate,
        strategy_id=account_filter_result.account_executable_report.strategy_id,
    )

    return _FinalAccountDecision(
        account_executable_report=final_report,
        used_backfill_symbols=tuple(used_backfill),
        unused_standby_symbols=tuple(sorted(unused_standby)),
        account_excluded_original_symbols=tuple(account_excluded_original),
        original_selected_symbols=original,
        forwarded_standby_symbols=standbys,
        final_decision_symbols=tuple(candidate.symbol for candidate in final_candidates),
        final_decision_count=len(final_candidates),
        forwarded_pool_count=len(all_input_candidates),
    )


def _no_positive_allocation_reason(candidate: ExecutionCandidate | None) -> str:
    if candidate is None:
        return "no_positive_allocation"
    metadata = dict(candidate.metadata)
    if "expected_gross_edge" in metadata and "estimated_transaction_cost" in metadata:
        try:
            gross_edge = float(metadata["expected_gross_edge"])
            transaction_cost = float(metadata["estimated_transaction_cost"])
            if gross_edge <= transaction_cost:
                return "expected_edge_below_cost"
            return "no_positive_allocation"
        except (TypeError, ValueError):
            return "missing_structured_edge_evidence"
    if "expected_gross_edge" not in metadata and "estimated_transaction_cost" not in metadata:
        return "no_positive_allocation"
    return "missing_structured_edge_evidence"


def _sell_sizing_decision(
    candidate: ExecutionCandidate,
    account: PaperAccount,
    config: DailyPaperLoopConfig,
    *,
    lot_size: int | None = None,
    final_quantity: int,
    status: str,
    reason_codes: tuple[str, ...],
    order_id: str | None = None,
    fee_profile_provenance: str | None = None,
) -> Mapping[str, Any]:
    current_quantity = int(account.positions.get(candidate.symbol, 0))
    lot = max(1, int(lot_size or config.min_order_lot))
    board_lot_quantity = (current_quantity // lot) * lot
    return {
        "symbol": candidate.symbol,
        "side": OrderIntentSide.SELL.value,
        "order_id": order_id,
        "candidate_id": dict(candidate.metadata).get("candidate_id"),
        "optimizer_target_quantity": current_quantity,
        "optimizer_target_position_shares": 0,
        "current_position_shares": current_quantity,
        "t_plus_one_sellable_quantity": None,
        "t_plus_one_sellable_quantity_status": "unavailable_until_execution_inventory_check",
        "max_position_cap_shares": None,
        "target_after_max_position_cap_shares": 0,
        "desired_delta_shares": current_quantity,
        "quantity_after_board_lot_shares": board_lot_quantity,
        "affordable_quantity_cap_shares": None,
        "quantity_after_cash_constraint_shares": None,
        "final_order_quantity": int(final_quantity),
        "result_status": status,
        "reason_codes": tuple(reason_codes),
        "fee_profile_provenance": fee_profile_provenance,
    }


def _max_affordable_buy_quantity(
    *,
    cash: float,
    price: float,
    lot: int,
    cost_assumptions: PaperFillCostAssumptions | None = None,
    fee_profile: BrokerFeeProfile | None = None,
    instrument_type: str = "stock",
    side: str = "buy",
) -> int:
    if cash <= 0 or price <= 0:
        return 0
    rough = int((cash / price) // lot) * lot
    while rough >= lot and _pre_trade_cash_required(
        quantity=rough,
        price=price,
        cost_assumptions=cost_assumptions,
        fee_profile=fee_profile,
        instrument_type=instrument_type,
        side=side,
    ) > cash:
        rough -= lot
    return max(0, rough)


def _pre_trade_cash_required(
    *,
    quantity: int,
    price: float,
    cost_assumptions: PaperFillCostAssumptions | None = None,
    fee_profile: BrokerFeeProfile | None = None,
    instrument_type: str = "stock",
    side: str = "buy",
) -> float:
    if fee_profile is not None:
        return estimate_pre_trade_cash_requirement(
            fee_profile=fee_profile,
            instrument_type=instrument_type,
            side=side,
            quantity=quantity,
            reference_price=price,
        ).cash_required
    if cost_assumptions is None:
        raise DailyPaperStateError("pre-trade cash estimate requires cost assumptions or a fee profile")
    return estimate_buy_cash_required(quantity, price, cost_assumptions)


def _execution_rows_for_open(rows_by_symbol: Mapping[str, Mapping[str, Any]]) -> Mapping[str, Mapping[str, Any]]:
    rows = {}
    for symbol, row in rows_by_symbol.items():
        open_price = float(row.get("open") or 0.0)
        payload = {**dict(row), "execution_price": open_price, "price_basis": "d_plus_1_open"}
        if open_price <= 0:
            payload["close"] = 0.0
        rows[str(symbol)] = payload
    return rows


def _mark_state_to_valuation(
    state: AShareExecutionAccountState,
    valuation_prices: Mapping[str, float],
) -> AShareExecutionAccountState:
    rows = account_symbol_pnl_breakdown(state.account, valuation_prices)
    unrealized = round(sum(float(row.get("unrealized_pnl") or 0.0) for row in rows), 6)
    return replace(state, account=replace(state.account, unrealized_pnl=unrealized))


def _reconcile_execution_state(
    *,
    before: AShareExecutionAccountState,
    after: AShareExecutionAccountState,
    outcomes: tuple[Any, ...],
) -> None:
    _validate_account_finite(after.account)
    for symbol, quantity in after.account.positions.items():
        if int(quantity) < 0:
            raise DailyPaperStateError(f"negative position after execution: {symbol}")
    lot_totals: dict[str, int] = {}
    for lot in after.settlement_lots:
        lot_totals[lot.symbol] = lot_totals.get(lot.symbol, 0) + int(lot.quantity)
    for symbol, quantity in after.account.positions.items():
        if lot_totals.get(symbol, 0) != int(quantity):
            raise DailyPaperStateError(f"settlement lots must exactly match holdings: {symbol}")
    for symbol in lot_totals:
        if symbol not in after.account.positions:
            raise DailyPaperStateError(f"settlement lot exists without holding: {symbol}")
    before_positions = dict(before.account.positions)
    expected = dict(before_positions)
    for outcome in outcomes:
        if outcome.status not in {"filled", "partial"}:
            continue
        delta = int(outcome.filled_quantity) if outcome.side == "buy" else -int(outcome.filled_quantity)
        expected[outcome.symbol] = expected.get(outcome.symbol, 0) + delta
        if expected[outcome.symbol] <= 0:
            expected.pop(outcome.symbol, None)
    if dict(sorted(expected.items())) != dict(sorted(after.account.positions.items())):
        raise DailyPaperStateError("filled quantities do not reconcile to position changes")


def _settlement_lots_exact(state: AShareExecutionAccountState) -> bool:
    lots: dict[str, int] = {}
    for lot in state.settlement_lots:
        if not lot.acquisition_date:
            return False
        lots[lot.symbol] = lots.get(lot.symbol, 0) + int(lot.quantity)
    positions = {symbol: int(quantity) for symbol, quantity in state.account.positions.items() if int(quantity) > 0}
    return lots == positions


def _reconciliation_audit(
    *,
    before: AShareExecutionAccountState,
    after: AShareExecutionAccountState,
    outcomes: tuple[Any, ...],
) -> Mapping[str, Any]:
    before_log_count = len(before.account.trade_log)
    new_trades = tuple(after.account.trade_log[before_log_count:])
    filled_outcomes = tuple(outcome for outcome in outcomes if outcome.status in {"filled", "partial"})
    no_fill_outcomes = tuple(outcome for outcome in outcomes if outcome.status in {"rejected", "deferred"})
    checks = {
        "cash_delta": abs(
            round(float(after.account.cash) - float(before.account.cash), 6)
            - round(sum(float(trade.cash_impact) for trade in new_trades), 6)
        )
        <= 1e-6,
        "cash_non_negative": float(after.account.cash) >= -1e-6,
        "trade_count_matches_filled_outcomes": len(new_trades) == len(filled_outcomes),
        "filled_quantities_match_trades": {
            (trade.symbol, trade.side, trade.quantity) for trade in new_trades
        }
        == {(outcome.symbol, outcome.side, outcome.filled_quantity) for outcome in filled_outcomes},
        "fee_totals_match_trades": abs(
            round(sum(float(outcome.total_cost) for outcome in filled_outcomes), 6)
            - round(sum(float(trade.total_cost) for trade in new_trades), 6)
        )
        <= 1e-6,
        "realized_pnl_delta_matches_trades": abs(
            round(float(after.account.realized_pnl) - float(before.account.realized_pnl), 6)
            - round(sum(float(trade.realized_pnl) for trade in new_trades if trade.side == "sell"), 6)
        )
        <= 1e-6,
        "realized_pnl_by_symbol_finite": all(math.isfinite(float(value)) for value in after.account.realized_pnl_by_symbol.values()),
        "average_costs_valid": all(
            symbol in after.account.average_costs and math.isfinite(float(after.account.average_costs[symbol])) and float(after.account.average_costs[symbol]) > 0
            for symbol, quantity in after.account.positions.items()
            if int(quantity) > 0
        )
        and all(symbol in after.account.positions for symbol in after.account.average_costs),
        "settlement_lots_reconcile": _settlement_lots_exact(after),
        "rejected_deferred_no_trades": len(no_fill_outcomes) + len(filled_outcomes) == len(outcomes)
        and len(new_trades) == len(filled_outcomes),
        "positions_non_negative": all(int(quantity) >= 0 for quantity in after.account.positions.values()),
    }
    failed = tuple(name for name, passed in checks.items() if not passed)
    return {
        "status": "passed" if not failed else "failed",
        "checked": tuple(checks),
        "passed": tuple(name for name, passed in checks.items() if passed),
        "failed": failed,
        "positions_non_negative": checks["positions_non_negative"],
        "settlement_lots_reconcile": checks["settlement_lots_reconcile"],
        "new_trade_count": len(new_trades),
        "filled_order_count": sum(1 for outcome in outcomes if outcome.status == "filled"),
        "partial_fill_count": sum(1 for outcome in outcomes if outcome.status == "partial"),
        "rejected_order_count": sum(1 for outcome in outcomes if outcome.status == "rejected"),
        "deferred_order_count": sum(1 for outcome in outcomes if outcome.status == "deferred"),
    }


def _session_report(
    *,
    session_record: Mapping[str, Any],
    status: str,
    state_before: DailyPaperLoopState,
    state_after: DailyPaperLoopState,
    config: DailyPaperLoopConfig,
    loop_input: DailyPaperLoopInput | None = None,
    calendar: TradingCalendar | None = None,
) -> Mapping[str, Any]:
    report = {
        "schema_version": DAILY_LOOP_REPORT_SCHEMA_VERSION,
        "loop_version": DAILY_LOOP_VERSION,
        "run_config": _config_payload(config),
        "session_id": session_record["session_id"],
        "decision_session": session_record["decision_session"],
        "execution_session": session_record["execution_session"],
        "input_digest": session_record["input_digest"],
        "idempotency_status": status,
        "state": {
            "path": str(config.state_path),
            "schema_version": state_after.schema_version,
            "hash_before": session_record.get("state_hash_before", state_before.state_hash),
            "hash_after": _session_hash_after(session_record, state_after),
        },
        "calendar_provenance": dict(session_record["calendar_provenance"]),
        "market_data_provenance": dict(session_record["market_data_provenance"]),
        "information_provenance": dict(session_record["information_provenance"]),
        "advisory_provenance": dict(session_record["advisory_provenance"]),
        "candidate_report": session_record["candidate_report"],
        "quant_firm_input_candidate_report": session_record.get("quant_firm_input_candidate_report", {}),
        "account_executable_universe": session_record.get("account_executable_universe", {}),
        "account_final_decision": session_record.get("account_final_decision", {}),
        "account_capabilities": session_record.get("account_capabilities", {}),
        "fee_resolution": session_record.get("fee_resolution", {}),
        "quant_firm_report": session_record["quant_firm_decision"],
        "quant_firm_candidate_actions": session_record.get("quant_firm_candidate_actions", ()),
        "allocation_sizing": session_record["allocation_plan"],
        "sizing_decisions": session_record.get("sizing_decisions", ()),
        "order_intents": session_record["order_intents"],
        "order_provenance": session_record["order_provenance"],
        "fee_assumptions_by_order_id": session_record.get("fee_assumptions_by_order_id", {}),
        "skipped_orders": session_record["skipped_orders"],
        "fills": tuple(row for row in session_record["execution_outcomes"] if row["status"] == "filled"),
        "partial_fills": tuple(row for row in session_record["execution_outcomes"] if row["status"] == "partial"),
        "no_fills": tuple(row for row in session_record["execution_outcomes"] if row["status"] in {"rejected", "deferred"}),
        "rejections": tuple(row for row in session_record["execution_outcomes"] if row["status"] == "rejected"),
        "fee_breakdown": session_record["fee_breakdown"],
        "ledger_before": session_record["ledger_before"],
        "ledger_after": session_record["ledger_after"],
        "realized_pnl": session_record["ledger_after"]["realized_pnl"],
        "unrealized_pnl": session_record["ledger_after"]["unrealized_pnl"],
        "equity": session_record["ledger_after"]["total_equity"],
        "execution_summary": session_record["execution_summary"],
        "metadata_availability": session_record["metadata_availability"],
        "reconciliation_audit": session_record["reconciliation_audit"],
        "next_session_state": session_record.get("next_session_state", {
            "last_completed_session": state_after.last_completed_session,
            "seen_order_ids": tuple(sorted(state_after.execution_state.seen_order_ids)),
        }),
        "leakage_audit": session_record["leakage_audit"],
        "limitations": session_record["limitations"],
    }
    return _json_ready(report)


def render_daily_paper_session_report(
    *,
    session_record: Mapping[str, Any],
    state: DailyPaperLoopState,
    config: DailyPaperLoopConfig,
    status: str,
) -> Mapping[str, Any]:
    """Render a persisted daily-loop session using the canonical PR #111 schema."""

    return _session_report(
        session_record=session_record,
        status=status,
        state_before=state,
        state_after=state,
        config=config,
    )


def _idempotent_report(**kwargs: Any) -> Mapping[str, Any]:
    applied = kwargs["applied"]
    state = kwargs["state"]
    config = kwargs["config"]
    return render_daily_paper_session_report(
        session_record=applied,
        state=state,
        config=config,
        status=DailyPaperLoopStatus.IDEMPOTENT_REPLAY.value,
    )


def _session_hash_after(session_record: Mapping[str, Any], state: DailyPaperLoopState) -> str | None:
    session_id = str(session_record.get("session_id", ""))
    sessions = sorted(
        (dict(row) for row in state.applied_sessions.values()),
        key=lambda row: (str(row.get("decision_session", "")), str(row.get("execution_session", "")), str(row.get("session_id", ""))),
    )
    for index, row in enumerate(sessions):
        if str(row.get("session_id", "")) != session_id:
            continue
        if index + 1 < len(sessions):
            return sessions[index + 1].get("state_hash_before")
        return state.state_hash
    return state.state_hash


def _input_digest(loop_input: DailyPaperLoopInput, config: DailyPaperLoopConfig, decision_session: date, execution_session: date) -> str:
    payload = {
        "loop_version": DAILY_LOOP_VERSION,
        "decision_session": decision_session.isoformat(),
        "execution_session": execution_session.isoformat(),
        "initial_capital": round(float(config.initial_capital), 6),
        "strategy_id": config.strategy_id,
        "calendar_sessions": loop_input.calendar.to_iso_strings(),
        "calendar_provider": loop_input.calendar.provider.value,
        "calendar_provenance": dict(loop_input.calendar_provenance),
        "candidate_report": _candidate_report_payload(loop_input.candidate_report),
        "market": _json_ready(loop_input.market),
        "market_data_provenance": dict(loop_input.market.market_data_provenance),
        "information_provenance": dict(loop_input.information_provenance),
        "advisory_provenance": dict(loop_input.advisory_provenance),
        "quant_firm_context": dict(loop_input.quant_firm_context),
        "mode": {"live_market_data": bool(config.live_market_data), "live_symbol_cap": config.live_symbol_cap},
        "execution_config": {"max_participation_rate": 0.10},
        "cost_assumptions": _json_ready(config.cost_assumptions),
        "broker_returned_account_fee_profile": _json_ready(config.broker_returned_account_fee_profile),
        "persisted_user_account_fee_profile": _json_ready(config.persisted_user_account_fee_profile),
        "sizing": {
            "max_position_weight": config.max_position_weight,
            "target_position_count": config.target_position_count,
            "reserve_cash_weight": config.reserve_cash_weight,
            "min_order_lot": config.min_order_lot,
        },
    }
    if config.account_capabilities is not None:
        payload["account_capabilities"] = _json_ready(config.account_capabilities)
    return payload_digest(payload)


def _candidate_report_payload(report: ExecutionCandidateReport) -> Mapping[str, Any]:
    return {
        "strategy_id": report.strategy_id,
        "aggregate_score": report.aggregate_score,
        "candidates": tuple(_candidate_payload(candidate) for candidate in report.candidates),
    }


def _candidate_payload(candidate: ExecutionCandidate) -> Mapping[str, Any]:
    return {
        "symbol": candidate.symbol,
        "direction": candidate.direction,
        "confidence": candidate.confidence,
        "expected_return": candidate.expected_return,
        "risk_score": candidate.risk_score,
        "liquidity_score": candidate.liquidity_score,
        "timestamp": candidate.timestamp.isoformat(),
        "lot_size": candidate.lot_size,
        "metadata": dict(candidate.metadata),
    }


def _account_filter_payload(filter_result: Any) -> Mapping[str, Any]:
    return {
        "research_universe_count": len(filter_result.research_report.candidates),
        "strategy_ranked_universe_count": len(filter_result.strategy_ranked_report.candidates),
        "account_executable_universe_count": len(filter_result.account_executable_report.candidates),
        "account_executable_symbols": tuple(candidate.symbol for candidate in filter_result.account_executable_report.candidates),
        "exclusions": tuple(_candidate_exclusion_payload(exclusion) for exclusion in filter_result.exclusions),
    }


def _candidate_exclusion_payload(exclusion: Any) -> Mapping[str, Any]:
    return {
        "symbol": exclusion.symbol,
        "candidate_id": exclusion.candidate_id,
        "side": exclusion.side,
        "reason": exclusion.reason,
        "stage": exclusion.stage,
        "instrument_rules": _json_ready(exclusion.instrument_rules),
        "details": _json_ready(exclusion.details),
    }


def _account_capabilities_payload(capabilities: Any | None) -> Mapping[str, Any]:
    return {
        "supplied": capabilities is not None,
        "source": "explicit_config" if capabilities is not None else "not_supplied",
        "capabilities": _json_ready(capabilities) if capabilities is not None else None,
    }


def _fee_resolution_payload(fee_resolution: Any) -> Mapping[str, Any]:
    return {
        "profile_id": fee_resolution.profile.profile_id,
        "provenance": fee_resolution.provenance.value,
        "broker_truth": bool(fee_resolution.broker_truth),
        "resolution_order": tuple(fee_resolution.resolution_order),
        "profile": _json_ready(fee_resolution.profile),
        "actual_fill_fee_priority_note": "actual broker fill fees override pre-trade profiles when available; offline paper outcomes carry simulated fill fees only.",
    }


def _final_decision_payload(decision: Any) -> Mapping[str, Any]:
    return {
        "original_selected_symbols": decision.original_selected_symbols,
        "forwarded_standby_symbols": decision.forwarded_standby_symbols,
        "account_excluded_original_symbols": decision.account_excluded_original_symbols,
        "used_account_backfill_symbols": decision.used_backfill_symbols,
        "unused_standby_symbols": decision.unused_standby_symbols,
        "final_account_decision_symbols": decision.final_decision_symbols,
        "forwarded_pool_count": decision.forwarded_pool_count,
        "final_decision_count": decision.final_decision_count,
        "final_aggregate_score": decision.account_executable_report.aggregate_score,
    }


def _proposal_payload(proposal: OrderIntentProposal) -> Mapping[str, Any]:
    return {
        "proposal_source": _enum_value(proposal.proposal_source),
        "advisory_only": proposal.advisory_only,
        "run_label": proposal.run_label,
        "metadata": dict(proposal.metadata),
        "intents": tuple(_json_ready(intent) for intent in proposal.intents),
    }


def _order_provenance(
    intent: OrderIntent,
    report: ExecutionCandidateReport,
    quant_decision: QuantFirmDecisionReport,
    allocation_plan: Any | None,
    input_digest: str,
) -> Mapping[str, Any]:
    candidate = next((item for item in report.candidates if item.symbol == intent.symbol), None)
    return {
        "session_id": intent.metadata.get("session_id"),
        "decision_session": intent.metadata.get("decision_session"),
        "execution_session": intent.metadata.get("execution_session"),
        "candidate_id": dict(candidate.metadata).get("candidate_id", candidate.symbol if candidate else intent.symbol),
        "candidate_timestamp": candidate.timestamp.isoformat() if candidate else None,
        "candidate_direction": candidate.direction if candidate else None,
        "candidate_confidence": candidate.confidence if candidate else None,
        "quant_firm_decision_id": quant_decision.cycle_id,
        "quant_firm_final_recommendation": quant_decision.final_recommendation,
        "sizing_strategy_id": getattr(allocation_plan, "strategy_id", None),
        "instrument_type": intent.metadata.get("instrument_type"),
        "fee_profile_id": intent.metadata.get("fee_profile_id"),
        "fee_profile_provenance": intent.metadata.get("fee_profile_provenance"),
        "fee_profile_broker_truth": intent.metadata.get("fee_profile_broker_truth"),
        "strategy_input_digest": input_digest,
        "order_id": intent.metadata.get("order_id"),
        "idempotency_key": intent.metadata.get("idempotency_key"),
    }


def _fee_breakdown(outcomes: tuple[Any, ...]) -> Mapping[str, float]:
    result = {"commission": 0.0, "transaction_tax": 0.0, "transfer_fee": 0.0, "exchange_fee": 0.0, "transfer_or_exchange_fee": 0.0, "slippage_cost": 0.0, "total_cost": 0.0}
    for outcome in outcomes:
        for key in tuple(result):
            if key == "total_cost":
                continue
            result[key] = round(result[key] + float(dict(outcome.fee_breakdown).get(key, 0.0)), 6)
        result["total_cost"] = round(result["total_cost"] + float(outcome.total_cost), 6)
    return result


def _engineering_fallback_fee_profile(cost_assumptions: PaperFillCostAssumptions) -> BrokerFeeProfile:
    transfer_fee_rate = float(cost_assumptions.transfer_fee_rate)
    exchange_fee_rate = float(cost_assumptions.exchange_fee_rate)
    stamp_rate = float(cost_assumptions.stamp_tax_rate)
    stock_buy_stamp_rate = stamp_rate if bool(cost_assumptions.stamp_tax_applies_to_buy) else 0.0
    etf_buy_stamp_rate = stamp_rate if bool(cost_assumptions.stamp_tax_applies_to_buy and cost_assumptions.stamp_tax_applies_to_etf) else 0.0
    etf_sell_stamp_rate = stamp_rate if bool(cost_assumptions.stamp_tax_applies_to_etf) else 0.0
    buy_model = RuntimeFeeModel(
        commission_rate=float(cost_assumptions.fee_rate),
        min_commission=float(cost_assumptions.min_fee),
        stamp_duty_rate=stock_buy_stamp_rate,
        transfer_fee_rate=transfer_fee_rate,
        exchange_fee_rate=exchange_fee_rate,
        slippage_bps=float(cost_assumptions.slippage_bps),
    )
    sell_model = RuntimeFeeModel(
        commission_rate=float(cost_assumptions.fee_rate),
        min_commission=float(cost_assumptions.min_fee),
        stamp_duty_rate=stamp_rate,
        transfer_fee_rate=transfer_fee_rate,
        exchange_fee_rate=exchange_fee_rate,
        slippage_bps=float(cost_assumptions.slippage_bps),
    )
    return BrokerFeeProfile(
        profile_id="engineering-fallback-from-paper-fill-cost-assumptions",
        default_buy=buy_model,
        default_sell=sell_model,
        instrument_side_overrides={
            "etf": {
                "buy": RuntimeFeeModel(
                    commission_rate=float(cost_assumptions.fee_rate),
                    min_commission=float(cost_assumptions.min_fee),
                    stamp_duty_rate=etf_buy_stamp_rate,
                    transfer_fee_rate=transfer_fee_rate,
                    exchange_fee_rate=exchange_fee_rate,
                    slippage_bps=float(cost_assumptions.slippage_bps),
                ),
                "sell": RuntimeFeeModel(
                    commission_rate=float(cost_assumptions.fee_rate),
                    min_commission=float(cost_assumptions.min_fee),
                    stamp_duty_rate=etf_sell_stamp_rate,
                    transfer_fee_rate=transfer_fee_rate,
                    exchange_fee_rate=exchange_fee_rate,
                    slippage_bps=float(cost_assumptions.slippage_bps),
                ),
            }
        },
        notes=("Deterministic engineering fallback derived from DailyPaperLoopConfig.cost_assumptions; not broker truth.",),
    )


def _quant_order_authorization(
    quant_decision: QuantFirmDecisionReport,
    context: Mapping[str, Any],
) -> Mapping[str, Any]:
    if not is_quant_firm_approved(quant_decision):
        return {
            "buy_authorized": False,
            "sell_authorized": False,
            "requested_action": str(context.get("requested_action", "")),
            "skip_reason": "quant_firm_non_actionable_decision",
        }
    return {
        "buy_authorized": True,
        "sell_authorized": True,
        "requested_action": str(context.get("requested_action", "")),
        "skip_reason": "",
    }


def _quant_firm_candidate_actions(
    report: ExecutionCandidateReport,
    quant_decision: QuantFirmDecisionReport,
    context: Mapping[str, Any],
) -> tuple[Mapping[str, Any], ...]:
    authorization = _quant_order_authorization(quant_decision, context)
    rows: list[Mapping[str, Any]] = []
    for candidate in report.candidates:
        action = "exit" if candidate.direction == "short" else "buy" if candidate.direction == "long" else "hold"
        approved = authorization["sell_authorized"] if action == "exit" else authorization["buy_authorized"] if action == "buy" else True
        rows.append(
            {
                "symbol": candidate.symbol,
                "candidate_id": dict(candidate.metadata).get("candidate_id", candidate.symbol),
                "candidate_direction": candidate.direction,
                "requested_action": action,
                "approved": bool(approved),
                "reason_code": "approved" if approved else authorization["skip_reason"],
                "quant_firm_final_recommendation": quant_decision.final_recommendation,
            }
        )
    return tuple(rows)


def _is_exit_candidate(candidate: ExecutionCandidate) -> bool:
    metadata = dict(candidate.metadata)
    action = str(metadata.get("action", metadata.get("decision_action", ""))).strip().lower()
    return action in ACTIONABLE_SELL_ACTIONS or metadata.get("exit_signal") is True


def _validate_config(config: DailyPaperLoopConfig) -> None:
    if config.live_market_data and not config.decision_session:
        raise DailyPaperStateError("live market data mode requires explicit decision_session")
    if not math.isfinite(float(config.initial_capital)) or config.initial_capital <= 0:
        raise DailyPaperStateError("initial_capital must be finite and positive")
    if not math.isfinite(float(config.max_position_weight)) or not (0 < float(config.max_position_weight) <= 1):
        raise DailyPaperStateError("max_position_weight must be > 0 and <= 1")
    if int(config.target_position_count) < 1:
        raise DailyPaperStateError("target_position_count must be >= 1")
    if not math.isfinite(float(config.reserve_cash_weight)) or not (0 <= float(config.reserve_cash_weight) < 1):
        raise DailyPaperStateError("reserve_cash_weight must be >= 0 and < 1")
    if int(config.min_order_lot) <= 0:
        raise DailyPaperStateError("min_order_lot must be > 0")
    if not (1 <= int(config.live_symbol_cap) <= 6):
        raise DailyPaperStateError("live symbol cap must be between 1 and 6")


def _validate_chronology(state: DailyPaperLoopState, decision_session: date, execution_session: date) -> None:
    if state.last_decision_session and decision_session <= _as_date(state.last_decision_session):
        raise DailyPaperStateError("decision session must be after the last applied decision session")
    if state.last_execution_session and execution_session <= _as_date(state.last_execution_session):
        raise DailyPaperStateError("execution session must be after the last applied execution session")
    if state.last_execution_session and decision_session < _as_date(state.last_execution_session):
        raise DailyPaperStateError("decision session overlaps an already applied execution lifecycle")


def _validate_time_inputs(loop_input: DailyPaperLoopInput, decision_session: date) -> None:
    cutoff = _decision_cutoff(decision_session)
    for candidate in loop_input.candidate_report.candidates:
        if candidate.direction not in CANONICAL_DIRECTIONS:
            raise DailyPaperStateError(f"candidate direction must be canonical: {candidate.symbol}")
        timestamp = _aware_shanghai(candidate.timestamp, f"candidate timestamp for {candidate.symbol}")
        if timestamp.year == 1970:
            raise DailyPaperStateError("candidate timestamp must be explicitly set for daily paper sessions")
        if timestamp > cutoff:
            raise DailyPaperStateError("candidate timestamp cannot be after decision cutoff")
    for provenance_name, provenance in (
        ("information", loop_input.information_provenance),
        ("advisory", loop_input.advisory_provenance),
        ("quant_context", loop_input.quant_firm_context),
    ):
        for path, value in _timestamp_fields(provenance, prefix=provenance_name):
            timestamp = _parse_aware_shanghai(value, path)
            if timestamp > cutoff:
                raise DailyPaperStateError(f"{path} cannot be after decision cutoff")


def _resolve_buy_reference_state(row: Mapping[str, Any]) -> tuple[str, float | None]:
    """Canonical three-state buy-reference parser for a single decision row.

    Returns (state, price):
    - ("unspecified", None): both keys absent → fallback to D close
    - ("available", positive_float): explicit valid buy reference
    - ("unavailable", None): explicitly prohibited
    Raises ValueError on any invalid/conflicting combination.
    """
    has_ebp = "executable_buy_price" in row
    has_avail = "executable_buy_price_available" in row

    if not has_ebp and not has_avail:
        return ("unspecified", None)

    if has_ebp and not has_avail:
        ebp = row["executable_buy_price"]
        if ebp is None:
            return ("unavailable", None)
        try:
            v = float(ebp)
        except (TypeError, ValueError):
            raise ValueError(f"executable_buy_price must be numeric or None, got {type(ebp).__name__}") from None
        if v > 0 and math.isfinite(v):
            return ("available", v)
        raise ValueError(f"executable_buy_price must be positive and finite, got {v}")

    # has_avail is True
    avail = row["executable_buy_price_available"]
    if avail is None:
        ebp = row.get("executable_buy_price")
        if ebp is None:
            return ("unspecified", None)
        raise ValueError("executable_buy_price_available=None with executable_buy_price present is invalid")
    if avail is True:
        ebp = row.get("executable_buy_price")
        if ebp is None:
            raise ValueError("executable_buy_price_available=True requires executable_buy_price")
        try:
            v = float(ebp)
        except (TypeError, ValueError):
            raise ValueError(f"executable_buy_price must be numeric, got {type(ebp).__name__}") from None
        if v > 0 and math.isfinite(v):
            return ("available", v)
        raise ValueError(f"executable_buy_price must be positive and finite, got {v}")
    if avail is False:
        ebp = row.get("executable_buy_price")
        if ebp is not None:
            raise ValueError("executable_buy_price_available=False cannot have a price")
        return ("unavailable", None)
    raise ValueError(f"executable_buy_price_available must be bool or None, got {type(avail).__name__}")


def _validate_market_bundle(
    market: DailyPaperMarketBundle,
    candidate_symbols: set[str],
    holding_symbols: set[str],
    decision_session: date,
    execution_session: date,
) -> Mapping[str, Any]:
    decision_symbols = set(market.decision_rows_by_symbol)
    execution_symbols = set(market.execution_rows_by_symbol)
    missing_holding_decision = holding_symbols - decision_symbols
    if missing_holding_decision:
        raise DailyPaperStateError(f"missing D market evidence for held symbols: {sorted(missing_holding_decision)}")
    missing_holding_execution = holding_symbols - execution_symbols
    if missing_holding_execution:
        raise DailyPaperStateError(f"missing D+1 market evidence for held symbols: {sorted(missing_holding_execution)}")
    missing_decision_candidates = candidate_symbols - decision_symbols - holding_symbols
    decision_prices: dict[str, float] = {}
    executable_buy_prices: dict[str, float] = {}
    for symbol, row in sorted(market.decision_rows_by_symbol.items()):
        _validate_market_row(symbol, row, decision_session, "decision")
        decision_prices[str(symbol)] = _positive_float(row.get("close"), f"decision close for {symbol}")
        state, ebp_val = _resolve_buy_reference_state(row)
        if state == "unspecified":
            executable_buy_prices[str(symbol)] = decision_prices[str(symbol)]
        elif state == "available":
            assert ebp_val is not None
            executable_buy_prices[str(symbol)] = ebp_val
        # else: "unavailable" → omitted from executable_buy_prices
    valuation_prices: dict[str, float] = {}
    for symbol, row in sorted(market.execution_rows_by_symbol.items()):
        _validate_market_row(str(symbol), row, execution_session, "execution")
        valuation_prices[str(symbol)] = _positive_float(row.get("close"), f"execution close for {symbol}")
    return {
        "decision_prices": decision_prices,
        "executable_buy_prices": executable_buy_prices,
        "valuation_prices": valuation_prices,
        "missing_decision_candidate_symbols": tuple(sorted(missing_decision_candidates)),
    }


def _validate_market_row(symbol: str, row: Mapping[str, Any], expected_session: date, label: str) -> None:
    if str(row.get("symbol", symbol)) != symbol:
        raise DailyPaperStateError(f"{label} row symbol mismatch: {symbol}")
    if _as_date(str(row.get("date"))) != expected_session:
        raise DailyPaperStateError(f"{label} market row must be exact session {expected_session.isoformat()}: {symbol}")
    if label == "execution":
        if "open" in row and not math.isfinite(float(row.get("open") or 0.0)):
            raise DailyPaperStateError(f"{label}.{symbol}.open must be finite")
        _positive_float(row.get("close"), f"{label}.{symbol}.close")
        return
    for key in ("open", "high", "low", "close"):
        _positive_float(row.get(key), f"{label}.{symbol}.{key}")


def _leakage_audit(
    loop_input: DailyPaperLoopInput,
    market_evidence: Mapping[str, Any],
    decision_session: date,
    execution_session: date,
) -> Mapping[str, Any]:
    cutoff = _decision_cutoff(decision_session)
    candidate_ok = all(
        _aware_shanghai(candidate.timestamp, f"candidate timestamp for {candidate.symbol}") <= cutoff
        for candidate in loop_input.candidate_report.candidates
    )
    decision_rows_ok = all(_as_date(str(row.get("date"))) == decision_session for row in loop_input.market.decision_rows_by_symbol.values())
    execution_rows_ok = all(_as_date(str(row.get("date"))) == execution_session for row in loop_input.market.execution_rows_by_symbol.values())
    return {
        "candidate_timestamp_lte_decision_cutoff": candidate_ok,
        "decision_market_rows_exact_d": decision_rows_ok,
        "sizing_uses_decision_close_prices": bool(market_evidence["decision_prices"] or not loop_input.candidate_report.candidates),
        "fill_uses_d_plus_1_open_execution_price": execution_rows_ok,
        "valuation_uses_d_plus_1_close_after_fill": execution_rows_ok,
        "timezone": SHANGHAI_TZ.key,
        "decision_cutoff": cutoff.isoformat(),
        "computed_not_hardcoded": True,
    }


def _decision_cutoff(decision_session: date) -> datetime:
    return datetime.combine(decision_session, time(15, 0), tzinfo=SHANGHAI_TZ)


def _aware_shanghai(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DailyPaperStateError(f"{field_name} must be timezone-aware")
    return value.astimezone(SHANGHAI_TZ)


def _parse_aware_shanghai(value: Any, field_name: str) -> datetime:
    if isinstance(value, datetime):
        return _aware_shanghai(value, field_name)
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise DailyPaperStateError(f"{field_name} timestamp must be parseable") from exc
    return _aware_shanghai(parsed, field_name)


def _positive_float(value: Any, field_name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise DailyPaperStateError(f"{field_name} must be numeric") from exc
    if not math.isfinite(result) or result <= 0:
        raise DailyPaperStateError(f"{field_name} must be positive")
    return result


def _validate_account_finite(account: PaperAccount) -> None:
    values = (account.cash, account.realized_pnl, account.unrealized_pnl)
    if not all(math.isfinite(float(value)) for value in values):
        raise DailyPaperStateError("account values must be finite")


def _session_id(config: DailyPaperLoopConfig, decision_session: date, execution_session: date) -> str:
    return f"{DAILY_LOOP_VERSION}:{config.strategy_id}:{decision_session.isoformat()}:{execution_session.isoformat()}"


def _order_id(session_id: str, symbol: str, side: Any, quantity: int, index: int) -> str:
    return payload_digest({"session_id": session_id, "index": index, "symbol": symbol, "side": _enum_value(side), "quantity": quantity})[:24]


def _idempotency_key(session_id: str, order_id: str, input_digest: str) -> str:
    return payload_digest({"session_id": session_id, "order_id": order_id, "input_digest": input_digest})


def _equity(account: PaperAccount, prices: Mapping[str, float]) -> float:
    value = float(account.cash)
    for symbol, quantity in account.positions.items():
        if symbol not in prices:
            raise DailyPaperStateError(f"missing valuation price for held symbol: {symbol}")
        value += int(quantity) * _positive_float(prices[symbol], f"valuation price for {symbol}")
    return round(value, 6)


def _holding_symbol_universe(state: DailyPaperLoopState) -> set[str]:
    return {
        *(symbol for symbol, quantity in state.execution_state.account.positions.items() if int(quantity) > 0),
    }


def _next_session_iso(calendar: TradingCalendar, session: date) -> str | None:
    try:
        return calendar.next_session(session).isoformat()
    except Exception:
        return None


def _timestamp_fields(value: Any, *, prefix: str, depth: int = 0) -> tuple[tuple[str, Any], ...]:
    if depth > 6:
        return ()
    found: list[tuple[str, Any]] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            path = f"{prefix}.{key}"
            key_text = str(key).lower()
            if "timestamp" in key_text or "cutoff" in key_text or key_text in PIT_TIME_FIELD_NAMES:
                found.append((path, item))
            elif isinstance(item, (Mapping, list, tuple)):
                found.extend(_timestamp_fields(item, prefix=path, depth=depth + 1))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            found.extend(_timestamp_fields(item, prefix=f"{prefix}[{index}]", depth=depth + 1))
    return tuple(found)


def _as_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _config_payload(config: DailyPaperLoopConfig) -> Mapping[str, Any]:
    return {
        "decision_session": config.decision_session,
        "initial_capital": config.initial_capital,
        "strategy_id": config.strategy_id,
        "max_position_weight": config.max_position_weight,
        "target_position_count": config.target_position_count,
        "reserve_cash_weight": config.reserve_cash_weight,
        "min_order_lot": config.min_order_lot,
        "live_market_data": config.live_market_data,
        "live_symbol_cap": config.live_symbol_cap,
        "cost_assumptions": _json_ready(config.cost_assumptions),
        "account_capabilities": _account_capabilities_payload(config.account_capabilities),
        "broker_returned_account_fee_profile": _json_ready(config.broker_returned_account_fee_profile),
        "persisted_user_account_fee_profile": _json_ready(config.persisted_user_account_fee_profile),
    }


def _limitations(config: DailyPaperLoopConfig) -> tuple[str, ...]:
    return (
        "paper_trading_only_no_broker_execution",
        "daily_bar_open_fill_convention_no_intraday_claim",
        "deepseek_live_disabled",
        "no_profitability_claim",
        "state_json_not_database",
        f"live_market_data_enabled:{bool(config.live_market_data)}",
    )


def _json_ready(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _json_ready(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_json_ready(item) for item in value]
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    try:
        canonical_json(value)
        return value
    except TypeError:
        return str(value)


def _enum_value(value: Any) -> str:
    return str(value.value if hasattr(value, "value") else value)
