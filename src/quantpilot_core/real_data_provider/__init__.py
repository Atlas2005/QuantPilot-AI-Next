"""Real data provider adapter contracts and optional provider implementations."""

from quantpilot_core.real_data_provider.akshare_adapter import (
    AkShareDailyBarProvider,
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

__all__ = [
    "Adjustment",
    "AkShareDailyBarProvider",
    "DailyBarProvider",
    "DailyBarRequest",
    "NormalizedDailyBar",
    "ProviderDataError",
    "ProviderDependencyError",
    "ProviderError",
    "ProviderName",
    "parse_yyyymmdd",
    "require_columns",
    "to_float",
    "to_yyyymmdd",
]
