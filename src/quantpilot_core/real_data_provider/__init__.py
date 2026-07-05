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
    NormalizedDailyBar,
    ProviderDataError,
    ProviderDependencyError,
    ProviderError,
    ProviderName,
    parse_yyyymmdd,
    require_columns,
    to_float,
    to_yyyymmdd,
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

__all__ = [
    "Adjustment",
    "AkShareDailyBarProvider",
    "BaoStockDailyBarProvider",
    "BaoStockDependencyStatus",
    "DailyBarProvider",
    "DailyBarProvenanceResult",
    "DailyBarComparison",
    "BaoStockTradingCalendarProvider",
    "DailyBarRequest",
    "CalendarAttempt",
    "CalendarError",
    "CalendarProvenanceResult",
    "NormalizedDailyBar",
    "ProviderAttempt",
    "ProviderDataError",
    "ProviderDependencyError",
    "ProviderError",
    "ProviderName",
    "TradingCalendar",
    "TradingCalendarProvider",
    "TushareDailyBarProvider",
    "TushareDependencyStatus",
    "TusharePrimaryBaoStockCalendarProvider",
    "TusharePrimaryBaoStockFallbackProvider",
    "TushareTradingCalendarProvider",
    "baostock_result_to_frame",
    "calendar_to_announcement_trading_calendar",
    "compare_daily_bars",
    "detect_baostock_dependency",
    "detect_tushare_dependency",
    "normalize_baostock_daily_bars",
    "normalize_tushare_daily_bars",
    "parse_yyyymmdd",
    "provenance_warnings",
    "require_columns",
    "to_float",
    "to_yyyymmdd",
]
