"""Data value types for local fixture validation."""

from dataclasses import dataclass
from enum import Enum


class AssetType(str, Enum):
    A_SHARE_STOCK = "a_share_stock"
    INDEX = "index"
    FUND = "fund"
    UNKNOWN = "unknown"


class AdjustmentType(str, Enum):
    RAW = "raw"
    QFQ = "qfq"
    HFQ = "hfq"
    UNKNOWN = "unknown"


class DataFrequency(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    INTRADAY = "intraday"
    UNKNOWN = "unknown"


class DataQualityStatus(str, Enum):
    VALID = "valid"
    WARNING = "warning"
    INVALID = "invalid"


@dataclass(frozen=True)
class DailyBar:
    """A provisional local daily OHLCV record shape."""

    symbol: str
    trade_date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float
    adjustment: AdjustmentType = AdjustmentType.UNKNOWN
    asset_type: AssetType = AssetType.A_SHARE_STOCK

