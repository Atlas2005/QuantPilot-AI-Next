"""Report generation for P33 broker SDK research."""

from __future__ import annotations

from quantpilot_core.broker_sdk_research.contracts import (
    BrokerBoundaryType,
    BrokerResearchCandidateReport,
    BrokerResearchDecision,
    BrokerResearchPriority,
    BrokerResearchReport,
    BrokerResearchRiskFlag,
    BrokerResearchSeverity,
    BrokerSdkCandidate,
)
from quantpilot_core.broker_sdk_research.validation import (
    validate_broker_sdk_candidate,
    validate_broker_sdk_candidates,
)


def build_broker_research_candidate_report(
    candidate: BrokerSdkCandidate,
) -> BrokerResearchCandidateReport:
    """Build a deterministic report for one broker research candidate."""

    risk_flags = validate_broker_sdk_candidate(candidate)
    blockers = tuple(flag.code for flag in risk_flags if flag.severity == BrokerResearchSeverity.CRITICAL.value)
    warnings = tuple(flag.code for flag in risk_flags if flag.severity != BrokerResearchSeverity.CRITICAL.value)
    if blockers:
        decision = BrokerResearchDecision.BLOCKED.value
        priority = BrokerResearchPriority.BLOCKED.value
    elif warnings:
        decision = BrokerResearchDecision.MANUAL_REVIEW.value
        priority = _priority(candidate, warning_count=len(warnings))
    else:
        decision = BrokerResearchDecision.RESEARCH_READY.value
        priority = _priority(candidate, warning_count=0)

    return BrokerResearchCandidateReport(
        candidate_id=candidate.candidate_id,
        display_name=candidate.display_name,
        priority=priority,
        decision=decision,
        blockers=blockers,
        warnings=warnings,
        manual_investigation_checklist=_manual_checklist(candidate),
        risk_flags=risk_flags,
    )


def build_broker_research_report(
    candidates: tuple[BrokerSdkCandidate, ...],
) -> BrokerResearchReport:
    """Build the P33 metadata-only broker SDK research report."""

    global_flags = validate_broker_sdk_candidates(candidates)
    candidate_reports = tuple(build_broker_research_candidate_report(candidate) for candidate in candidates)
    candidate_flags = tuple(flag for report in candidate_reports for flag in report.risk_flags)
    risk_flags = global_flags + candidate_flags
    blockers = tuple(
        f"{report.candidate_id}:{code}"
        for report in candidate_reports
        for code in report.blockers
    )
    warnings = tuple(
        f"{report.candidate_id}:{code}"
        for report in candidate_reports
        for code in report.warnings
    )
    if any(flag.severity == BrokerResearchSeverity.CRITICAL.value for flag in risk_flags):
        decision = BrokerResearchDecision.BLOCKED.value
        reason = "critical_risk_flags"
    elif warnings:
        decision = BrokerResearchDecision.MANUAL_REVIEW.value
        reason = "warning_flags"
    else:
        decision = BrokerResearchDecision.RESEARCH_READY.value
        reason = "research_ready"

    return BrokerResearchReport(
        ok=decision == BrokerResearchDecision.RESEARCH_READY.value,
        decision=decision,
        reason=reason,
        candidate_reports=candidate_reports,
        recommended_research_priority=_ranked_candidate_ids(candidate_reports),
        blockers=blockers,
        warnings=warnings,
        manual_investigation_checklist=tuple(
            item
            for report in candidate_reports
            for item in report.manual_investigation_checklist
        ),
        integration_boundary_evidence=tuple(
            evidence
            for candidate in candidates
            for evidence in candidate.integration_boundary_evidence
        ),
        forbidden_scope_evidence=tuple(
            evidence
            for candidate in candidates
            for evidence in candidate.forbidden_scope_evidence
        ),
        risk_flags=risk_flags,
    )


def _priority(candidate: BrokerSdkCandidate, *, warning_count: int) -> str:
    if warning_count >= 2:
        return BrokerResearchPriority.LOW.value
    if candidate.boundary_type == BrokerBoundaryType.MANUAL_CSV.value:
        return BrokerResearchPriority.HIGH.value
    if candidate.sandbox_profile.sandbox_declared or candidate.sandbox_profile.paper_mode_declared:
        return BrokerResearchPriority.HIGH.value
    if candidate.capability_profile.supports_paper_or_sandbox:
        return BrokerResearchPriority.MEDIUM.value
    return BrokerResearchPriority.LOW.value


def _ranked_candidate_ids(
    reports: tuple[BrokerResearchCandidateReport, ...],
) -> tuple[str, ...]:
    priority_order = {
        BrokerResearchPriority.HIGH.value: 0,
        BrokerResearchPriority.MEDIUM.value: 1,
        BrokerResearchPriority.LOW.value: 2,
        BrokerResearchPriority.BLOCKED.value: 3,
    }
    return tuple(
        report.candidate_id
        for report in sorted(
            reports,
            key=lambda item: (priority_order[item.priority], item.candidate_id),
        )
    )


def _manual_checklist(candidate: BrokerSdkCandidate) -> tuple[str, ...]:
    return (
        f"{candidate.candidate_id}:confirm_license_and_source",
        f"{candidate.candidate_id}:verify_sandbox_or_paper_boundary",
        f"{candidate.candidate_id}:confirm_no_repository_credentials",
        f"{candidate.candidate_id}:map_a_share_market_rules",
        f"{candidate.candidate_id}:document_manual_approval_workflow",
    )
