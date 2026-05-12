"""CSV loading helpers for local daily bar fixtures."""

import csv
from pathlib import Path

from quantpilot_core.data.validation import validate_daily_bar_sequence


def load_daily_bars_csv(path: str | Path) -> list[dict]:
    """Load local daily bar fixture rows with csv.DictReader."""

    csv_path = Path(path)
    with csv_path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def validate_daily_bars_csv(path: str | Path) -> list[str]:
    """Load and validate local daily bar fixture rows."""

    return validate_daily_bar_sequence(load_daily_bars_csv(path))

