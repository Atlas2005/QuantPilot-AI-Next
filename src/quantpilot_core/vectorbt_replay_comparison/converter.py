"""Convert QuantPilot signal samples into vectorbt replay input."""

from __future__ import annotations

from quantpilot_core.gate_pruning_tradability_fill_loop import TradeSide
from quantpilot_core.vectorbt_replay_adapter import VectorbtReplayInput
from quantpilot_core.vectorbt_replay_comparison.contracts import SignalReplaySample


def signal_sample_to_vectorbt_input(sample: SignalReplaySample) -> VectorbtReplayInput:
    """Convert dated BUY/SELL signals into vectorbt entries and exits."""

    _validate_sample(sample)
    entries: dict[str, tuple[bool, ...]] = {}
    exits: dict[str, tuple[bool, ...]] = {}
    for symbol in sample.symbols:
        entry_values: list[bool] = []
        exit_values: list[bool] = []
        for date_value in sample.dates:
            signals = sample.signals_by_date.get(date_value, ())
            entry_values.append(
                any(signal.symbol == symbol and signal.side == TradeSide.BUY.value for signal in signals)
            )
            exit_values.append(
                any(signal.symbol == symbol and signal.side == TradeSide.SELL.value for signal in signals)
            )
        entries[symbol] = tuple(entry_values)
        exits[symbol] = tuple(exit_values)

    return VectorbtReplayInput(
        prices={symbol: tuple(sample.prices_by_symbol[symbol]) for symbol in sample.symbols},
        entries=entries,
        exits=exits,
        init_cash=sample.init_cash,
        fees=sample.fees,
        slippage=sample.slippage,
    )


def _validate_sample(sample: SignalReplaySample) -> None:
    if not sample.sample_id.strip():
        raise ValueError("sample_id_missing")
    if not sample.dates:
        raise ValueError("dates_missing")
    if not sample.symbols:
        raise ValueError("symbols_missing")
    if set(sample.symbols) != set(sample.prices_by_symbol):
        raise ValueError("price_symbols_mismatch")
    for symbol in sample.symbols:
        prices = sample.prices_by_symbol[symbol]
        if len(prices) != len(sample.dates):
            raise ValueError(f"price_length_mismatch:{symbol}")
        if any(price <= 0 for price in prices):
            raise ValueError(f"price_not_positive:{symbol}")
    if sample.init_cash <= 0:
        raise ValueError("init_cash_not_positive")
    if sample.fees < 0:
        raise ValueError("fees_negative")
    if sample.slippage < 0:
        raise ValueError("slippage_negative")
