"""Report builder for the RQAlpha data bundle and config review layer."""

from __future__ import annotations

from pathlib import Path

from quantpilot_core.rqalpha_data_bundle_config_review.contracts import (
    RqalphaConfigReviewResult,
)
from quantpilot_core.rqalpha_data_bundle_config_review.review import (
    review_rqalpha_data_bundle_config,
)


def build_rqalpha_data_bundle_config_review_report(
    project_root: Path | str = ".",
) -> dict[str, object]:
    """Build a plain review report without runtime execution."""

    result = review_rqalpha_data_bundle_config(project_root)
    missing_evidence_count = sum(not item.exists for item in result.evidence_items)
    return {
        "status": result.status,
        "evidence_count": sum(item.exists for item in result.evidence_items),
        "missing_evidence_count": missing_evidence_count,
        "requirements": tuple(
            {
                "name": requirement.name,
                "required": requirement.required,
                "status": requirement.status,
                "reason": requirement.reason,
            }
            for requirement in result.requirements
        ),
        "warnings": result.warnings,
        "next_actions": result.next_actions,
        "ready_for_runtime": result.ready_for_runtime,
        "production_ready": result.production_ready,
        "blocks_other_frameworks": result.blocks_other_frameworks,
        "review_statements": _review_statements(result),
    }


def _review_statements(result: RqalphaConfigReviewResult) -> tuple[str, ...]:
    return (
        "RQAlpha remains the mature-framework target for A-share event-driven semantics.",
        "R4B does not prove local runtime execution.",
        "vectorbt and Qlib workflows must not be blocked by RQAlpha config/data-bundle gaps.",
        (
            "Next step should be isolated RQAlpha prototype only if data bundle/config "
            "requirements are resolved."
        ),
        f"Review status: {result.status}.",
    )
