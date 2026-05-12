"""Manual AkShare daily bar probe.

This script is not a production adapter and is not intended for CI.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


PROVIDER = "akshare"
SYMBOL = "600000"
DATE_RANGE = {"start": "20240102", "end": "20240110"}
OUTPUT_DIR = Path("local_artifacts") / "provider_probes" / PROVIDER
RAW_OUTPUT = OUTPUT_DIR / "akshare_daily_raw.local.csv"
SUMMARY_OUTPUT = OUTPUT_DIR / "summary.local.json"
CONTRACT_FIELDS = {
    "symbol",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "adjustment",
    "asset_type",
}


def main() -> int:
    errors: list[str] = []
    returned_columns: list[str] = []
    mapped_fields: list[str] = []
    row_count = 0

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        import akshare as ak  # type: ignore[import-not-found]
    except ImportError as exc:
        errors.append(f"akshare_not_installed:{exc}")
        _write_summary(row_count, returned_columns, mapped_fields, errors)
        return 2

    try:
        frame: Any = ak.stock_zh_a_hist(
            symbol=SYMBOL,
            period="daily",
            start_date=DATE_RANGE["start"],
            end_date=DATE_RANGE["end"],
            adjust="qfq",
        )
        returned_columns = [str(column) for column in getattr(frame, "columns", [])]
        row_dicts = _to_row_dicts(frame)
        row_count = len(row_dicts)
        mapped_fields = _map_columns(returned_columns)
        _write_raw_csv(returned_columns, row_dicts)
    except Exception as exc:  # noqa: BLE001 - manual probe should summarize failures.
        errors.append(f"probe_exception:{type(exc).__name__}:{exc}")

    _write_summary(row_count, returned_columns, mapped_fields, errors)
    return 0 if not errors else 1


def _to_row_dicts(frame: Any) -> list[dict[str, str]]:
    if hasattr(frame, "to_dict"):
        records = frame.to_dict("records")
        return [
            {str(key): str(value) for key, value in record.items()}
            for record in records
        ]
    return []


def _map_columns(columns: list[str]) -> list[str]:
    normalized = {_normalize(column): column for column in columns}
    column_map = {
        "日期": "trade_date",
        "股票代码": "symbol",
        "代码": "symbol",
        "开盘": "open",
        "最高": "high",
        "最低": "low",
        "收盘": "close",
        "成交量": "volume",
        "成交额": "amount",
        "date": "trade_date",
        "symbol": "symbol",
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "volume": "volume",
        "amount": "amount",
    }
    mapped = {
        target
        for source, target in column_map.items()
        if _normalize(source) in normalized
    }
    mapped.update({"adjustment", "asset_type"})
    return sorted(mapped)


def _normalize(value: str) -> str:
    return str(value).strip().lower().replace("_", "")


def _write_raw_csv(columns: list[str], rows: list[dict[str, str]]) -> None:
    with RAW_OUTPUT.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _write_summary(
    row_count: int,
    returned_columns: list[str],
    mapped_fields: list[str],
    errors: list[str],
) -> None:
    mapped_set = set(mapped_fields)
    summary = {
        "provider": PROVIDER,
        "symbol": SYMBOL,
        "date_range": DATE_RANGE,
        "row_count": row_count,
        "returned_columns": returned_columns,
        "mapped_contract_fields": sorted(mapped_set),
        "missing_contract_fields": sorted(CONTRACT_FIELDS - mapped_set),
        "errors": errors,
    }
    with SUMMARY_OUTPUT.open("w", encoding="utf-8") as file:
        json.dump(summary, file, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    raise SystemExit(main())

