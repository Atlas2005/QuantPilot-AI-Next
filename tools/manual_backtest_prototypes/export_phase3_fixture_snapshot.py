"""Export a JSON snapshot of the fake Phase 3 fixture.

This helper is local-only and does not fetch data or require external packages.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = REPO_ROOT / "data" / "fixtures" / "a_share_daily_sample_valid.csv"
DEFAULT_OUTPUT = (
    REPO_ROOT
    / "local_artifacts"
    / "backtest_prototypes"
    / "phase3_fixture_snapshot.json"
)


def build_fixture_snapshot(input_path: str | Path = DEFAULT_INPUT) -> dict:
    """Build a serializable snapshot from the fake Phase 3 fixture."""

    fixture_path = Path(input_path)
    with fixture_path.open("r", encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    return {
        "source": "phase3_fake_local_fixture",
        "row_count": len(rows),
        "columns": list(rows[0].keys()) if rows else [],
        "rows": rows,
        "notes": "Fake local fixture only; not real market data.",
    }


def write_fixture_snapshot(
    output_path: str | Path = DEFAULT_OUTPUT,
    input_path: str | Path = DEFAULT_INPUT,
) -> Path:
    """Write a fake fixture snapshot to a local artifact path."""

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    snapshot = build_fixture_snapshot(input_path)
    with output.open("w", encoding="utf-8") as file:
        json.dump(snapshot, file, ensure_ascii=False, indent=2)
    return output


def main() -> int:
    write_fixture_snapshot()
    print(str(DEFAULT_OUTPUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

