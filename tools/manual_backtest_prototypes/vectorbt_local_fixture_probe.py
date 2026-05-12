"""Manual vectorbt probe using the fake Phase 3 fixture.

This is not a production adapter, not a real backtest, and not intended for CI.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
INPUT_FIXTURE = REPO_ROOT / "data" / "fixtures" / "a_share_daily_sample_valid.csv"
OUTPUT_DIR = REPO_ROOT / "local_artifacts" / "backtest_prototypes" / "vectorbt"
SUMMARY_PATH = OUTPUT_DIR / "vectorbt_probe_summary.json"
SYMBOL = "000001.SZ"
UNSUPPORTED_A_SHARE_RULES = [
    "T+1 not proven",
    "limit-up/limit-down not proven",
    "suspension handling not proven",
    "ST/delisting special cases not proven",
    "liquidity constraints not proven",
    "realistic fees/slippage not proven",
]


def main() -> int:
    summary = _base_summary()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        import vectorbt as vbt  # type: ignore[import-not-found]
        import pandas as pd  # type: ignore[import-not-found]
    except ImportError as exc:
        summary["errors"].append(f"vectorbt_or_pandas_not_installed:{exc}")
        _write_summary(summary)
        return 2

    summary["vectorbt_importable"] = True

    try:
        rows = _load_symbol_rows(INPUT_FIXTURE, SYMBOL)
        summary["row_count"] = len(rows)
        if len(rows) < 2:
            summary["errors"].append("not_enough_rows_for_signal")
            _write_summary(summary)
            return 1

        frame = pd.DataFrame(rows)
        frame["trade_date"] = pd.to_datetime(frame["trade_date"])
        frame = frame.sort_values("trade_date").set_index("trade_date")
        close = frame["close"].astype(float)
        previous_close = close.shift(1)
        entries = close > previous_close
        exits = close < previous_close

        portfolio = vbt.Portfolio.from_signals(
            close,
            entries=entries.fillna(False),
            exits=exits.fillna(False),
            init_cash=100000.0,
            fees=0.0,
            freq="1D",
        )
        stats = portfolio.stats()
        metric_keys = [str(key) for key in list(getattr(stats, "index", []))]

        summary["prototype_ran"] = True
        summary["output_metrics_available"] = bool(metric_keys)
        summary["available_metric_keys"] = metric_keys
        summary["a_share_rule_support_observed"] = [
            "None proven. This was a toy signal over a fake local fixture."
        ]
        summary["warnings"].append(
            "Prototype used fake local fixture and zero fees; result is not real backtest evidence."
        )
        summary["conclusion"] = (
            "vectorbt consumed the fake fixture shape and produced toy metrics, "
            "but A-share realism remains unproven."
        )
    except Exception as exc:  # noqa: BLE001 - manual probe should summarize failures.
        summary["errors"].append(f"probe_exception:{type(exc).__name__}:{exc}")
        summary["conclusion"] = "vectorbt prototype failed safely."
        _write_summary(summary)
        return 1

    _write_summary(summary)
    return 0


def _base_summary() -> dict[str, Any]:
    return {
        "provider": "vectorbt",
        "input_fixture": str(INPUT_FIXTURE),
        "input_is_fake_fixture": True,
        "symbol": SYMBOL,
        "row_count": 0,
        "vectorbt_importable": False,
        "prototype_ran": False,
        "output_metrics_available": False,
        "available_metric_keys": [],
        "a_share_rule_support_observed": [],
        "unsupported_a_share_rules": UNSUPPORTED_A_SHARE_RULES,
        "errors": [],
        "warnings": [],
        "conclusion": "Not run yet.",
    }


def _load_symbol_rows(path: Path, symbol: str) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as file:
        rows = [
            row
            for row in csv.DictReader(file)
            if row.get("symbol") == symbol
        ]
    return sorted(rows, key=lambda row: row["trade_date"])


def _write_summary(summary: dict[str, Any]) -> None:
    with SUMMARY_PATH.open("w", encoding="utf-8") as file:
        json.dump(summary, file, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    raise SystemExit(main())

