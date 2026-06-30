"""Validation helpers for R26 broker sandbox adapter preflight."""

from __future__ import annotations

from quantpilot_core.ai_action_paper_bridge import ActionSide
from quantpilot_core.broker_sandbox_adapter_preflight.contracts import (
    BrokerSandboxAdapterMode,
    BrokerSandboxRiskFlag,
    BrokerSandboxSeverity,
    BrokerSandboxInstruction,
)


NOTIONAL_TOLERANCE = 0.0001


def validate_broker_sandbox_instruction(
    instruction: BrokerSandboxInstruction,
    *,
    allow_odd_lot: bool = False,
) -> tuple[BrokerSandboxRiskFlag, ...]:
    """Validate broker sandbox handoff instruction shape only."""

    flags: list[BrokerSandboxRiskFlag] = []
    if not instruction.instruction_id.strip():
        flags.append(_critical("instruction_id_missing", "Instruction ID must be non-empty."))
    if not instruction.proposal_id.strip():
        flags.append(_critical("proposal_id_missing", "Proposal ID must be non-empty."))
    if not instruction.symbol.strip():
        flags.append(_critical("symbol_missing", "Symbol must be non-empty."))
    if instruction.side not in {ActionSide.BUY.value, ActionSide.SELL.value, ActionSide.HOLD.value}:
        flags.append(_critical("side_invalid", "Side must be BUY, SELL, or HOLD."))
    if instruction.mode not in {mode.value for mode in BrokerSandboxAdapterMode}:
        flags.append(_critical("mode_invalid", "Mode is unsupported."))
    if instruction.side in {ActionSide.BUY.value, ActionSide.SELL.value}:
        if instruction.quantity <= 0:
            flags.append(_critical("quantity_not_positive", "BUY/SELL quantity must be positive."))
        if instruction.estimated_price <= 0:
            flags.append(_critical("estimated_price_not_positive", "BUY/SELL estimated price must be positive."))
    if instruction.side == ActionSide.HOLD.value and instruction.quantity != 0:
        flags.append(_critical("hold_quantity_not_zero", "HOLD quantity must be zero."))
    if instruction.limit_price is not None and instruction.limit_price <= 0:
        flags.append(_critical("limit_price_not_positive", "Limit price must be positive when provided."))
    expected_notional = round(instruction.quantity * instruction.estimated_price, 4)
    if abs(instruction.estimated_notional - expected_notional) > NOTIONAL_TOLERANCE:
        flags.append(
            _critical(
                "estimated_notional_mismatch",
                "Estimated notional must equal quantity times estimated price.",
            )
        )
    if not _has_evidence(instruction.evidence_refs):
        flags.append(_critical("evidence_refs_missing", "Evidence refs are required."))
    if (
        instruction.side in {ActionSide.BUY.value, ActionSide.SELL.value}
        and instruction.quantity > 0
        and instruction.quantity % 100 != 0
        and not allow_odd_lot
    ):
        flags.append(_critical("a_share_lot_size_invalid", "A-share quantity must be a 100-share lot."))
    return tuple(flags)


def _has_evidence(evidence_refs: tuple[str, ...]) -> bool:
    return any(ref.strip() for ref in evidence_refs)


def _critical(code: str, message: str) -> BrokerSandboxRiskFlag:
    return BrokerSandboxRiskFlag(
        code=code,
        severity=BrokerSandboxSeverity.CRITICAL.value,
        message=message,
    )
