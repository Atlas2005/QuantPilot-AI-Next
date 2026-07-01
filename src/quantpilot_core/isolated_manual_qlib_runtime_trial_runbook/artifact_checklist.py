"""Artifact checklist for P43 manual Qlib runtime trial."""

from __future__ import annotations

from quantpilot_core.isolated_manual_qlib_runtime_trial_runbook.contracts import (
    QlibTrialArtifactChecklist,
    QlibTrialArtifactChecklistItem,
    QlibTrialArtifactKind,
)


SOURCE_BY_KIND = {
    QlibTrialArtifactKind.DATASET_SPEC.value: "qlib_real_offline_workflow_spike",
    QlibTrialArtifactKind.WORKFLOW_CONFIG.value: "qlib_real_offline_workflow_spike",
    QlibTrialArtifactKind.FACTOR_MAPPING.value: "qlib_real_offline_workflow_spike",
    QlibTrialArtifactKind.COST_MODEL_ASSUMPTIONS.value: "qlib_real_offline_workflow_spike",
    QlibTrialArtifactKind.EXECUTION_ASSUMPTIONS.value: "controlled_optional_qlib_runtime_spike",
    QlibTrialArtifactKind.RESULT_RECORD_TEMPLATE.value: "controlled_optional_qlib_runtime_spike",
}


def build_qlib_trial_artifact_checklist(
    missing_kinds: tuple[str, ...] = (),
) -> QlibTrialArtifactChecklist:
    """Build deterministic required artifact checklist."""

    missing = set(missing_kinds)
    items = tuple(
        QlibTrialArtifactChecklistItem(
            kind=kind.value,
            required=True,
            present=kind.value not in missing,
            source_module=SOURCE_BY_KIND[kind.value],
            validation_note=f"{kind.value}_must_be_available_before_manual_runtime",
            blocker_if_missing=f"missing_required_artifact:{kind.value}",
        )
        for kind in QlibTrialArtifactKind
    )
    blockers = tuple(
        item.blocker_if_missing for item in items if item.required and not item.present
    )
    return QlibTrialArtifactChecklist(
        items=items,
        blockers=blockers,
        all_required_present=not blockers,
    )
