"""Print a concise summary of the manual vectorbt probe."""

from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SUMMARY_PATH = (
    REPO_ROOT
    / "local_artifacts"
    / "backtest_prototypes"
    / "vectorbt"
    / "vectorbt_probe_summary.json"
)


def main() -> int:
    if not SUMMARY_PATH.exists():
        print(f"Missing vectorbt summary: {SUMMARY_PATH}")
        return 1

    with SUMMARY_PATH.open("r", encoding="utf-8") as file:
        summary = json.load(file)

    print(f"provider: {summary.get('provider')}")
    print(f"symbol: {summary.get('symbol')}")
    print(f"row_count: {summary.get('row_count')}")
    print(f"vectorbt_importable: {summary.get('vectorbt_importable')}")
    print(f"prototype_ran: {summary.get('prototype_ran')}")
    print(f"output_metrics_available: {summary.get('output_metrics_available')}")
    print(f"metric_key_count: {len(summary.get('available_metric_keys', []))}")
    print(f"unsupported_a_share_rules: {summary.get('unsupported_a_share_rules')}")
    print(f"errors: {summary.get('errors')}")
    print(f"warnings: {summary.get('warnings')}")
    print(f"conclusion: {summary.get('conclusion')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

