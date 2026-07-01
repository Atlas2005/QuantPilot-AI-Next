"""Bridge executable candidate decisions to paper ledger dry-run."""

from quantpilot_core.executable_candidate_paper_bridge.bridge import (
    build_paper_ledger_instruction_from_candidate,
    run_candidate_paper_dry_run,
)
from quantpilot_core.executable_candidate_paper_bridge.contracts import (
    CandidatePaperBridgeInput,
    CandidatePaperBridgeIssue,
    CandidatePaperBridgeResult,
)
from quantpilot_core.executable_candidate_paper_bridge.report import (
    build_candidate_paper_bridge_report,
)

__all__ = [
    "CandidatePaperBridgeInput",
    "CandidatePaperBridgeIssue",
    "CandidatePaperBridgeResult",
    "build_candidate_paper_bridge_report",
    "build_paper_ledger_instruction_from_candidate",
    "run_candidate_paper_dry_run",
]
