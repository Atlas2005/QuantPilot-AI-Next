"""Executable candidate evaluation for A-share market reality."""

from quantpilot_core.executable_candidate.contracts import (
    CandidateAssetType,
    CandidateSide,
    ExecutableCandidateCostEstimate,
    ExecutableCandidateDecision,
    ExecutableCandidateInput,
    ExecutableCandidateIssue,
)
from quantpilot_core.executable_candidate.cost import estimate_a_share_cost
from quantpilot_core.executable_candidate.report import build_executable_candidate_report
from quantpilot_core.executable_candidate.sizing import (
    cap_quantity_by_participation,
    floor_buy_quantity_to_lot,
    max_affordable_buy_quantity,
)
from quantpilot_core.executable_candidate.tradability import evaluate_executable_candidate

__all__ = [
    "CandidateAssetType",
    "CandidateSide",
    "ExecutableCandidateCostEstimate",
    "ExecutableCandidateDecision",
    "ExecutableCandidateInput",
    "ExecutableCandidateIssue",
    "build_executable_candidate_report",
    "cap_quantity_by_participation",
    "estimate_a_share_cost",
    "evaluate_executable_candidate",
    "floor_buy_quantity_to_lot",
    "max_affordable_buy_quantity",
]
