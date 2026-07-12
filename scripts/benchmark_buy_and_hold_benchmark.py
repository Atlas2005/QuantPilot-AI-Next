#!/usr/bin/env python3
"""Manual complexity check for the Full-A buy-and-hold benchmark.

Run with ``PYTHONPATH=src python scripts/benchmark_buy_and_hold_benchmark.py``.
It prints timings for the retired repeated-mask reference and the grouped
implementation; it deliberately makes no timing assertion.
"""
from __future__ import annotations

import time
from types import SimpleNamespace

import pandas as pd

from quantpilot_core.evaluation.real_data_walk_forward_smoke import _buy_and_hold_benchmark


def reference_benchmark(frame: pd.DataFrame, windows: tuple[SimpleNamespace, ...], initial_cash: float) -> float:
    ordered = frame.sort_values(["date", "symbol"], kind="stable")
    symbols = tuple(sorted(str(symbol) for symbol in ordered["symbol"].dropna().unique()))
    valid = []
    for symbol in symbols:
        group = ordered.loc[ordered["symbol"] == symbol]
        start_rows = group.loc[group["date"] >= windows[0].test_start]
        end_rows = group.loc[group["date"] <= windows[-1].test_end]
        if not start_rows.empty and not end_rows.empty:
            start_price, end_price = float(start_rows.iloc[0]["close"]), float(end_rows.iloc[-1]["close"])
            if start_price > 0 and end_price > 0:
                valid.append((start_price, end_price))
    return round(sum((initial_cash / len(valid) / start) * end for start, end in valid), 6)


def main() -> None:
    symbol_count, date_count = 500, 80
    dates = pd.bdate_range("2024-01-02", periods=date_count).date.astype(str)
    frame = pd.DataFrame([
        {"date": date, "symbol": f"{index:06d}.SZ", "close": 10.0 + index / 1000.0 + day / 100.0}
        for day, date in enumerate(dates)
        for index in range(symbol_count)
    ]).sample(frac=1.0, random_state=7).reset_index(drop=True)
    windows = (SimpleNamespace(test_start=dates[20], test_end=dates[-1]),)

    started = time.perf_counter(); reference = reference_benchmark(frame, windows, 1_000_000.0); reference_seconds = time.perf_counter() - started
    started = time.perf_counter(); optimized = _buy_and_hold_benchmark(frame, windows, 1_000_000.0); optimized_seconds = time.perf_counter() - started

    assert reference == optimized["benchmark_final_equity"]
    print(f"symbols={symbol_count} rows={len(frame)}")
    print(f"reference repeated full-column comparisons: {symbol_count}; seconds={reference_seconds:.6f}")
    print(f"grouped benchmark full-column comparisons: 0; seconds={optimized_seconds:.6f}")


if __name__ == "__main__":
    main()
