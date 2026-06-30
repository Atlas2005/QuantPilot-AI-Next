"""R21 AI action proposal to paper-ledger candidate bridge."""

from quantpilot_core.ai_action_paper_bridge.bridge import run_ai_action_paper_bridge
from quantpilot_core.ai_action_paper_bridge.contracts import (
    AIActionBridgeRiskFlag,
    AIActionPaperBridgeResult,
    AIActionProposal,
    ActionSide,
    BridgeDecision,
    PaperLedgerCandidateInstruction,
    ProposalSource,
    RiskSeverity,
)
from quantpilot_core.ai_action_paper_bridge.preflight import (
    estimate_trade_cost,
    to_paper_ledger_candidate,
    validate_ai_action_proposal,
)

__all__ = [
    "AIActionBridgeRiskFlag",
    "AIActionPaperBridgeResult",
    "AIActionProposal",
    "ActionSide",
    "BridgeDecision",
    "PaperLedgerCandidateInstruction",
    "ProposalSource",
    "RiskSeverity",
    "estimate_trade_cost",
    "run_ai_action_paper_bridge",
    "to_paper_ledger_candidate",
    "validate_ai_action_proposal",
]
