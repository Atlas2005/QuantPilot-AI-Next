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


@dataclass
class _PendingAction:
    signal: PredictionSignal
    side: OrderIntentSide
    quantity: int
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
    latest_prices: dict[str, float] = {}
    previous_session_close: dict[str, float] = {}
    session_dates: dict[str, str] = {}
    equity_curve: list[float] = [float(cfg.initial_cash)]

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
            if bar is None or bar.start < datetime.fromisoformat(action.signal.decision_timestamp):
                continue
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
                    "prediction_decision_timestamp": action.signal.decision_timestamp,
                    "execution_timestamp": bar.start.isoformat(),
                    "next_bar_execution": bar.start
                    >= datetime.fromisoformat(action.signal.decision_timestamp),
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
            quantity = int(state.account.positions.get(signal.symbol, 0))
            existing_pending = pending.get(signal.symbol)
            if (
                signal.state == PredictionState.ENTRY.value
                and quantity <= 0
                and (existing_pending is None or existing_pending.side is not OrderIntentSide.BUY)
            ):
                pending[signal.symbol] = _PendingAction(
                    signal,
                    OrderIntentSide.BUY,
                    int(cfg.order_quantity),
                )
            elif signal.state in {
                PredictionState.EXIT.value,
                PredictionState.INVALIDATED.value,
            } and quantity > 0 and (
                existing_pending is None or existing_pending.side is not OrderIntentSide.SELL
            ):
                pending[signal.symbol] = _PendingAction(
                    signal,
                    OrderIntentSide.SELL,
                    quantity,
                )
        equity_curve.append(_equity(state.account, latest_prices))

    report = _replay_report(
        bars=completed,
        engine=engine,
        config=cfg,
        state=state,
        pending=pending,
        execution_outcomes=tuple(execution_outcomes),
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
    report: dict[str, Any] = {
        "schema_version": "tdx_prediction_replay_v1",
        "mode": "replay",
        "symbols": list(engine.symbols),
        "bar_count": len(bars),
        "bar_range": [bars[0].start.isoformat(), bars[-1].end.isoformat()],
        "signal_count_by_state": dict(
            sorted(Counter(signal.state for signal in engine.material_signals).items())
        ),
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
                bool(row.get("next_bar_execution")) for row in execution_outcomes
            ),
            "outcomes": list(execution_outcomes),
        },
        "net_profitability": {
            "starting_equity": round(config.initial_cash, 6),
            "ending_equity": round(ending_equity, 6),
            "gross_return": round(gross_return, 8),
            "net_return_after_existing_fees_and_slippage": round(net_return, 8),
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
            "deterministic bounded normalization of existing factor scores; "
            "not a trained or validated probability model"
        ),
        "factor_window_semantics": (
            "the existing factor baseline's 20d/60d field names are retained, but in "
            f"this intraday adapter each row is one completed "
            f"{engine.config.feature_interval_minutes}-minute feature bar"
        ),
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
    brier_values: list[float] = []
    for horizon in horizons:
        evaluated = 0
        hits = 0
        for prediction in predictions:
            future = _future_bar(by_symbol[prediction.symbol], prediction.data_cutoff_timestamp, horizon)
            cutoff_bar = _latest_bar_at_or_before(
                by_symbol[prediction.symbol], prediction.data_cutoff_timestamp
            )
            if future is None or cutoff_bar is None:
                continue
            forward_return = future.close / cutoff_bar.close - 1.0
            predicted_up = prediction.entry_probability >= prediction.exit_probability
            hits += bool((forward_return > 0) == predicted_up)
            evaluated += 1
            if horizon == brier_horizon:
                brier_values.append(
                    (prediction.entry_probability - (1.0 if forward_return > 0 else 0.0)) ** 2
                )
        results[f"{horizon}_completed_1m_bars"] = {
            "prediction_count": evaluated,
            "directional_hit_rate": round(hits / evaluated, 6) if evaluated else None,
        }
    return {
        "directional_horizons": results,
        "brier_horizon": f"{brier_horizon}_completed_1m_bars",
        "entry_probability_brier_score": (
            round(sum(brier_values) / len(brier_values), 8) if brier_values else None
        ),
        "prediction_correctness_is_separate_from_execution": True,
    }


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
        if datetime.fromisoformat(str(outcome["execution_timestamp"])) < datetime.fromisoformat(
            str(outcome["prediction_decision_timestamp"])
        ):
            violations.append(f"execution_before_decision:{outcome['symbol']}")
    return {
        "passed": not violations,
        "violation_count": len(violations),
        "violations": violations,
        "feature_cutoff_rule": "completed feature bars with end <= decision timestamp",
        "context_cutoff_rule": (
            "daily candidates become available at the existing 15:00 decision cutoff; "
            "cached evidence requires data_asof <= decision timestamp"
        ),
        "execution_rule": "prediction actions execute no earlier than the next one-minute bar",
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
