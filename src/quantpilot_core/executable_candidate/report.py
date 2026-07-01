"""Report helper for executable candidate evaluation."""

from __future__ import annotations

from quantpilot_core.executable_candidate.contracts import (
    ExecutableCandidateDecision,
    ExecutableCandidateInput,
)
from quantpilot_core.executable_candidate.tradability import evaluate_executable_candidate


def build_executable_candidate_report(
    candidate: ExecutableCandidateInput,
) -> ExecutableCandidateDecision:
    """Build a deterministic candidate decision report."""

    return evaluate_executable_candidate(candidate)
