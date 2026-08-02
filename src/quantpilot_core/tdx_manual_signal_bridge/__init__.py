"""TDX manual signal bridge — exports QuantPilot signals for TDX display.

This is a read-only advisory bridge.  QuantPilot performs the analysis;
TDX displays signals for manual trader review.  No orders are placed
through this bridge and no broker interfaces are invoked.
"""

from quantpilot_core.tdx_manual_signal_bridge.contracts import (
    TDX_SIGNAL_CSV_HEADER,
    TdxSignal,
    TdxSignalAction,
)
from quantpilot_core.tdx_manual_signal_bridge.exporter import (
    export_signals,
    load_report,
    load_state,
    signal_to_dict,
    signal_to_row,
)
from quantpilot_core.tdx_manual_signal_bridge.writer import (
    TDX_PREDICTION_SIGNAL_CSV_HEADER,
    write_prediction_signals_atomic,
    write_signals_atomic,
    write_signals_csv_atomic,
    write_signals_json_atomic,
)

__all__ = [
    "TDX_SIGNAL_CSV_HEADER",
    "TDX_PREDICTION_SIGNAL_CSV_HEADER",
    "TdxSignal",
    "TdxSignalAction",
    "export_signals",
    "load_report",
    "load_state",
    "signal_to_dict",
    "signal_to_row",
    "write_prediction_signals_atomic",
    "write_signals_atomic",
    "write_signals_csv_atomic",
    "write_signals_json_atomic",
]
