"""Deterministic profitability smoke baseline for the paper pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Mapping

from quantpilot_core.execution_candidate import ExecutionCandidate, ExecutionCandidateReport
from quantpilot_core.execution_optimizer import OptimizationAssumption, build_portfolio_allocation_plan
from quantpilot_core.order_intent import OrderIntentProposal, OrderIntentProposalSource, build_order_intent_proposal
from quantpilot_core.paper_trading import PaperAccount, PaperFillCostAssumptions, PaperFillSimulator, PaperTradingLoop


PriceFrame = tuple[tuple[str, Mapping[str, float]], ...]


@dataclass(frozen=True)
class ProfitabilitySmokeReport:
    """Small structured profitability baseline from the current paper pipeline."""

    initial_cash: float
    final_equity: float
    total_return: float
    realized_pnl: float
    unrealized_pnl: float
    number_of_filled_trades: int
    number_of_rejected_trades: int
    turnover: float
    cost_drag: float
    cost_total: float
    zero_cost_final_equity: float
    zero_cost_total_return: float
    insufficient_cash_rejected_trades: int
    insufficient_cash_rejection_reasons: tuple[str, ...]
    price_dates: tuple[str, ...]
    symbols: tuple[str, ...]
    symbol_unrealized_pnl: Mapping[str, float]
    no_external_calls: bool


def run_profitability_smoke_test(
    *,
    initial_cash: float = 20_000.0,
    cost_assumptions: PaperFillCostAssumptions | None = None,
) -> ProfitabilitySmokeReport:
    """Run the deterministic EXEC2-to-paper profitability smoke baseline."""

    prices = _price_frame()
    first_prices = prices[0][1]
    last_prices = prices[-1][1]
    assumptions = cost_assumptions or PaperFillCostAssumptions(
        fee_rate=0.0003,
        min_fee=5.0,
        stamp_tax_rate=0.0005,
        slippage_bps=5.0,
        lot_size=100,
    )
    zero_cost_assumptions = PaperFillCostAssumptions(
        fee_rate=0.0,
        min_fee=0.0,
        stamp_tax_rate=0.0,
        slippage_bps=0.0,
        lot_size=assumptions.lot_size,
    )
    proposal = _proposal(first_prices, initial_cash)
    paid_report = _run_price_frame(proposal, prices, initial_cash, assumptions)
    zero_cost_report = _run_price_frame(proposal, prices, initial_cash, zero_cost_assumptions)
    insufficient_cash = PaperTradingLoop(PaperFillSimulator(assumptions)).run(
        proposal,
        first_prices,
        PaperAccount(cash=100.0),
    )
    final_equity = _equity(paid_report.account.cash, paid_report.account.positions, last_prices)
    zero_cost_final_equity = _equity(zero_cost_report.account.cash, zero_cost_report.account.positions, last_prices)
    realized_pnl = round(paid_report.account.realized_pnl, 6)
    symbol_pnl = _symbol_unrealized_pnl(paid_report.account, last_prices)
    unrealized_pnl = round(sum(symbol_pnl.values()), 6)
    total_return = _return(final_equity, initial_cash)
    zero_cost_total_return = _return(zero_cost_final_equity, initial_cash)
    rejection_reasons = tuple(
        reason
        for rejected in insufficient_cash.fill_result.rejected_fills
        for reason in rejected.reasons
    )

    return ProfitabilitySmokeReport(
        initial_cash=round(initial_cash, 6),
        final_equity=final_equity,
        total_return=total_return,
        realized_pnl=realized_pnl,
        unrealized_pnl=unrealized_pnl,
        number_of_filled_trades=len(paid_report.account.trade_log),
        number_of_rejected_trades=paid_report.metrics.rejected_count,
        turnover=round(sum(trade.gross_notional for trade in paid_report.account.trade_log), 6),
        cost_drag=round(zero_cost_final_equity - final_equity, 6),
        cost_total=round(sum(trade.total_cost for trade in paid_report.account.trade_log), 6),
        zero_cost_final_equity=zero_cost_final_equity,
        zero_cost_total_return=zero_cost_total_return,
        insufficient_cash_rejected_trades=len(insufficient_cash.fill_result.rejected_fills),
        insufficient_cash_rejection_reasons=rejection_reasons,
        price_dates=tuple(date for date, _ in prices),
        symbols=tuple(first_prices),
        symbol_unrealized_pnl=symbol_pnl,
        no_external_calls=True,
    )


def _proposal(first_prices: Mapping[str, float], initial_cash: float) -> OrderIntentProposal:
    plan = build_portfolio_allocation_plan(
        _exec1_report(),
        last_prices=first_prices,
        assumptions=OptimizationAssumption(capital=initial_cash, lot_size=100),
    )
    return build_order_intent_proposal(plan, run_label="profitability-smoke")


def _run_price_frame(
    proposal: OrderIntentProposal,
    prices: PriceFrame,
    initial_cash: float,
    assumptions: PaperFillCostAssumptions,
):
    loop = PaperTradingLoop(PaperFillSimulator(assumptions))
    account = PaperAccount(cash=initial_cash)
    result = None
    for index, (_, latest_prices) in enumerate(prices):
        active_proposal = proposal if index == 0 else _empty_mark_proposal(proposal)
        result = loop.run(active_proposal, latest_prices, account)
        account = result.account
    assert result is not None
    return result


def _empty_mark_proposal(proposal: OrderIntentProposal) -> OrderIntentProposal:
    return OrderIntentProposal(
        intents=(),
        proposal_source=OrderIntentProposalSource.EXEC2,
        advisory_only=True,
        created_at=proposal.created_at,
        run_label=proposal.run_label,
        metadata=proposal.metadata,
    )


def _exec1_report() -> ExecutionCandidateReport:
    timestamp = datetime(2026, 1, 2, 9, 30, tzinfo=UTC)
    return ExecutionCandidateReport(
        candidates=(
            ExecutionCandidate(
                symbol="000001.SZ",
                direction="long",
                confidence=0.9,
                expected_return=0.7,
                risk_score=0.2,
                liquidity_score=0.9,
                timestamp=timestamp,
            ),
            ExecutionCandidate(
                symbol="000002.SZ",
                direction="long",
                confidence=0.7,
                expected_return=0.45,
                risk_score=0.3,
                liquidity_score=0.85,
                timestamp=timestamp,
            ),
        ),
        aggregate_score=0.575,
        strategy_id="PROFITABILITY_SMOKE_EXEC1",
    )


def _price_frame() -> PriceFrame:
    return (
        ("2026-01-02", {"000001.SZ": 10.0, "000002.SZ": 20.0}),
        ("2026-01-03", {"000001.SZ": 12.0, "000002.SZ": 19.0}),
        ("2026-01-04", {"000001.SZ": 13.0, "000002.SZ": 18.0}),
    )


def _equity(cash: float, positions: Mapping[str, int], prices: Mapping[str, float]) -> float:
    market_value = sum(quantity * prices[symbol] for symbol, quantity in positions.items())
    return round(cash + market_value, 6)


def _symbol_unrealized_pnl(account: PaperAccount, prices: Mapping[str, float]) -> Mapping[str, float]:
    spent_by_symbol: dict[str, float] = {}
    for trade in account.trade_log:
        if trade.side == "buy":
            spent_by_symbol[trade.symbol] = round(spent_by_symbol.get(trade.symbol, 0.0) - trade.cash_impact, 6)
    return {
        symbol: round(quantity * prices[symbol] - spent_by_symbol.get(symbol, 0.0), 6)
        for symbol, quantity in sorted(account.positions.items())
    }


def _return(final_equity: float, initial_cash: float) -> float:
    if initial_cash <= 0:
        return 0.0
    return round((final_equity - initial_cash) / initial_cash, 6)
