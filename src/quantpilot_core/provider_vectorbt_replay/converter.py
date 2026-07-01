"""Convert validated provider samples into vectorbt signal replay samples."""

from __future__ import annotations

from quantpilot_core.gate_pruning_tradability_fill_loop import TradeSide, TradeSignalCandidate
from quantpilot_core.real_provider_mixed_etf_paper_replay import (
    RealProviderReplayInput,
    validate_provider_mixed_universe_sample,
)
from quantpilot_core.vectorbt_replay_comparison import SignalReplaySample


def provider_replay_input_to_signal_sample(
    replay_input: RealProviderReplayInput,
) -> SignalReplaySample:
    """Convert provider mixed stock/ETF sample records to vectorbt replay signals."""

    validation = validate_provider_mixed_universe_sample(replay_input)
    if not validation.ok or validation.sample is None:
        blockers = ",".join(validation.blockers) or "provider_sample_invalid"
        raise ValueError(f"provider_sample_invalid:{blockers}")

    sample = validation.sample
    symbols = tuple(sorted((*sample.stock_symbols, *sample.etf_symbols)))
    prices_by_symbol = _close_prices_by_symbol_and_day(
        records=sample.records,
        symbols=symbols,
        trading_days=sample.trading_days,
    )

    stock_symbol = sample.stock_symbols[0]
    etf_symbol = sample.etf_symbols[0]
    trading_days = sample.trading_days
    first_etf_close = prices_by_symbol[etf_symbol][0]
    signals_by_date = {
        trading_days[0]: (
            _signal("provider-vectorbt-stock-buy-day1", stock_symbol, TradeSide.BUY.value, 100, prices_by_symbol[stock_symbol][0]),
            _signal("provider-vectorbt-etf-buy-day1", etf_symbol, TradeSide.BUY.value, 500, prices_by_symbol[etf_symbol][0]),
        ),
        trading_days[1]: (
            _signal("provider-vectorbt-etf-buy-day2", etf_symbol, TradeSide.BUY.value, 500, round(first_etf_close * 1.01, 4)),
        ),
        trading_days[2]: (
            _signal("provider-vectorbt-etf-sell-day3", etf_symbol, TradeSide.SELL.value, 500, round(first_etf_close * 1.02, 4)),
        ),
    }

    return SignalReplaySample(
        sample_id=sample.sample_source_uri,
        symbols=symbols,
        dates=sample.trading_days,
        prices_by_symbol=prices_by_symbol,
        signals_by_date=signals_by_date,
        init_cash=replay_input.initial_cash,
    )


def _close_prices_by_symbol_and_day(
    *,
    records: tuple[dict[str, object], ...],
    symbols: tuple[str, ...],
    trading_days: tuple[str, ...],
) -> dict[str, tuple[float, ...]]:
    close_by_key = {
        (str(row["symbol"]), str(row["trade_date"])): float(row["close"])
        for row in records
    }
    prices: dict[str, tuple[float, ...]] = {}
    for symbol in symbols:
        values: list[float] = []
        for trading_day in trading_days:
            key = (symbol, trading_day)
            if key not in close_by_key:
                raise ValueError(f"missing_close_for_symbol_day:{symbol}:{trading_day}")
            values.append(close_by_key[key])
        prices[symbol] = tuple(values)
    return prices


def _signal(
    signal_id: str,
    symbol: str,
    side: str,
    quantity: int,
    price: float,
) -> TradeSignalCandidate:
    return TradeSignalCandidate(
        signal_id=signal_id,
        symbol=symbol,
        side=side,
        quantity=quantity,
        reference_price=price,
        limit_price=price,
        expected_return=0.01,
        confidence=0.68,
        evidence_refs=(f"evidence://r3d/provider-vectorbt/{signal_id}",),
    )
