"""In-memory A-share provider normalization for VBT3/Qlib signal workflows."""

from quantpilot_core.data_provider_normalization.contracts import (
    NORMALIZED_OHLCV_COLUMNS,
    ProviderCrossCheckReport,
    ProviderKey,
    ProviderValueDifference,
)
from quantpilot_core.data_provider_normalization.cross_check import (
    cross_check_normalized_provider_frames,
)
from quantpilot_core.data_provider_normalization.normalization import (
    canonicalize_a_share_symbol,
    normalize_baostock_history_k_frame,
    normalize_tushare_daily_frame,
    normalized_ohlcv_to_vbt3_signal_frame,
)

__all__ = [
    "NORMALIZED_OHLCV_COLUMNS",
    "ProviderCrossCheckReport",
    "ProviderKey",
    "ProviderValueDifference",
    "canonicalize_a_share_symbol",
    "cross_check_normalized_provider_frames",
    "normalize_baostock_history_k_frame",
    "normalize_tushare_daily_frame",
    "normalized_ohlcv_to_vbt3_signal_frame",
]

