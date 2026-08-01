"""Real data provider adapter contracts and optional provider implementations."""

from quantpilot_core.real_data_provider.akshare_adapter import (
    AkShareDailyBarProvider,
)
from quantpilot_core.real_data_provider.baostock_adapter import (
    BaoStockDailyBarProvider,
    BaoStockDependencyStatus,
    baostock_result_to_frame,
    detect_baostock_dependency,
    normalize_baostock_daily_bars,
)
from quantpilot_core.real_data_provider.contracts import (
    Adjustment,
    DailyBarProvider,
    DailyBarRequest,
    Level1MarketDataProvider,
    NormalizedDailyBar,
    NormalizedIntradayBar,
    NormalizedLevel1Event,
    ProviderDataError,
    ProviderDependencyError,
    ProviderError,
    ProviderName,
    parse_yyyymmdd,
    require_columns,
    is_suspended_trade_status,
    to_float,
    to_yyyymmdd,
)
from quantpilot_core.real_data_provider.index_daily_provider import (
    BaoStockIndexDailyProvider,
    IndexDailyProvenanceResult,
    TushareIndexDailyProvider,
    TusharePrimaryBaoStockIndexDailyProvider,
)
from quantpilot_core.real_data_provider.primary_fallback import (
    DailyBarProvenanceResult,
    ProviderAttempt,
    TusharePrimaryBaoStockFallbackProvider,
    provenance_warnings,
)
from quantpilot_core.real_data_provider.provider_cross_check import (
    DailyBarComparison,
    compare_daily_bars,
)
from quantpilot_core.real_data_provider.trading_calendar import (
    BaoStockTradingCalendarProvider,
    CalendarAttempt,
    CalendarError,
    CalendarProvenanceResult,
    TradingCalendar,
    TradingCalendarProvider,
    TusharePrimaryBaoStockCalendarProvider,
    TushareTradingCalendarProvider,
    calendar_to_announcement_trading_calendar,
)
from quantpilot_core.real_data_provider.tushare_adapter import (
    TushareDailyBarProvider,
    TushareDependencyStatus,
    detect_tushare_dependency,
    normalize_tushare_daily_bars,
)
from quantpilot_core.real_data_provider.snapshot_adapter import SnapshotDailyBarProvider
from quantpilot_core.real_data_provider.intraday_aggregation import (
    SUPPORTED_INTRADAY_INTERVALS,
    MinuteBarAggregator,
    aggregate_intraday_bars,
)
from quantpilot_core.real_data_provider.level1_collector import (
    Level1CollectorReport,
    Level1MarketDataSink,
    LiveLevel1Collector,
)
from quantpilot_core.real_data_provider.tdx_level1_adapter import (
    TDXLevel1Provider,
    canonicalize_tdx_level1_symbol,
    normalize_tdx_level1_snapshot,
)

__all__ = [
    "Adjustment",
    "AkShareDailyBarProvider",
    "BaoStockDailyBarProvider",
    "BaoStockIndexDailyProvider",
    "BaoStockDependencyStatus",
    "DailyBarProvider",
    "DailyBarProvenanceResult",
    "DailyBarComparison",
    "BaoStockTradingCalendarProvider",
    "DailyBarRequest",
    "Level1CollectorReport",
    "Level1MarketDataProvider",
    "Level1MarketDataSink",
    "LiveLevel1Collector",
    "MinuteBarAggregator",
    "IndexDailyProvenanceResult",
    "CalendarAttempt",
    "CalendarError",
    "CalendarProvenanceResult",
    "NormalizedDailyBar",
    "NormalizedIntradayBar",
    "NormalizedLevel1Event",
    "ProviderAttempt",
    "ProviderDataError",
    "ProviderDependencyError",
    "ProviderError",
    "ProviderName",
    "TradingCalendar",
    "TradingCalendarProvider",
    "TushareDailyBarProvider",
    "SnapshotDailyBarProvider",
    "SUPPORTED_INTRADAY_INTERVALS",
    "TDXLevel1Provider",
    "TushareIndexDailyProvider",
    "TushareDependencyStatus",
    "TusharePrimaryBaoStockCalendarProvider",
    "TusharePrimaryBaoStockFallbackProvider",
    "TusharePrimaryBaoStockIndexDailyProvider",
    "TushareTradingCalendarProvider",
    "baostock_result_to_frame",
    "calendar_to_announcement_trading_calendar",
    "canonicalize_tdx_level1_symbol",
    "compare_daily_bars",
    "detect_baostock_dependency",
    "detect_tushare_dependency",
    "normalize_baostock_daily_bars",
    "normalize_tdx_level1_snapshot",
    "normalize_tushare_daily_bars",
    "aggregate_intraday_bars",
    "parse_yyyymmdd",
    "provenance_warnings",
    "require_columns",
    "is_suspended_trade_status",
    "to_float",
    "to_yyyymmdd",
]
