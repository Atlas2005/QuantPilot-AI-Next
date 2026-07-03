#!/usr/bin/env python
"""Manual runner for the small real-data walk-forward smoke."""

from __future__ import annotations

from dataclasses import asdict
from pprint import pprint

from quantpilot_core.evaluation import run_real_data_walk_forward_smoke


def main() -> None:
    report = run_real_data_walk_forward_smoke()
    print("QuantPilot real-data walk-forward smoke")
    print(f"provider: {report.provider}")
    print(f"symbols: {', '.join(report.symbols)}")
    print(f"date range: {report.date_range[0]} to {report.date_range[1]}")
    print(f"windows run: {report.windows_run}")
    if report.final_equity is None:
        print("status: unavailable")
        print("notes:")
        for note in report.notes:
            print(f"- {note}")
        return

    print(f"initial cash: {report.initial_cash:.2f}")
    print(f"final equity: {report.final_equity:.2f}")
    print(f"total return: {report.total_return:.6f}")
    print(f"max drawdown: {report.max_drawdown:.6f}")
    print(f"filled trades: {report.filled_trades}")
    print(f"rejected trades: {report.rejected_trades}")
    print(f"cost total: {report.cost_total:.6f}")
    print("per-window metrics:")
    pprint(tuple(asdict(report)["per_window_metrics"]))


if __name__ == "__main__":
    main()
