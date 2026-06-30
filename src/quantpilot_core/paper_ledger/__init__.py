"""Paper ledger dry path for gated provider samples."""

from quantpilot_core.paper_ledger.contracts import (
    PaperLedgerAccount,
    PaperLedgerOrderIntent,
    PaperLedgerResult,
    PaperLedgerStatus,
    PaperOrderSide,
    PaperOrderStatus,
)
from quantpilot_core.paper_ledger.a_share_constraints import (
    AShareConstraintResult,
    AShareConstraintStatus,
    AShareCostModel,
    ASharePositionLot,
    apply_a_share_slippage,
    calculate_a_share_order_cost,
    run_a_share_constrained_paper_order,
    validate_a_share_board_lot,
    validate_t_plus_one_sell,
)
from quantpilot_core.paper_ledger.ledger import (
    build_paper_order_from_sample_preflight_result,
    run_paper_ledger_from_gated_sample,
)

__all__ = [
    "AShareConstraintResult",
    "AShareConstraintStatus",
    "AShareCostModel",
    "ASharePositionLot",
    "PaperLedgerAccount",
    "PaperLedgerOrderIntent",
    "PaperLedgerResult",
    "PaperLedgerStatus",
    "PaperOrderSide",
    "PaperOrderStatus",
    "apply_a_share_slippage",
    "build_paper_order_from_sample_preflight_result",
    "calculate_a_share_order_cost",
    "run_a_share_constrained_paper_order",
    "run_paper_ledger_from_gated_sample",
    "validate_a_share_board_lot",
    "validate_t_plus_one_sell",
]
