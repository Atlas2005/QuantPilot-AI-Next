"""Legacy provider replay for P39 reference compatibility."""

from __future__ import annotations

from quantpilot_core.daily_paper_trading_loop_tradability_metrics import (
    DailyPaperTradingInput,
    build_daily_paper_trading_loop_report,
)
from quantpilot_core.gate_pruning_tradability_fill_loop import TradeSide, TradeSignalCandidate
from quantpilot_core.real_provider_mixed_etf_paper_replay.contracts import (
    ProviderReplayResult,
    RealProviderReplayInput,
)
from quantpilot_core.real_provider_mixed_etf_paper_replay.sample_bridge import (
    validate_provider_mixed_universe_sample,
)


def replay_provider_mixed_etf_sample(
    replay_input: RealProviderReplayInput,
) -> ProviderReplayResult:
    """Replay accepted samples through the legacy P36 path for compatibility."""

    validation = validate_provider_mixed_universe_sample(replay_input)
    if not validation.ok or validation.sample is None:
        return ProviderReplayResult(
            validation=validation,
            trading_day_count=0,
            stock_candidate_count=0,
            etf_candidate_count=0,
            order_intent_count_total=0,
            simulated_fill_count_total=0,
            fill_rate=0.0,
            zero_trade_day_count=0,
            zero_trade_reason_distribution={},
            cost_tax_slippage_total=0.0,
            capital_used_average=0.0,
            capital_used_max=0.0,
            net_pnl_after_cost=0.0,
            provider_sample_quality_flags=validation.quality_flags,
            etf_impact_notes=("data_quality_blocked_replay",),
            small_capital_suitability_notes=("replay_blocked_before_capital_path_check",),
        )

    sample = validation.sample
    paper_input = _sample_to_daily_paper_input(replay_input)
    daily_report = build_daily_paper_trading_loop_report(paper_input)
    metrics = daily_report.metrics
    return ProviderReplayResult(
        validation=validation,
        trading_day_count=metrics.trading_day_count,
        stock_candidate_count=len(sample.stock_symbols),
        etf_candidate_count=len(sample.etf_symbols),
        order_intent_count_total=metrics.order_intent_count_total,
        simulated_fill_count_total=metrics.simulated_fill_count_total,
        fill_rate=metrics.fill_rate,
        zero_trade_day_count=metrics.zero_trade_day_count,
        zero_trade_reason_distribution=metrics.zero_trade_reason_distribution,
        cost_tax_slippage_total=metrics.cost_tax_slippage_total,
        capital_used_average=metrics.capital_used_average,
        capital_used_max=metrics.capital_used_max,
        net_pnl_after_cost=metrics.net_pnl_after_cost,
        provider_sample_quality_flags=validation.quality_flags,
        etf_impact_notes=_etf_notes(metrics.simulated_fill_count_total, sample.etf_symbols),
        small_capital_suitability_notes=_capital_notes(metrics.fill_rate),
    )


def _sample_to_daily_paper_input(replay_input: RealProviderReplayInput) -> DailyPaperTradingInput:
    validation = validate_provider_mixed_universe_sample(replay_input)
    if not validation.ok or validation.sample is None:
        raise ValueError("provider sample must validate before replay input conversion")
    sample = validation.sample
    first_close_by_symbol: dict[str, float] = {}
    price_limits_by_day: dict[str, dict[str, tuple[float, float]]] = {}
    for row in sample.records:
        symbol = str(row["symbol"])
        close = float(row["close"])
        first_close_by_symbol.setdefault(symbol, close)
        price_limits_by_day.setdefault(str(row["trade_date"]), {})[symbol] = (
            round(close * 0.90, 4),
            round(close * 1.10, 4),
        )

    stock_symbol = sample.stock_symbols[0]
    etf_symbol = sample.etf_symbols[0]
    stock_price = first_close_by_symbol[stock_symbol]
    etf_price = first_close_by_symbol[etf_symbol]
    trading_days = sample.trading_days
    signals_by_day = {
        trading_days[0]: (
            _signal("provider-stock-buy-day1", stock_symbol, TradeSide.BUY.value, 100, stock_price, 0.01),
            _signal("provider-etf-buy-day1", etf_symbol, TradeSide.BUY.value, 500, etf_price, 0.012),
        ),
        trading_days[1]: (
            _signal("provider-etf-buy-day2", etf_symbol, TradeSide.BUY.value, 500, round(etf_price * 1.01, 4), 0.012),
        ),
        trading_days[2]: (
            _signal("provider-etf-sell-day3", etf_symbol, TradeSide.SELL.value, 500, round(etf_price * 1.02, 4), 0.008),
        ),
    }
    return DailyPaperTradingInput(
        trading_days=trading_days,
        signals_by_day=signals_by_day,
        initial_cash=replay_input.initial_cash,
        initial_positions={stock_symbol: 300, etf_symbol: 500},
        initial_sellable_positions={stock_symbol: 300, etf_symbol: 500},
        price_limits_by_day=price_limits_by_day,
        suspended_symbols_by_day={day: () for day in trading_days},
        commission_rate=0.0001,
        min_commission=1.0,
        stamp_duty_rate=0.0,
        slippage_bps=3.0,
        safety_barrier_percent=140.0,
        evidence_refs=sample.evidence_refs,
    )


def _signal(
    signal_id: str,
    symbol: str,
    side: str,
    quantity: int,
    limit_price: float,
    expected_return: float,
) -> TradeSignalCandidate:
    return TradeSignalCandidate(
        signal_id=signal_id,
        symbol=symbol,
        side=side,
        quantity=quantity,
        reference_price=limit_price,
        limit_price=limit_price,
        expected_return=expected_return,
        confidence=0.68,
        evidence_refs=(f"evidence://p39/signal/{signal_id}",),
    )


def _etf_notes(fill_count: int, etf_symbols: tuple[str, ...]) -> tuple[str, ...]:
    notes = [f"etf_symbols:{','.join(etf_symbols)}"]
    notes.append("etf_replay_produced_fills" if fill_count > 0 else "etf_replay_no_fills")
    return tuple(notes)


def _capital_notes(fill_rate: float) -> tuple[str, ...]:
    if fill_rate > 0:
        return (
            "1000_cny_stage_replay_observable",
            "10000_cny_stage_replay_observable",
            "100000_cny_stage_replay_observable",
        )
    return ("capital_path_replay_blocked_by_zero_fill_rate",)
