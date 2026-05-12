"""Summarize manual provider probe JSON summaries."""

from __future__ import annotations

import json
from pathlib import Path


SUMMARY_ROOT = Path("local_artifacts") / "provider_probes"


def main() -> int:
    summaries = sorted(SUMMARY_ROOT.glob("*/summary.local.json"))
    if not summaries:
        print("No provider probe summaries found.")
        return 1

    for path in summaries:
        with path.open("r", encoding="utf-8") as file:
            summary = json.load(file)
        print(f"Provider: {summary.get('provider')}")
        print(f"  symbol: {summary.get('symbol')}")
        print(f"  date_range: {summary.get('date_range')}")
        print(f"  row_count: {summary.get('row_count')}")
        print(f"  returned_columns: {summary.get('returned_columns')}")
        print(f"  mapped_contract_fields: {summary.get('mapped_contract_fields')}")
        print(f"  missing_contract_fields: {summary.get('missing_contract_fields')}")
        print(f"  errors: {summary.get('errors')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

