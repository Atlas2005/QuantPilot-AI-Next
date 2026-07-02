from __future__ import annotations

import importlib
import json
from pathlib import Path

from quantpilot_core.rqalpha_data_bundle_config_review import (
    RqalphaConfigReviewStatus,
    build_rqalpha_data_bundle_config_review_report,
    review_rqalpha_data_bundle_config,
)


def test_review_absent_evidence_returns_evidence_missing(tmp_path: Path) -> None:
    result = review_rqalpha_data_bundle_config(tmp_path)

    assert result.status == RqalphaConfigReviewStatus.EVIDENCE_MISSING.value
    assert result.ready_for_runtime is False
    assert result.production_ready is False
    assert result.blocks_other_frameworks is False
    assert all(not item.exists for item in result.evidence_items)


def test_review_fake_probe_summary_reports_import_without_runtime_readiness(
    tmp_path: Path,
) -> None:
    probe_dir = tmp_path / "local_artifacts" / "backtest_prototypes" / "rqalpha"
    probe_dir.mkdir(parents=True)
    (probe_dir / "rqalpha_probe_summary.json").write_text(
        json.dumps(
            {
                "provider": "rqalpha",
                "rqalpha_importable": True,
                "rqalpha_version": "6.1.4",
                "minimal_local_run_attempted": False,
                "minimal_local_run_succeeded": False,
                "data_bundle_required_or_observed": "Likely required.",
                "fake_fixture_direct_support_observed": False,
                "output_metrics_available": False,
                "environment_path": "not loaded",
            }
        ),
        encoding="utf-8",
    )

    result = review_rqalpha_data_bundle_config(tmp_path)

    assert result.status == RqalphaConfigReviewStatus.DATA_BUNDLE_REQUIRED.value
    assert result.ready_for_runtime is False
    assert result.production_ready is False
    assert result.blocks_other_frameworks is False
    requirement_statuses = {item.name: item.status for item in result.requirements}
    assert requirement_statuses["rqalpha install/import evidence"] == "satisfied"
    assert requirement_statuses["local fixture execution evidence"] == "not_proven"
    probe_item = next(
        item for item in result.evidence_items if item.evidence_type == "isolated_probe_summary"
    )
    assert "importable=True" in probe_item.summary


def test_report_includes_status_and_next_actions(tmp_path: Path) -> None:
    report = build_rqalpha_data_bundle_config_review_report(tmp_path)

    assert report["status"] == RqalphaConfigReviewStatus.EVIDENCE_MISSING.value
    assert report["next_actions"]
    assert any("R4B does not prove" in item for item in report["review_statements"])
    assert report["production_ready"] is False
    assert report["blocks_other_frameworks"] is False


def test_package_exports_expected_symbols() -> None:
    module = importlib.import_module("quantpilot_core.rqalpha_data_bundle_config_review")

    assert hasattr(module, "RqalphaConfigReviewStatus")
    assert hasattr(module, "RqalphaEvidenceItem")
    assert hasattr(module, "RqalphaConfigRequirement")
    assert hasattr(module, "RqalphaConfigReviewResult")
    assert hasattr(module, "review_rqalpha_data_bundle_config")
    assert hasattr(module, "build_rqalpha_data_bundle_config_review_report")


def test_source_does_not_import_runtime_or_call_network() -> None:
    package_root = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "quantpilot_core"
        / "rqalpha_data_bundle_config_review"
    )
    forbidden_fragments = (
        "import rqalpha",
        "from rqalpha",
        "requests.",
        "urllib.request",
        "http.client",
    )
    violations: list[str] = []

    for path in package_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        for fragment in forbidden_fragments:
            if fragment in text:
                violations.append(f"{path.name}: {fragment}")

    assert violations == []
