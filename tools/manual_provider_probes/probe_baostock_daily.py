"""Manual Baostock daily bar probe.

This script is not a production adapter and is not intended for CI.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


PROVIDER = "baostock"
SYMBOL = "sh.600000"
DATE_RANGE = {"start": "2024-01-02", "end": "2024-01-10"}
OUTPUT_DIR = Path("local_artifacts") / "provider_probes" / PROVIDER
RAW_OUTPUT = OUTPUT_DIR / "baostock_daily_raw.local.csv"
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
        import baostock as bs  # type: ignore[import-not-found]
    except ImportError as exc:
        errors.append(f"baostock_not_installed:{exc}")
        _write_summary(row_count, returned_columns, mapped_fields, errors)
        return 2

    login_result: Any | None = None
    try:
        login_result = bs.login()
        if getattr(login_result, "error_code", "0") != "0":
            errors.append(f"login_error:{getattr(login_result, 'error_msg', '')}")
            _write_summary(row_count, returned_columns, mapped_fields, errors)
            return 1

        result = bs.query_history_k_data_plus(
            SYMBOL,
            "date,code,open,high,low,close,volume,amount",
            start_date=DATE_RANGE["start"],
            end_date=DATE_RANGE["end"],
            frequency="d",
            adjustflag="2",
        )

        if getattr(result, "error_code", "0") != "0":
            errors.append(f"query_error:{getattr(result, 'error_msg', '')}")
            _write_summary(row_count, returned_columns, mapped_fields, errors)
            return 1

        returned_columns = list(getattr(result, "fields", []) or [])
        rows: list[list[str]] = []
        while result.next():
            rows.append(result.get_row_data())

        row_count = len(rows)
        mapped_fields = _map_columns(returned_columns)
        _write_raw_csv(returned_columns, rows)
    except Exception as exc:  # noqa: BLE001 - manual probe should summarize failures.
        errors.append(f"probe_exception:{type(exc).__name__}:{exc}")
    finally:
        if login_result is not None:
            try:
                bs.logout()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"logout_exception:{type(exc).__name__}:{exc}")

    _write_summary(row_count, returned_columns, mapped_fields, errors)
    return 0 if not errors else 1


def _map_columns(columns: list[str]) -> list[str]:
    column_map = {
        "code": "symbol",
        "date": "trade_date",
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "volume": "volume",
        "amount": "amount",
    }
    mapped = {column_map[column] for column in columns if column in column_map}
    mapped.update({"adjustment", "asset_type"})
    return sorted(mapped)


def _write_raw_csv(columns: list[str], rows: list[list[str]]) -> None:
    with RAW_OUTPUT.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(columns)
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

