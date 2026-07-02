"""Review local RQAlpha evidence without importing or running the runtime."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quantpilot_core.rqalpha_data_bundle_config_review.contracts import (
    RqalphaConfigRequirement,
    RqalphaConfigReviewResult,
    RqalphaConfigReviewStatus,
    RqalphaEvidenceItem,
)


EVIDENCE_PATHS: tuple[tuple[str, str], ...] = (
    ("data/backtest_engine_candidates/rqalpha_preflight.json", "preflight_metadata"),
    ("docs/RQALPHA_PREFLIGHT_REVIEW.md", "preflight_review_doc"),
    ("docs/RQALPHA_ADAPTER_PREFLIGHT_SPIKE.md", "adapter_preflight_doc"),
    ("docs/modules/phase_6c_3a_rqalpha_preflight", "preflight_module_docs"),
    ("docs/modules/phase_6c_3b_rqalpha_isolated_prototype", "isolated_prototype_docs"),
    (
        "local_artifacts/backtest_prototypes/rqalpha/rqalpha_probe_summary.json",
        "isolated_probe_summary",
    ),
    ("tools/manual_backtest_prototypes/rqalpha_local_fixture_probe.py", "manual_probe_tool"),
    ("tools/manual_backtest_prototypes/summarize_rqalpha_probe.py", "probe_summary_tool"),
)

PROBE_SUMMARY_PATH = (
    "local_artifacts/backtest_prototypes/rqalpha/rqalpha_probe_summary.json"
)


def review_rqalpha_data_bundle_config(
    project_root: Path | str = ".",
) -> RqalphaConfigReviewResult:
    """Build a structured local review from historical RQAlpha prototype evidence."""

    root = Path(project_root)
    probe_summary = _load_probe_summary(root / PROBE_SUMMARY_PATH)
    evidence_items = tuple(
        _build_evidence_item(root, relative_path, evidence_type, probe_summary)
        for relative_path, evidence_type in EVIDENCE_PATHS
    )
    evidence_count = sum(item.exists for item in evidence_items)
    importable = probe_summary.get("rqalpha_importable") is True
    local_run_attempted = probe_summary.get("minimal_local_run_attempted") is True
    local_run_succeeded = probe_summary.get("minimal_local_run_succeeded") is True
    fake_fixture_supported = probe_summary.get("fake_fixture_direct_support_observed") is True
    data_bundle_observed = str(
        probe_summary.get("data_bundle_required_or_observed") or ""
    ).strip()
    data_bundle_required = (
        "required" in data_bundle_observed.lower()
        or bool(data_bundle_observed)
        or (importable and not local_run_succeeded)
    )
    config_required = importable and not local_run_succeeded

    requirements = (
        RqalphaConfigRequirement(
            name="rqalpha install/import evidence",
            required=True,
            status="satisfied" if importable else "missing",
            reason=(
                "Isolated probe summary reports import success."
                if importable
                else "No isolated install/import evidence was loaded from the probe summary."
            ),
        ),
        RqalphaConfigRequirement(
            name="data bundle requirement",
            required=True,
            status="required" if data_bundle_required else "not_observed",
            reason=(
                data_bundle_observed
                or "No local data bundle evidence was found in the loaded artifacts."
            ),
        ),
        RqalphaConfigRequirement(
            name="config requirement",
            required=True,
            status="required" if config_required else "not_observed",
            reason=(
                "A local config remains required before another isolated prototype."
                if config_required
                else "No explicit config blocker was loaded from available evidence."
            ),
        ),
        RqalphaConfigRequirement(
            name="local fixture execution evidence",
            required=True,
            status="satisfied" if local_run_succeeded else "not_proven",
            reason=(
                "Probe summary reports a minimal local run succeeded."
                if local_run_succeeded
                else "Existing evidence does not prove fake local fixture execution."
            ),
        ),
        RqalphaConfigRequirement(
            name="production/live readiness",
            required=False,
            status="not_ready",
            reason="R4B is review-only and never claims production or live readiness.",
        ),
    )

    status = _determine_status(
        evidence_count=evidence_count,
        importable=importable,
        local_run_succeeded=local_run_succeeded,
        fake_fixture_supported=fake_fixture_supported,
        data_bundle_required=data_bundle_required,
        config_required=config_required,
    )
    ready_for_runtime = (
        status == RqalphaConfigReviewStatus.READY_FOR_ISOLATED_PROTOTYPE.value
    )
    warnings = _build_warnings(evidence_count, probe_summary)
    next_actions = _build_next_actions(status)

    return RqalphaConfigReviewResult(
        status=status,
        evidence_items=evidence_items,
        requirements=requirements,
        warnings=warnings,
        next_actions=next_actions,
        ready_for_runtime=ready_for_runtime,
        production_ready=False,
        blocks_other_frameworks=False,
    )


def _build_evidence_item(
    root: Path,
    relative_path: str,
    evidence_type: str,
    probe_summary: dict[str, Any],
) -> RqalphaEvidenceItem:
    path = root / relative_path
    exists = path.exists()
    if not exists:
        summary = "missing"
    elif relative_path == PROBE_SUMMARY_PATH:
        summary = _summarize_probe_summary(probe_summary)
    elif path.is_dir():
        summary = "directory exists"
    else:
        summary = "file exists"
    return RqalphaEvidenceItem(
        path=relative_path,
        exists=exists,
        evidence_type=evidence_type,
        summary=summary,
    )


def _load_probe_summary(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(loaded, dict):
        return {}
    safe_keys = {
        "provider",
        "rqalpha_importable",
        "rqalpha_version",
        "minimal_local_run_attempted",
        "minimal_local_run_succeeded",
        "data_bundle_required_or_observed",
        "fake_fixture_direct_support_observed",
        "output_metrics_available",
        "conclusion",
        "warnings",
        "errors",
    }
    return {key: loaded[key] for key in safe_keys if key in loaded}


def _summarize_probe_summary(probe_summary: dict[str, Any]) -> str:
    if not probe_summary:
        return "probe summary exists but no safe top-level fields were loaded"
    parts = [
        f"importable={probe_summary.get('rqalpha_importable')}",
        f"version={probe_summary.get('rqalpha_version')}",
        f"local_run_succeeded={probe_summary.get('minimal_local_run_succeeded')}",
        f"fake_fixture_support={probe_summary.get('fake_fixture_direct_support_observed')}",
    ]
    return "; ".join(parts)


def _determine_status(
    *,
    evidence_count: int,
    importable: bool,
    local_run_succeeded: bool,
    fake_fixture_supported: bool,
    data_bundle_required: bool,
    config_required: bool,
) -> str:
    if evidence_count == 0:
        return RqalphaConfigReviewStatus.EVIDENCE_MISSING.value
    if data_bundle_required:
        return RqalphaConfigReviewStatus.DATA_BUNDLE_REQUIRED.value
    if config_required:
        return RqalphaConfigReviewStatus.CONFIG_REQUIRED.value
    if importable and (not local_run_succeeded or not fake_fixture_supported):
        return RqalphaConfigReviewStatus.LOCAL_FIXTURE_NOT_PROVEN.value
    if importable and local_run_succeeded and fake_fixture_supported:
        return RqalphaConfigReviewStatus.READY_FOR_ISOLATED_PROTOTYPE.value
    return RqalphaConfigReviewStatus.EVIDENCE_LOADED.value


def _build_warnings(
    evidence_count: int,
    probe_summary: dict[str, Any],
) -> tuple[str, ...]:
    warnings = [
        "R4B does not run RQAlpha and does not add an RQAlpha dependency.",
        "Missing RQAlpha config or data bundle evidence must not block vectorbt, Qlib, or multi-agent workflows.",
        "Production and live readiness remain false.",
    ]
    if evidence_count == 0:
        warnings.append("No historical RQAlpha evidence files were found under project_root.")
    for item in probe_summary.get("warnings", ()):
        if isinstance(item, str):
            warnings.append(item)
    return tuple(warnings)


def _build_next_actions(status: str) -> tuple[str, ...]:
    common = (
        "Keep RQAlpha optional and isolated from the main project environment.",
        "Do not create generic backtest metrics or a replacement engine inside QuantPilot.",
    )
    if status == RqalphaConfigReviewStatus.EVIDENCE_MISSING.value:
        return (
            "Recover or regenerate historical RQAlpha preflight/probe evidence before any runtime work.",
            *common,
        )
    if status in {
        RqalphaConfigReviewStatus.DATA_BUNDLE_REQUIRED.value,
        RqalphaConfigReviewStatus.CONFIG_REQUIRED.value,
        RqalphaConfigReviewStatus.LOCAL_FIXTURE_NOT_PROVEN.value,
    }:
        return (
            "Resolve explicit local RQAlpha data bundle and config requirements before another isolated prototype.",
            "Attempt an isolated local prototype only after those requirements are documented.",
            *common,
        )
    return (
        "Review whether an isolated local prototype is warranted before any runtime execution.",
        *common,
    )
