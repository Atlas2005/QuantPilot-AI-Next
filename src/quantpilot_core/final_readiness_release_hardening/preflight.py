"""R30 final readiness / release hardening preflight."""

from __future__ import annotations

from quantpilot_core.final_readiness_release_hardening.checks import (
    default_forbidden_scope_checks,
    default_required_documents,
    default_required_modules,
)
from quantpilot_core.final_readiness_release_hardening.contracts import (
    FinalReadinessInput,
    FinalReadinessReport,
)
from quantpilot_core.final_readiness_release_hardening.report import (
    build_final_readiness_report,
)


def run_final_readiness_release_hardening(
    input_data: FinalReadinessInput | None = None,
    *,
    project_root: str | None = None,
) -> FinalReadinessReport:
    """Run the final preflight/sandbox MVP readiness report."""

    final_input = input_data or FinalReadinessInput(
        release_id="r30-preflight-sandbox-mvp",
        modules=default_required_modules(),
        documents=default_required_documents(),
        forbidden_scope_checks=default_forbidden_scope_checks(),
        evidence_refs=("evidence://r30/final-readiness-default-input",),
    )
    return build_final_readiness_report(final_input, project_root=project_root)
