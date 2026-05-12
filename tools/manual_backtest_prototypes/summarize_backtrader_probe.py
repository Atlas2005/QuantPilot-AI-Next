from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SUMMARY_PATH = ROOT / "local_artifacts" / "backtest_prototypes" / "backtrader" / "backtrader_probe_summary.json"


def _load_summary() -> dict[str, Any]:
    if not SUMMARY_PATH.exists():
        raise FileNotFoundError(f"Missing Backtrader probe summary: {SUMMARY_PATH}")
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


def main() -> int:
    try:
        summary = _load_summary()
    except Exception as exc:
        print(f"Unable to summarize Backtrader probe: {exc}")
        return 1

    lines = [
        f"provider: {summary.get('provider')}",
        f"symbol: {summary.get('symbol')}",
        f"row_count: {summary.get('row_count')}",
        f"backtrader_importable: {summary.get('backtrader_importable')}",
        f"prototype_ran: {summary.get('prototype_ran')}",
        f"output_metrics_available: {summary.get('output_metrics_available')}",
        f"starting_cash: {summary.get('starting_cash')}",
        f"final_value: {summary.get('final_value')}",
        f"toy_trade_count_if_available: {summary.get('toy_trade_count_if_available')}",
        f"unsupported_a_share_rules: {summary.get('unsupported_a_share_rules')}",
        f"errors: {summary.get('errors')}",
        f"warnings: {summary.get('warnings')}",
        f"conclusion: {summary.get('conclusion')}",
    ]
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
