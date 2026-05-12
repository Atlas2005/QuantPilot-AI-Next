"""Schema constants for provisional daily bar fixtures."""

DAILY_BAR_SCHEMA_VERSION = "0.1.0"

DAILY_BAR_REQUIRED_FIELDS = (
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

DAILY_BAR_NUMERIC_FIELDS = (
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
)

DAILY_BAR_FIELD_DESCRIPTIONS = {
    "symbol": "Local symbol identifier such as 000001.SZ.",
    "trade_date": "Date string in YYYY-MM-DD format.",
    "open": "Opening price for the fixture row.",
    "high": "High price for the fixture row.",
    "low": "Low price for the fixture row.",
    "close": "Closing price for the fixture row.",
    "volume": "Volume for the fixture row.",
    "amount": "Turnover amount for the fixture row.",
    "adjustment": "Adjustment marker: raw, qfq, hfq, or unknown.",
    "asset_type": "Asset type marker such as a_share_stock.",
}

