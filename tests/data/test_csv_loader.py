from pathlib import Path

import pytest

from quantpilot_core.data.csv_loader import load_daily_bars_csv, validate_daily_bars_csv
from quantpilot_core.data.fixtures import get_sample_fixture_path


def test_valid_csv_loads() -> None:
    rows = load_daily_bars_csv(get_sample_fixture_path("a_share_daily_sample_valid.csv"))

    assert len(rows) == 6
    assert rows[0]["symbol"] == "000001.SZ"


def test_validate_daily_bars_csv_works() -> None:
    assert validate_daily_bars_csv(
        get_sample_fixture_path("a_share_daily_sample_valid.csv")
    ) == []
    assert validate_daily_bars_csv(
        get_sample_fixture_path("a_share_daily_sample_invalid.csv")
    )


def test_missing_file_raises_file_not_found() -> None:
    with pytest.raises(FileNotFoundError):
        load_daily_bars_csv(Path("missing_fixture.csv"))

