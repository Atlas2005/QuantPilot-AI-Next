from quantpilot_core.data.schema import (
    DAILY_BAR_FIELD_DESCRIPTIONS,
    DAILY_BAR_NUMERIC_FIELDS,
    DAILY_BAR_REQUIRED_FIELDS,
    DAILY_BAR_SCHEMA_VERSION,
)
from quantpilot_core.data.types import (
    AdjustmentType,
    AssetType,
    DailyBar,
    DataFrequency,
    DataQualityStatus,
)


def test_schema_has_required_fields() -> None:
    assert DAILY_BAR_REQUIRED_FIELDS == (
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
    )
    assert set(DAILY_BAR_NUMERIC_FIELDS) == {
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
    }
    assert set(DAILY_BAR_FIELD_DESCRIPTIONS) == set(DAILY_BAR_REQUIRED_FIELDS)


def test_daily_bar_can_be_created() -> None:
    bar = DailyBar(
        symbol="000001.SZ",
        trade_date="2024-01-02",
        open=10.0,
        high=10.5,
        low=9.9,
        close=10.2,
        volume=100000.0,
        amount=1020000.0,
        adjustment=AdjustmentType.QFQ,
        asset_type=AssetType.A_SHARE_STOCK,
    )

    assert bar.symbol == "000001.SZ"
    assert bar.adjustment == AdjustmentType.QFQ


def test_enum_values_are_correct() -> None:
    assert {item.value for item in AssetType} == {
        "a_share_stock",
        "index",
        "fund",
        "unknown",
    }
    assert {item.value for item in AdjustmentType} == {
        "raw",
        "qfq",
        "hfq",
        "unknown",
    }
    assert {item.value for item in DataFrequency} == {
        "daily",
        "weekly",
        "monthly",
        "intraday",
        "unknown",
    }
    assert {item.value for item in DataQualityStatus} == {
        "valid",
        "warning",
        "invalid",
    }


def test_schema_version_exists() -> None:
    assert DAILY_BAR_SCHEMA_VERSION == "0.1.0"

