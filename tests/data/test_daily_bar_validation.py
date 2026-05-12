from quantpilot_core.data.csv_loader import load_daily_bars_csv
from quantpilot_core.data.fixtures import get_sample_fixture_path
from quantpilot_core.data.validation import (
    validate_daily_bar_record,
    validate_daily_bar_sequence,
)


def test_valid_fixture_has_no_validation_errors() -> None:
    records = load_daily_bars_csv(get_sample_fixture_path("a_share_daily_sample_valid.csv"))

    assert validate_daily_bar_sequence(records) == []


def test_invalid_fixture_has_validation_errors() -> None:
    records = load_daily_bars_csv(get_sample_fixture_path("a_share_daily_sample_invalid.csv"))

    errors = validate_daily_bar_sequence(records)

    assert errors
    assert any("missing_or_blank:symbol" in error for error in errors)
    assert any("negative_price:open" in error for error in errors)
    assert any("negative_volume" in error for error in errors)
    assert any("invalid_price_range:high_lt_low" in error for error in errors)
    assert any("invalid_trade_date" in error for error in errors)
    assert any("negative_amount" in error for error in errors)
    assert any("invalid_adjustment" in error for error in errors)
    assert any("duplicate_symbol_trade_date" in error for error in errors)
    assert any("unsorted_trade_date" in error for error in errors)


def test_required_field_checks_work() -> None:
    errors = validate_daily_bar_record(
        {
            "symbol": "",
            "trade_date": "2024-01-02",
            "open": "10",
            "high": "10",
            "low": "10",
            "close": "10",
            "volume": "1",
            "amount": "1",
            "adjustment": "qfq",
            "asset_type": "a_share_stock",
        }
    )

    assert "missing_or_blank:symbol" in errors


def test_numeric_checks_work() -> None:
    errors = validate_daily_bar_record(
        {
            "symbol": "000001.SZ",
            "trade_date": "2024-01-02",
            "open": "not-a-number",
            "high": "10",
            "low": "10",
            "close": "10",
            "volume": "1",
            "amount": "1",
            "adjustment": "qfq",
            "asset_type": "a_share_stock",
        }
    )

    assert "invalid_numeric:open" in errors


def test_date_format_checks_work() -> None:
    errors = validate_daily_bar_record(
        {
            "symbol": "000001.SZ",
            "trade_date": "20240102",
            "open": "10",
            "high": "10",
            "low": "10",
            "close": "10",
            "volume": "1",
            "amount": "1",
            "adjustment": "qfq",
            "asset_type": "a_share_stock",
        }
    )

    assert "invalid_trade_date" in errors


def test_duplicate_symbol_date_check_works() -> None:
    records = [
        {
            "symbol": "000001.SZ",
            "trade_date": "2024-01-02",
            "open": "10",
            "high": "10",
            "low": "10",
            "close": "10",
            "volume": "1",
            "amount": "1",
            "adjustment": "qfq",
            "asset_type": "a_share_stock",
        },
        {
            "symbol": "000001.SZ",
            "trade_date": "2024-01-02",
            "open": "10",
            "high": "10",
            "low": "10",
            "close": "10",
            "volume": "1",
            "amount": "1",
            "adjustment": "qfq",
            "asset_type": "a_share_stock",
        },
    ]

    assert any(
        "duplicate_symbol_trade_date" in error
        for error in validate_daily_bar_sequence(records)
    )


def test_unsorted_sequence_check_works() -> None:
    records = [
        {
            "symbol": "000001.SZ",
            "trade_date": "2024-01-03",
            "open": "10",
            "high": "10",
            "low": "10",
            "close": "10",
            "volume": "1",
            "amount": "1",
            "adjustment": "qfq",
            "asset_type": "a_share_stock",
        },
        {
            "symbol": "000001.SZ",
            "trade_date": "2024-01-02",
            "open": "10",
            "high": "10",
            "low": "10",
            "close": "10",
            "volume": "1",
            "amount": "1",
            "adjustment": "qfq",
            "asset_type": "a_share_stock",
        },
    ]

    assert any(
        "unsorted_trade_date" in error
        for error in validate_daily_bar_sequence(records)
    )

