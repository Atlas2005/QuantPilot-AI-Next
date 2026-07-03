#!/usr/bin/env python
"""Manual runner for the small real-data walk-forward smoke."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path
from pprint import pprint

from quantpilot_core.evaluation import RealDataWalkForwardSmokeConfig, run_real_data_walk_forward_smoke


DEFAULT_ARTIFACT_PATH = Path("artifacts/real_data_walk_forward_smoke/latest_report.json")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the manual real-data walk-forward smoke.")
    parser.add_argument(
        "--write-artifact",
        action="store_true",
        help=f"write a JSON report to {DEFAULT_ARTIFACT_PATH}",
    )
    parser.add_argument(
        "--artifact-path",
        default=None,
        help="custom JSON report path; implies --write-artifact",
    )
    args = parser.parse_args()
    artifact_path = args.artifact_path or (DEFAULT_ARTIFACT_PATH if args.write_artifact else None)
    report = run_real_data_walk_forward_smoke(RealDataWalkForwardSmokeConfig(artifact_path=artifact_path))
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
    print("rejection reasons:")
    rejection_reasons: dict[str, int] = {}
    for metrics in report.per_window_metrics:
        for reason, count in metrics.get("rejection_reasons", {}).items():
            rejection_reasons[reason] = rejection_reasons.get(reason, 0) + int(count)
    if rejection_reasons:
        for reason, count in sorted(rejection_reasons.items()):
            print(f"- {reason}: {count}")
    else:
        print("- none")
    print(f"cost total: {report.cost_total:.6f}")
    if report.benchmark_final_equity is not None:
        print(f"benchmark final equity: {report.benchmark_final_equity:.2f}")
        print(f"benchmark total return: {report.benchmark_total_return:.6f}")
        print(f"strategy excess return: {report.strategy_excess_return:.6f}")
    if report.artifact_path:
        print(f"artifact path: {report.artifact_path}")
    print("per-window metrics:")
    pprint(tuple(asdict(report)["per_window_metrics"]))


if __name__ == "__main__":
    main()
