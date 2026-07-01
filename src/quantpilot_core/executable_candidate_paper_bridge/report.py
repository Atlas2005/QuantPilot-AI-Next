"""Report helper for executable candidate paper bridge."""

from __future__ import annotations

from quantpilot_core.executable_candidate_paper_bridge.bridge import run_candidate_paper_dry_run
from quantpilot_core.executable_candidate_paper_bridge.contracts import (
    CandidatePaperBridgeInput,
    CandidatePaperBridgeResult,
)


def build_candidate_paper_bridge_report(
    bridge_input: CandidatePaperBridgeInput,
) -> CandidatePaperBridgeResult:
    """Build a bridge report using the existing dry-run engine."""

    return run_candidate_paper_dry_run(bridge_input)
