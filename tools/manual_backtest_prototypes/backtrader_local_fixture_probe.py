from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
INPUT_FIXTURE = ROOT / "data" / "fixtures" / "a_share_daily_sample_valid.csv"
ARTIFACT_DIR = ROOT / "local_artifacts" / "backtest_prototypes" / "backtrader"
CONVERTED_CSV = ARTIFACT_DIR / "backtrader_fake_fixture_000001_SZ.csv"
SUMMARY_PATH = ARTIFACT_DIR / "backtrader_probe_summary.json"
SYMBOL = "000001.SZ"
UNSUPPORTED_A_SHARE_RULES = [
    "T+1 not proven",
    "limit-up/limit-down not proven",
    "suspension handling not proven",
    "ST/delisting special cases not proven",
    "liquidity constraints not proven",
    "realistic fees/slippage not proven",
    "realistic A-share order matching not proven",
    "corporate actions not proven",
]


def _base_summary() -> dict[str, Any]:
    return {
        "provider": "backtrader",
        "input_fixture": str(INPUT_FIXTURE),
        "input_is_fake_fixture": True,
        "symbol": SYMBOL,
        "row_count": 0,
        "backtrader_importable": False,
        "prototype_ran": False,
        "output_metrics_available": False,
        "starting_cash": None,
        "final_value": None,
        "toy_trade_count_if_available": None,
        "a_share_rule_support_observed": [],
        "unsupported_a_share_rules": UNSUPPORTED_A_SHARE_RULES,
        "errors": [],
        "warnings": [],
        "conclusion": "Not run yet.",
    }


def _write_summary(summary: dict[str, Any]) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def _load_symbol_rows() -> list[dict[str, str]]:
    if not INPUT_FIXTURE.exists():
        raise FileNotFoundError(f"Missing fixture: {INPUT_FIXTURE}")

    with INPUT_FIXTURE.open("r", encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row.get("symbol") == SYMBOL]

    return sorted(rows, key=lambda row: row["trade_date"])


def _write_backtrader_csv(rows: list[dict[str, str]]) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    with CONVERTED_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["datetime", "open", "high", "low", "close", "volume", "openinterest"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "datetime": row["trade_date"],
                    "open": row["open"],
                    "high": row["high"],
                    "low": row["low"],
                    "close": row["close"],
                    "volume": row["volume"],
                    "openinterest": "0",
                }
            )


def main() -> int:
    summary = _base_summary()

    try:
        import backtrader as bt  # type: ignore[import-not-found]
    except Exception as exc:
        summary["errors"].append(f"backtrader_not_installed:{exc}")
        summary["conclusion"] = "Backtrader is not importable in this environment."
        _write_summary(summary)
        return 2

    summary["backtrader_importable"] = True

    try:
        rows = _load_symbol_rows()
        summary["row_count"] = len(rows)
        if not rows:
            raise ValueError(f"No rows found for symbol {SYMBOL}")

        _write_backtrader_csv(rows)

        class ToyFixtureStrategy(bt.Strategy):  # type: ignore[misc]
            def __init__(self) -> None:
                self.previous_close = None
                self.trade_count = 0

            def next(self) -> None:
                close = float(self.data.close[0])
                if self.previous_close is None:
                    self.previous_close = close
                    return

                if not self.position and close > self.previous_close:
                    self.buy(size=1)
                elif self.position and close < self.previous_close:
                    self.close()

                self.previous_close = close

            def notify_trade(self, trade: Any) -> None:
                if trade.isclosed:
                    self.trade_count += 1

        starting_cash = 100000.0
        cerebro = bt.Cerebro()
        cerebro.broker.setcash(starting_cash)
        data = bt.feeds.GenericCSVData(
            dataname=str(CONVERTED_CSV),
            dtformat="%Y-%m-%d",
            datetime=0,
            open=1,
            high=2,
            low=3,
            close=4,
            volume=5,
            openinterest=6,
        )
        cerebro.adddata(data)
        cerebro.addstrategy(ToyFixtureStrategy)
        results = cerebro.run()
        final_value = float(cerebro.broker.getvalue())
        strategy = results[0] if results else None

        summary["prototype_ran"] = True
        summary["output_metrics_available"] = True
        summary["starting_cash"] = starting_cash
        summary["final_value"] = final_value
        summary["toy_trade_count_if_available"] = getattr(strategy, "trade_count", None)
        summary["a_share_rule_support_observed"] = [
            "None proven. This was a toy event-driven run over a fake local fixture."
        ]
        summary["warnings"].append(
            "Prototype used fake local fixture, unit order size, and default Backtrader broker simulation; result is not real backtest evidence."
        )
        summary["conclusion"] = (
            "Backtrader consumed the converted fake fixture shape and produced a toy event-driven result, "
            "but A-share realism remains unproven."
        )
        _write_summary(summary)
        return 0
    except Exception as exc:
        summary["errors"].append(f"backtrader_probe_failed:{exc}")
        summary["conclusion"] = "Backtrader probe failed safely."
        _write_summary(summary)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
