"""Paper trading loop from order intent proposal to Learning Desk metrics."""

from __future__ import annotations

from dataclasses import replace
from typing import Mapping

from quantpilot_core.order_intent import OrderIntentProposal
from quantpilot_core.paper_trading.contracts import (
    PaperAccount,
    PaperFillCostAssumptions,
    PaperLoopLearningDeskOutput,
    PaperPerformanceMetrics,
    PaperTrade,
    PaperTradingLoopResult,
)
from quantpilot_core.paper_trading.simulator import PaperFillSimulator


class PaperTradingLoop:
    """Run deterministic fill simulation and update paper account state."""

    def __init__(self, simulator: PaperFillSimulator | None = None) -> None:
        self.simulator = simulator or PaperFillSimulator()

    def run(
        self,
        proposal: OrderIntentProposal,
        latest_prices: Mapping[str, float] | object,
        account: PaperAccount,
    ) -> PaperTradingLoopResult:
        """Run the paper loop without external side effects."""

        starting_equity = _equity(account, latest_prices)
        fill_result = self.simulator.simulate(proposal, latest_prices, account=account)
        account_after = _apply_trades(account, fill_result.filled_trades, latest_prices)
        ending_equity = _equity(account_after, latest_prices)
        metrics = _metrics(
            account_after,
            starting_equity,
            ending_equity,
            fill_result.filled_trades,
            len(fill_result.rejected_fills),
            len(proposal.intents),
            latest_prices,
        )
        learning = _learning_desk_output(metrics, fill_result, proposal.run_label)
        return PaperTradingLoopResult(
            account=account_after,
            fill_result=fill_result,
            metrics=metrics,
            learning_desk_output=learning,
        )


def run_paper_trading_loop(
    proposal: OrderIntentProposal,
    latest_prices: Mapping[str, float] | object,
    account: PaperAccount | None = None,
    *,
    cost_assumptions: PaperFillCostAssumptions | None = None,
) -> PaperTradingLoopResult:
    """Registry-safe wrapper for one deterministic paper loop."""

    starting_account = account or PaperAccount(cash=100_000.0)
    return PaperTradingLoop(PaperFillSimulator(cost_assumptions)).run(proposal, latest_prices, starting_account)


def _apply_trades(
    account: PaperAccount,
    trades: tuple[PaperTrade, ...],
    latest_prices: Mapping[str, float] | object,
) -> PaperAccount:
    cash = account.cash
    positions = dict(account.positions)
    trade_log = list(account.trade_log)
    for trade in trades:
        cash = round(cash + trade.cash_impact, 6)
        if trade.side == "buy":
            positions[trade.symbol] = positions.get(trade.symbol, 0) + trade.quantity
        elif trade.side == "sell":
            positions[trade.symbol] = positions.get(trade.symbol, 0) - trade.quantity
            if positions[trade.symbol] <= 0:
                positions.pop(trade.symbol)
        trade_log.append(trade)
    unrealized = _unrealized_value(positions, latest_prices)
    return replace(
        account,
        cash=cash,
        positions=dict(sorted(positions.items())),
        unrealized_pnl=round(unrealized, 6),
        trade_log=tuple(trade_log),
    )


def _metrics(
    account: PaperAccount,
    starting_equity: float,
    ending_equity: float,
    trades: tuple[PaperTrade, ...],
    rejected_count: int,
    intent_count: int,
    latest_prices: Mapping[str, float] | object,
) -> PaperPerformanceMetrics:
    gross_exposure = _unrealized_value(account.positions, latest_prices)
    turnover = round(sum(trade.gross_notional for trade in trades), 6)
    fill_rate = round(len(trades) / intent_count, 6) if intent_count else 0.0
    cost_total = round(sum(trade.total_cost for trade in trades), 6)
    net_pnl = round(ending_equity - starting_equity, 6)
    return PaperPerformanceMetrics(
        starting_equity=starting_equity,
        ending_equity=ending_equity,
        cash=round(account.cash, 6),
        gross_exposure=round(gross_exposure, 6),
        realized_pnl=round(account.realized_pnl, 6),
        unrealized_pnl=round(account.unrealized_pnl, 6),
        net_pnl=net_pnl,
        trade_count=len(trades),
        rejected_count=rejected_count,
        fill_rate=fill_rate,
        turnover=turnover,
        cost_total=cost_total,
    )


def _learning_desk_output(metrics, fill_result, run_label: str | None) -> PaperLoopLearningDeskOutput:
    primary_failure = "none"
    if metrics.rejected_count:
        primary_failure = "paper_fill_rejections"
    if metrics.trade_count and metrics.net_pnl < 0:
        primary_failure = "negative_paper_loop_net_pnl"
    performance = {
        "run_label": run_label or "paper_trading_loop",
        "ending_equity": metrics.ending_equity,
        "net_pnl": metrics.net_pnl,
        "fill_rate": metrics.fill_rate,
        "trade_count": metrics.trade_count,
        "rejected_count": metrics.rejected_count,
        "cost_total": metrics.cost_total,
    }
    rejected_reasons = tuple(reason for rejected in fill_result.rejected_fills for reason in rejected.reasons)
    return PaperLoopLearningDeskOutput(
        performance_metrics=performance,
        failure_analysis={
            "primary_failure": primary_failure,
            "rejected_reasons": rejected_reasons,
            "no_failure_detected": primary_failure == "none",
        },
        strategy_mutation={
            "recommended_focus": "sizing" if rejected_reasons else "alpha_quality",
            "paper_loop_metrics_available": True,
        },
        evidence_refs=("paper_trading_loop:order_intent",),
    )


def _equity(account: PaperAccount, latest_prices: Mapping[str, float] | object) -> float:
    return round(account.cash + _unrealized_value(account.positions, latest_prices), 6)


def _unrealized_value(positions: Mapping[str, int], latest_prices: Mapping[str, float] | object) -> float:
    total = 0.0
    for symbol, quantity in positions.items():
        price = _lookup_price(latest_prices, symbol)
        if price is not None and price > 0:
            total += quantity * price
    return round(total, 6)


def _lookup_price(latest_prices: Mapping[str, float] | object, symbol: str) -> float | None:
    if isinstance(latest_prices, Mapping):
        value = latest_prices.get(symbol)
        return float(value) if value is not None else None
    if hasattr(latest_prices, "loc") and hasattr(latest_prices, "columns"):
        try:
            columns = getattr(latest_prices, "columns")
            if "symbol" in columns and "close" in columns:
                matches = latest_prices.loc[latest_prices["symbol"] == symbol, "close"]
                if len(matches):
                    return float(matches.iloc[-1])
            if symbol in columns:
                return float(latest_prices[symbol].iloc[-1])
        except Exception:
            return None
    return None

