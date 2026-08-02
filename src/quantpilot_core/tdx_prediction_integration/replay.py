"""Chronological TDX minute replay with existing A-share paper execution."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, fields
from datetime import datetime
from typing import Any

from quantpilot_core.a_share_market_reality_execution import (
    AShareExecutionAccountState,
    AShareExecutionOutcome,
    execute_a_share_reality_proposal,
    summarize_execution_outcomes,
)
from quantpilot_core.a_share_tradability_metadata import (
    AShareTradabilityMetadataConfig,
    enrich_market_rows,
)
from quantpilot_core.daily_paper_loop.state import payload_digest
from quantpilot_core.order_intent import OrderIntent, OrderIntentProposal, OrderIntentSide
from quantpilot_core.paper_trading import PaperAccount
from quantpilot_core.real_data_provider import NormalizedIntradayBar
from quantpilot_core.tdx_prediction_integration.contracts import (
    PredictionSignal,
    PredictionState,
    ReplayConfig,
    ReplayResult,
    TDX_PREDICTION_ENGINE_VERSION,
)
from quantpilot_core.tdx_prediction_integration.engine import (
    TDXPredictionEngineV1,
    engine_source_components,
)
from quantpilot_core.tdx_prediction_integration.intraday_features import (
    intraday_feature_semantics,
)


@dataclass
class _PendingAction:
    signal: PredictionSignal
    side: OrderIntentSide
    quantity: int
    transition_id: str
    decision_bar_index: int
    decision_bar_start: datetime
    decision_bar_end: datetime
    attempted_date: str | None = None


def run_historical_replay(
    bars: Sequence[NormalizedIntradayBar],
    engine: TDXPredictionEngineV1,
    *,
    config: ReplayConfig | None = None,
) -> ReplayResult:
    """Replay completed bars in time order and execute signals on the next bar."""

    cfg = config or ReplayConfig()
    if cfg.initial_cash <= 0:
        raise ValueError("initial_cash must be positive")
    if cfg.order_quantity <= 0:
        raise ValueError("order_quantity must be positive")
    completed = tuple(
        sorted(
            (
                bar
                for bar in bars
                if bar.interval_minutes == 1 and not bar.partial
            ),
            key=lambda bar: (bar.end, bar.symbol, bar.start),
        )
    )
    if not completed:
        raise ValueError("historical replay requires completed one-minute bars")
    _validate_chronology(completed)

    state = AShareExecutionAccountState(PaperAccount(cash=float(cfg.initial_cash)))
    pending: dict[str, _PendingAction] = {}
    execution_outcomes: list[Mapping[str, Any]] = []
    transition_records: list[dict[str, Any]] = []
    latest_prices: dict[str, float] = {}
    previous_session_close: dict[str, float] = {}
    session_dates: dict[str, str] = {}
    equity_curve: list[float] = [float(cfg.initial_cash)]
    bar_indices = _bar_indices(completed)

    grouped: dict[datetime, list[NormalizedIntradayBar]] = defaultdict(list)
    for bar in completed:
        grouped[bar.end].append(bar)

    for cutoff in sorted(grouped):
        current = tuple(sorted(grouped[cutoff], key=lambda bar: bar.symbol))
        by_symbol = {bar.symbol: bar for bar in current}
        for bar in current:
            prior_date = session_dates.get(bar.symbol)
            current_date = bar.start.date().isoformat()
            if prior_date is not None and prior_date != current_date:
                previous_session_close[bar.symbol] = latest_prices[bar.symbol]
        for symbol, action in tuple(sorted(pending.items())):
            bar = by_symbol.get(symbol)
            if bar is None:
                continue
            execution_bar_index = bar_indices[(bar.symbol, bar.start)]
            execution_delay_bars = execution_bar_index - action.decision_bar_index
            if execution_delay_bars <= 0:
                raise RuntimeError(
                    f"execution bar must follow decision bar for {bar.symbol}"
                )
            trade_date = bar.start.date().isoformat()
            if action.attempted_date == trade_date:
                continue
            before_trade_count = len(state.account.trade_log)
            result = execute_a_share_reality_proposal(
                _proposal(action, bar),
                {
                    symbol: _market_row(
                        bar,
                        previous_session_close.get(symbol),
                    )
                },
                state,
                trade_date=trade_date,
                cost_assumptions=cfg.cost_assumptions,
                config=cfg.execution_config,
            )
            state = result.state
            outcome = result.outcomes[0]
            execution_outcomes.append(
                {
                    **asdict(outcome),
                    "prediction_state": action.signal.state,
                    "transition_id": action.transition_id,
                    "prediction_decision_timestamp": action.signal.decision_timestamp,
                    "execution_timestamp": bar.start.isoformat(),
                    "decision_bar_index": action.decision_bar_index,
                    "decision_bar_start": action.decision_bar_start.isoformat(),
                    "decision_bar_end": action.decision_bar_end.isoformat(),
                    "execution_bar_index": execution_bar_index,
                    "execution_bar_start": bar.start.isoformat(),
                    "execution_bar_end": bar.end.isoformat(),
                    "execution_delay_bars": execution_delay_bars,
                    "account_trade_log_count_before": before_trade_count,
                    "account_trade_log_count_after": len(state.account.trade_log),
                }
            )
            if outcome.status == "deferred" and outcome.rejection_or_deferral_reason == (
                "t_plus_one_sellable_quantity_insufficient"
            ):
                action.attempted_date = trade_date
            else:
                pending.pop(symbol, None)

        for bar in current:
            current_date = bar.start.date().isoformat()
            session_dates[bar.symbol] = current_date
            latest_prices[bar.symbol] = bar.close

        emitted = engine.process_completed_bars(current)
        for signal in emitted:
            decision_bar = by_symbol.get(signal.symbol)
            if decision_bar is None or decision_bar.end.isoformat() != signal.decision_timestamp:
                raise RuntimeError(
                    f"prediction decision does not bind to a completed source bar: {signal.symbol}"
                )
            decision_bar_index = bar_indices[(decision_bar.symbol, decision_bar.start)]
            transition_id = (
                f"{signal.symbol}:{signal.decision_timestamp}:{signal.state}"
            )
            quantity = int(state.account.positions.get(signal.symbol, 0))
            existing_pending = pending.get(signal.symbol)
            record: dict[str, Any] = {
                "transition_id": transition_id,
                "symbol": signal.symbol,
                "state": signal.state,
                "decision_timestamp": signal.decision_timestamp,
                "decision_bar_index": decision_bar_index,
                "decision_bar_start": decision_bar.start.isoformat(),
                "decision_bar_end": decision_bar.end.isoformat(),
                "position_quantity_before_conversion": quantity,
                "actionable_transition": False,
                "intended_side": None,
                "conversion_reason": "state_transition_not_actionable",
            }
            if signal.state == PredictionState.ENTRY.value:
                record["intended_side"] = OrderIntentSide.BUY.value
                if quantity > 0:
                    record["conversion_reason"] = "already_in_position"
                elif existing_pending is not None:
                    record["conversion_reason"] = "duplicate_or_cooldown"
                else:
                    record["actionable_transition"] = True
                    record["conversion_reason"] = "pending_next_bar_execution"
                    pending[signal.symbol] = _PendingAction(
                        signal=signal,
                        side=OrderIntentSide.BUY,
                        quantity=int(cfg.order_quantity),
                        transition_id=transition_id,
                        decision_bar_index=decision_bar_index,
                        decision_bar_start=decision_bar.start,
                        decision_bar_end=decision_bar.end,
                    )
            elif signal.state in {
                PredictionState.EXIT.value,
                PredictionState.INVALIDATED.value,
            }:
                record["intended_side"] = OrderIntentSide.SELL.value
                if quantity <= 0:
                    record["conversion_reason"] = "no_position_to_exit"
                elif existing_pending is not None:
                    record["conversion_reason"] = "duplicate_or_cooldown"
                else:
                    record["actionable_transition"] = True
                    record["conversion_reason"] = "pending_next_bar_execution"
                    pending[signal.symbol] = _PendingAction(
                        signal=signal,
                        side=OrderIntentSide.SELL,
                        quantity=quantity,
                        transition_id=transition_id,
                        decision_bar_index=decision_bar_index,
                        decision_bar_start=decision_bar.start,
                        decision_bar_end=decision_bar.end,
                    )
            transition_records.append(record)
        equity_curve.append(_equity(state.account, latest_prices))

    report = _replay_report(
        bars=completed,
        engine=engine,
        config=cfg,
        state=state,
        pending=pending,
        execution_outcomes=tuple(execution_outcomes),
        transition_records=tuple(transition_records),
        latest_prices=latest_prices,
        equity_curve=tuple(equity_curve),
    )
    return ReplayResult(
        report=report,
        material_signals=engine.material_signals,
        all_predictions=engine.all_predictions,
        execution_outcomes=tuple(execution_outcomes),
    )


def _proposal(action: _PendingAction, bar: NormalizedIntradayBar) -> OrderIntentProposal:
    order_id = (
        f"tdx-prediction:{action.signal.symbol}:{action.signal.decision_timestamp}:"
        f"{bar.start.isoformat()}:{action.side.value}"
    )
    intent = OrderIntent(
        symbol=action.signal.symbol,
        side=action.side,
        target_shares=int(action.quantity),
        reason=f"prediction_state:{action.signal.state}",
        source_agent=TDX_PREDICTION_ENGINE_VERSION,
        confidence=(
            action.signal.entry_probability
            if action.side is OrderIntentSide.BUY
            else action.signal.exit_probability
        ),
        strategy_id=TDX_PREDICTION_ENGINE_VERSION,
        run_label="tdx_prediction_replay_v1",
        metadata={
            "order_id": order_id,
            "a_share_lot_size": 100,
            "prediction_decision_timestamp": action.signal.decision_timestamp,
            "prediction_data_cutoff_timestamp": action.signal.data_cutoff_timestamp,
        },
    )
    return OrderIntentProposal(
        intents=(intent,),
        proposal_source="exec2",
        advisory_only=True,
        created_at=bar.start.isoformat(),
        run_label="tdx_prediction_replay_v1",
        metadata={"no_broker_execution": True},
    )


def _market_row(
    bar: NormalizedIntradayBar,
    previous_close: float | None,
) -> Mapping[str, Any]:
    reference = float(previous_close or bar.open)
    base = {
        "date": bar.start.date().isoformat(),
        "symbol": bar.symbol,
        "execution_price": bar.open,
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "previous_close": reference,
        "volume": bar.volume,
        "available_volume": bar.volume,
        "is_suspended": False,
        "is_st": False,
        "price_basis": "tdx_unadjusted_intraday",
    }
    return enrich_market_rows(
        {bar.symbol: base},
        config=AShareTradabilityMetadataConfig(
            enabled=True,
            primary_price_provider="tdx_level1_intraday",
            fetched_at=bar.start.isoformat(),
        ),
    )[bar.symbol]


def _replay_report(
    *,
    bars: Sequence[NormalizedIntradayBar],
    engine: TDXPredictionEngineV1,
    config: ReplayConfig,
    state: AShareExecutionAccountState,
    pending: Mapping[str, _PendingAction],
    execution_outcomes: tuple[Mapping[str, Any], ...],
    transition_records: tuple[Mapping[str, Any], ...],
    latest_prices: Mapping[str, float],
    equity_curve: tuple[float, ...],
) -> Mapping[str, Any]:
    prediction_metrics = _prediction_metrics(
        engine.all_predictions,
        bars,
        config.evaluation_horizons,
        config.brier_horizon,
    )
    execution_summary = summarize_execution_outcomes(
        tuple(_outcome_object(row) for row in execution_outcomes)
    ) if execution_outcomes else {
        "attempted_order_count": 0,
        "fill_ratio": 0.0,
        "partial_fill_count": 0,
        "rejected_order_count": 0,
        "deferred_order_count": 0,
        "rejection_reasons": {},
    }
    filled = tuple(row for row in execution_outcomes if row["status"] in {"filled", "partial"})
    rejected = tuple(row for row in execution_outcomes if row["status"] in {"rejected", "deferred"})
    ending_equity = _equity(state.account, latest_prices)
    total_cost = sum(float(row.get("total_cost", 0.0)) for row in execution_outcomes)
    gross_return = (ending_equity + total_cost - config.initial_cash) / config.initial_cash
    net_return = (ending_equity - config.initial_cash) / config.initial_cash
    sell_trades = tuple(trade for trade in state.account.trade_log if trade.side == "sell")
    trade_returns = tuple(
        trade.realized_pnl / trade.gross_notional
        for trade in sell_trades
        if trade.gross_notional > 0
    )
    no_lookahead = _no_lookahead_audit(engine.all_predictions, execution_outcomes)
    state_counter = Counter(signal.state for signal in engine.material_signals)
    state_counts = {
        state.value: int(state_counter.get(state.value, 0))
        for state in PredictionState
    }
    reconciliation = _state_to_order_reconciliation(
        transition_records,
        execution_outcomes,
        pending,
    )
    buy_and_hold = _simple_buy_and_hold_return(bars)
    report: dict[str, Any] = {
        "schema_version": "tdx_prediction_replay_v1",
        "mode": "replay",
        "symbols": list(engine.symbols),
        "bar_count": len(bars),
        "bar_range": [bars[0].start.isoformat(), bars[-1].end.isoformat()],
        "bar_timestamp_convention": (
            "TDX timestamp is the one-minute bar start; NormalizedIntradayBar uses "
            "start-inclusive/end-exclusive bounds, so a decision bar end can equal "
            "the following execution bar start while their per-symbol indices differ"
        ),
        "bar_index_convention": (
            "zero-based chronological completed one-minute bars per symbol"
        ),
        "signal_count_by_state": state_counts,
        "material_signal_count": len(engine.material_signals),
        "prediction_evaluation": prediction_metrics,
        "trade_executability": {
            **execution_summary,
            "executable_signal_count": len(filled),
            "rejected_signal_count": len(rejected),
            "t_plus_one_rejection_count": sum(
                row.get("rejection_or_deferral_reason")
                == "t_plus_one_sellable_quantity_insufficient"
                for row in execution_outcomes
            ),
            "pending_next_bar_action_count": len(pending),
            "next_bar_execution_only": all(
                int(row.get("execution_bar_index", -1))
                > int(row.get("decision_bar_index", -1))
                and int(row.get("execution_delay_bars", 0)) >= 1
                for row in execution_outcomes
            ),
            "minimum_execution_delay_bars": (
                min(int(row["execution_delay_bars"]) for row in execution_outcomes)
                if execution_outcomes else None
            ),
            "state_to_order_reconciliation": reconciliation,
            "transition_records": list(transition_records),
            "outcomes": list(execution_outcomes),
        },
        "net_profitability": {
            "starting_equity": round(config.initial_cash, 6),
            "ending_equity": round(ending_equity, 6),
            "gross_return": round(gross_return, 8),
            "net_return_after_existing_fees_and_slippage": round(net_return, 8),
            "simple_buy_and_hold_return": buy_and_hold["equal_weight_return"],
            "excess_net_return_versus_buy_and_hold": round(
                net_return - float(buy_and_hold["equal_weight_return"]),
                8,
            ),
            "buy_and_hold_comparison": buy_and_hold,
            "transaction_cost_total": round(total_cost, 6),
            "maximum_drawdown": _maximum_drawdown(equity_curve),
            "win_rate": (
                round(sum(value > 0 for value in trade_returns) / len(trade_returns), 6)
                if trade_returns else None
            ),
            "average_trade_return": (
                round(sum(trade_returns) / len(trade_returns), 8)
                if trade_returns else None
            ),
            "turnover": round(
                sum(float(row.get("gross_value", 0.0)) for row in filled)
                / config.initial_cash,
                8,
            ),
        },
        "no_lookahead_audit": no_lookahead,
        "source_components_reused": list(engine_source_components()) + [
            "a_share_market_reality_execution.execute_a_share_reality_proposal",
            "paper_trading.PaperAccount",
        ],
        "probability_semantics": (
            "deterministic bounded normalization of fixed intraday features; "
            "not a trained or validated probability model"
        ),
        "intraday_feature_semantics": dict(intraday_feature_semantics()),
        "threshold_selection": "fixed before replay; not optimized on this replay sample",
        "deepseek_live_calls": False,
        "broker_or_order_api_calls": False,
    }
    report["deterministic_digest"] = payload_digest(report)
    return report


def _prediction_metrics(
    predictions: Sequence[PredictionSignal],
    bars: Sequence[NormalizedIntradayBar],
    horizons: Sequence[int],
    brier_horizon: int,
) -> Mapping[str, Any]:
    by_symbol: dict[str, list[NormalizedIntradayBar]] = defaultdict(list)
    for bar in bars:
        by_symbol[bar.symbol].append(bar)
    results: dict[str, Mapping[str, Any]] = {}
    for horizon in horizons:
        probabilities: list[float] = []
        labels: list[float] = []
        hits = 0
        for prediction in predictions:
            future = _future_bar(
                by_symbol[prediction.symbol],
                prediction.data_cutoff_timestamp,
                horizon,
            )
            cutoff_bar = _latest_bar_at_or_before(
                by_symbol[prediction.symbol], prediction.data_cutoff_timestamp
            )
            if future is None or cutoff_bar is None:
                continue
            forward_return = future.close / cutoff_bar.close - 1.0
            label = 1.0 if forward_return > 0 else 0.0
            predicted_up = prediction.entry_probability >= prediction.exit_probability
            hits += bool(bool(label) == predicted_up)
            probabilities.append(float(prediction.entry_probability))
            labels.append(label)
        evaluated = len(labels)
        class_frequency = sum(labels) / evaluated if evaluated else None
        model_brier = _brier_score(probabilities, labels)
        empirical_brier = (
            _brier_score([float(class_frequency)] * evaluated, labels)
            if class_frequency is not None else None
        )
        constant_brier = _brier_score([0.5] * evaluated, labels)
        results[f"{horizon}_completed_1m_bars"] = {
            "prediction_count": evaluated,
            "model_directional_hit_rate": (
                round(hits / evaluated, 6) if evaluated else None
            ),
            "directional_hit_rate": round(hits / evaluated, 6) if evaluated else None,
            "naive_majority_directional_hit_rate": (
                round(max(class_frequency, 1.0 - class_frequency), 6)
                if class_frequency is not None else None
            ),
            "empirical_positive_class_frequency": (
                round(class_frequency, 8) if class_frequency is not None else None
            ),
            "model_brier_score": model_brier,
            "empirical_class_frequency_brier_score": empirical_brier,
            "constant_0_5_brier_score": constant_brier,
            "brier_skill_score_vs_empirical_frequency": _brier_skill_score(
                model_brier,
                empirical_brier,
            ),
            "brier_skill_score_vs_constant_0_5": _brier_skill_score(
                model_brier,
                constant_brier,
            ),
        }
    selected = results.get(f"{brier_horizon}_completed_1m_bars", {})
    return {
        "directional_horizons": results,
        "brier_horizon": f"{brier_horizon}_completed_1m_bars",
        "model_brier_score": selected.get("model_brier_score"),
        "entry_probability_brier_score": selected.get("model_brier_score"),
        "empirical_class_frequency_brier_score": selected.get(
            "empirical_class_frequency_brier_score"
        ),
        "constant_0_5_brier_score": selected.get("constant_0_5_brier_score"),
        "brier_skill_score_vs_empirical_frequency": selected.get(
            "brier_skill_score_vs_empirical_frequency"
        ),
        "brier_skill_score_vs_constant_0_5": selected.get(
            "brier_skill_score_vs_constant_0_5"
        ),
        "model_directional_hit_rate": selected.get("model_directional_hit_rate"),
        "naive_directional_hit_rate": selected.get(
            "naive_majority_directional_hit_rate"
        ),
        "empirical_baseline_semantics": (
            "full-replay observed positive-class frequency; evaluation reference only"
        ),
        "prediction_correctness_is_separate_from_execution": True,
    }


def _brier_score(probabilities: Sequence[float], labels: Sequence[float]) -> float | None:
    if not labels:
        return None
    return round(
        sum(
            (float(probability) - float(label)) ** 2
            for probability, label in zip(probabilities, labels)
        )
        / len(labels),
        8,
    )


def _brier_skill_score(model: float | None, baseline: float | None) -> float | None:
    if model is None or baseline is None or baseline <= 0:
        return None
    return round(1.0 - model / baseline, 8)


def _future_bar(
    bars: Sequence[NormalizedIntradayBar],
    cutoff: str,
    horizon: int,
) -> NormalizedIntradayBar | None:
    timestamp = datetime.fromisoformat(cutoff)
    future = [bar for bar in bars if bar.end > timestamp]
    return future[horizon - 1] if len(future) >= horizon else None


def _latest_bar_at_or_before(
    bars: Sequence[NormalizedIntradayBar],
    cutoff: str,
) -> NormalizedIntradayBar | None:
    timestamp = datetime.fromisoformat(cutoff)
    eligible = [bar for bar in bars if bar.end <= timestamp]
    return eligible[-1] if eligible else None


def _no_lookahead_audit(
    predictions: Sequence[PredictionSignal],
    outcomes: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    violations: list[str] = []
    for signal in predictions:
        decision = datetime.fromisoformat(signal.decision_timestamp)
        if datetime.fromisoformat(signal.data_cutoff_timestamp) > decision:
            violations.append(f"prediction_cutoff_after_decision:{signal.symbol}")
        for context_asof in signal.context_data_asofs:
            parsed = datetime.fromisoformat(context_asof)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=decision.tzinfo)
            if parsed > decision:
                violations.append(f"context_available_after_decision:{signal.symbol}")
    for outcome in outcomes:
        required = (
            "decision_bar_index",
            "decision_bar_start",
            "decision_bar_end",
            "execution_bar_index",
            "execution_bar_start",
            "execution_bar_end",
            "execution_delay_bars",
        )
        missing = [field_name for field_name in required if field_name not in outcome]
        if missing:
            violations.append(
                f"execution_bar_audit_fields_missing:{outcome.get('symbol', '')}:"
                f"{','.join(missing)}"
            )
            continue
        decision_index = int(outcome["decision_bar_index"])
        execution_index = int(outcome["execution_bar_index"])
        delay = int(outcome["execution_delay_bars"])
        if execution_index <= decision_index:
            violations.append(f"execution_not_after_decision_bar:{outcome['symbol']}")
        if delay < 1 or delay != execution_index - decision_index:
            violations.append(f"execution_delay_bars_invalid:{outcome['symbol']}")
        decision_start = datetime.fromisoformat(str(outcome["decision_bar_start"]))
        decision_end = datetime.fromisoformat(str(outcome["decision_bar_end"]))
        execution_start = datetime.fromisoformat(str(outcome["execution_bar_start"]))
        execution_end = datetime.fromisoformat(str(outcome["execution_bar_end"]))
        if decision_end <= decision_start or execution_end <= execution_start:
            violations.append(f"invalid_bar_bounds:{outcome['symbol']}")
        if execution_start < decision_end:
            violations.append(f"execution_before_decision:{outcome['symbol']}")
        if str(outcome["prediction_decision_timestamp"]) != decision_end.isoformat():
            violations.append(f"decision_timestamp_not_bar_end:{outcome['symbol']}")
        if str(outcome["execution_timestamp"]) != execution_start.isoformat():
            violations.append(f"execution_timestamp_not_bar_start:{outcome['symbol']}")
    return {
        "passed": not violations,
        "violation_count": len(violations),
        "violations": violations,
        "feature_cutoff_rule": "completed feature bars with end <= decision timestamp",
        "context_cutoff_rule": (
            "daily candidates become available at the existing 15:00 decision cutoff; "
            "cached evidence requires data_asof <= decision timestamp"
        ),
        "execution_rule": (
            "execution_bar_index must be greater than decision_bar_index and "
            "execution_delay_bars must be at least one"
        ),
        "timestamp_convention": (
            "TDX labels bar starts; decisions use the completed bar end and executions "
            "use the next eligible bar start, which may display the same timestamp"
        ),
    }


def _bar_indices(
    bars: Sequence[NormalizedIntradayBar],
) -> Mapping[tuple[str, datetime], int]:
    by_symbol: dict[str, list[NormalizedIntradayBar]] = defaultdict(list)
    for bar in bars:
        by_symbol[bar.symbol].append(bar)
    return {
        (symbol, bar.start): index
        for symbol, rows in by_symbol.items()
        for index, bar in enumerate(sorted(rows, key=lambda item: item.start))
    }


def _state_to_order_reconciliation(
    transition_records: Sequence[Mapping[str, Any]],
    execution_outcomes: Sequence[Mapping[str, Any]],
    pending: Mapping[str, _PendingAction],
) -> Mapping[str, Any]:
    reason_keys = (
        "already_in_position",
        "no_position_to_exit",
        "duplicate_or_cooldown",
        "state_transition_not_actionable",
        "pending_next_bar_execution",
        "account_or_execution_rejection",
    )
    conversion_reasons = Counter(
        str(record["conversion_reason"]) for record in transition_records
    )
    outcome_statuses = Counter(str(row["status"]) for row in execution_outcomes)
    by_transition: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in execution_outcomes:
        by_transition[str(row["transition_id"])].append(row)
    pending_transition_ids = {action.transition_id for action in pending.values()}
    actionable_transition_ids = {
        str(record["transition_id"])
        for record in transition_records
        if bool(record["actionable_transition"])
    }
    attempted_transition_ids = set(by_transition)
    order_states = {
        PredictionState.ENTRY.value,
        PredictionState.EXIT.value,
        PredictionState.INVALIDATED.value,
    }
    order_state_records = tuple(
        record for record in transition_records if record["state"] in order_states
    )
    transition_details = []
    for record in transition_records:
        outcomes = by_transition.get(str(record["transition_id"]), [])
        transition_details.append(
            {
                **dict(record),
                "attempted_order_count": len(outcomes),
                "outcome_statuses": [str(row["status"]) for row in outcomes],
                "no_attempt_reason": (
                    str(record["conversion_reason"]) if not outcomes else None
                ),
            }
        )
    account_rejections = sum(
        status in {"rejected", "deferred"}
        for status in (str(row["status"]) for row in execution_outcomes)
    )
    reason_summary = {
        reason: int(conversion_reasons.get(reason, 0))
        for reason in reason_keys
    }
    reason_summary["account_or_execution_rejection"] = account_rejections
    non_actionable_order_state_count = sum(
        int(conversion_reasons.get(reason, 0))
        for reason in (
            "already_in_position",
            "no_position_to_exit",
            "duplicate_or_cooldown",
        )
    )
    conversion_reconciled = len(order_state_records) == (
        len(actionable_transition_ids) + non_actionable_order_state_count
    )
    lifecycle_reconciled = actionable_transition_ids == (
        attempted_transition_ids | pending_transition_ids
    )
    outcome_reconciled = len(execution_outcomes) == sum(outcome_statuses.values())
    return {
        "signal_transition_count": len(transition_records),
        "entry_signal_count": sum(
            record["state"] == PredictionState.ENTRY.value
            for record in transition_records
        ),
        "exit_signal_count": sum(
            record["state"] == PredictionState.EXIT.value
            for record in transition_records
        ),
        "invalidated_signal_count": sum(
            record["state"] == PredictionState.INVALIDATED.value
            for record in transition_records
        ),
        "order_state_signal_count": len(order_state_records),
        "actionable_transition_count": len(actionable_transition_ids),
        "unique_attempted_transition_count": len(attempted_transition_ids),
        "attempted_order_count": len(execution_outcomes),
        "retry_attempt_count": max(
            0,
            len(execution_outcomes) - len(attempted_transition_ids),
        ),
        "filled_order_count": int(outcome_statuses.get("filled", 0)),
        "partial_order_count": int(outcome_statuses.get("partial", 0)),
        "rejected_order_count": int(outcome_statuses.get("rejected", 0)),
        "deferred_order_count": int(outcome_statuses.get("deferred", 0)),
        "pending_transition_count": len(pending_transition_ids),
        "reason_counts": reason_summary,
        "initial_conversion_reconciled": conversion_reconciled,
        "actionable_lifecycle_reconciled": lifecycle_reconciled,
        "attempt_outcomes_reconciled": outcome_reconciled,
        "reconciled": (
            conversion_reconciled
            and lifecycle_reconciled
            and outcome_reconciled
        ),
        "transitions": transition_details,
    }


def _simple_buy_and_hold_return(
    bars: Sequence[NormalizedIntradayBar],
) -> Mapping[str, Any]:
    by_symbol: dict[str, list[NormalizedIntradayBar]] = defaultdict(list)
    for bar in bars:
        by_symbol[bar.symbol].append(bar)
    per_symbol = {}
    for symbol, rows in sorted(by_symbol.items()):
        ordered = sorted(rows, key=lambda bar: bar.start)
        per_symbol[symbol] = round(
            float(ordered[-1].close) / float(ordered[0].open) - 1.0,
            8,
        )
    equal_weight_return = (
        sum(per_symbol.values()) / len(per_symbol) if per_symbol else 0.0
    )
    return {
        "equal_weight_return": round(equal_weight_return, 8),
        "per_symbol_return": per_symbol,
        "semantics": (
            "equal-weight average of first one-minute open to last one-minute close; "
            "price return without simulated fees"
        ),
    }


def _validate_chronology(bars: Sequence[NormalizedIntradayBar]) -> None:
    seen: set[tuple[str, datetime]] = set()
    previous: dict[str, datetime] = {}
    for bar in bars:
        key = (bar.symbol, bar.start)
        if key in seen:
            raise ValueError(f"duplicate historical bar: {bar.symbol} {bar.start.isoformat()}")
        if bar.symbol in previous and bar.start <= previous[bar.symbol]:
            raise ValueError(f"non-chronological historical bars for {bar.symbol}")
        seen.add(key)
        previous[bar.symbol] = bar.start


def _equity(account: PaperAccount, latest_prices: Mapping[str, float]) -> float:
    return float(account.cash) + sum(
        int(quantity) * float(latest_prices.get(symbol, account.average_costs.get(symbol, 0.0)))
        for symbol, quantity in account.positions.items()
    )


def _maximum_drawdown(values: Sequence[float]) -> float:
    peak = float(values[0])
    worst = 0.0
    for value in values:
        peak = max(peak, float(value))
        if peak > 0:
            worst = min(worst, float(value) / peak - 1.0)
    return round(worst, 8)


def _outcome_object(row: Mapping[str, Any]) -> AShareExecutionOutcome:
    allowed = {field.name for field in fields(AShareExecutionOutcome)}
    return AShareExecutionOutcome(**{key: value for key, value in row.items() if key in allowed})
