from __future__ import annotations

import importlib
import json
from pathlib import Path

from quantpilot_core.rqalpha_isolated_prototype_runner_review import (
    RqalphaIsolatedPrototypeStatus,
    build_rqalpha_isolated_prototype_runner_review_report,
    review_rqalpha_isolated_prototype_runner,
    review_rqalpha_prototype_artifact,
)


def _write_probe_summary(tmp_path: Path, payload: dict[str, object]) -> None:
    probe_dir = tmp_path / "local_artifacts" / "backtest_prototypes" / "rqalpha"
    probe_dir.mkdir(parents=True)
    (probe_dir / "rqalpha_probe_summary.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def _write_local_run_artifact(tmp_path: Path, payload: dict[str, object]) -> None:
    artifact_dir = tmp_path / "local_artifacts" / "backtest_prototypes" / "rqalpha"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "rqalpha_local_run_result.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def test_missing_probe_summary_returns_evidence_missing(tmp_path: Path) -> None:
    result = review_rqalpha_isolated_prototype_runner(tmp_path)

    assert result.status == RqalphaIsolatedPrototypeStatus.EVIDENCE_MISSING.value
    assert result.probe_importable is False
    assert result.production_ready is False
    assert result.blocks_other_frameworks is False


def test_importable_without_minimal_run_returns_local_run_not_attempted(
    tmp_path: Path,
) -> None:
    _write_probe_summary(
        tmp_path,
        {
            "rqalpha_importable": True,
            "rqalpha_version": "6.1.4",
            "minimal_local_run_attempted": False,
            "minimal_local_run_succeeded": False,
            "output_metrics_available": False,
        },
    )

    result = review_rqalpha_isolated_prototype_runner(tmp_path)

    assert result.status == RqalphaIsolatedPrototypeStatus.LOCAL_RUN_NOT_ATTEMPTED.value
    assert result.probe_importable is True
    assert result.probe_version == "6.1.4"
    assert result.command_spec.environment_path == ".venv-prototypes/rqalpha/"
    assert (
        result.command_spec.output_artifact_path
        == "local_artifacts/backtest_prototypes/rqalpha/rqalpha_local_run_result.json"
    )


def test_minimal_run_succeeded_without_metrics_returns_output_metrics_missing(
    tmp_path: Path,
) -> None:
    _write_probe_summary(
        tmp_path,
        {
            "rqalpha_importable": True,
            "minimal_local_run_attempted": True,
            "minimal_local_run_succeeded": True,
            "output_metrics_available": False,
        },
    )

    result = review_rqalpha_isolated_prototype_runner(tmp_path)

    assert result.status == RqalphaIsolatedPrototypeStatus.OUTPUT_METRICS_MISSING.value
    assert result.artifact_review is not None
    assert result.artifact_review.metrics_available is False
    assert result.production_ready is False


def test_artifact_import_extracts_only_explicit_metrics(tmp_path: Path) -> None:
    _write_local_run_artifact(
        tmp_path,
        {
            "status": "completed",
            "executed": True,
            "metrics": {
                "total_return": 0.12,
                "sharpe": 1.4,
                "unapproved_metric": 99,
            },
        },
    )

    result = review_rqalpha_prototype_artifact(tmp_path)

    assert result.exists is True
    assert result.metrics_available is True
    assert [metric.name for metric in result.normalized_metrics] == [
        "total_return",
        "sharpe",
    ]
    assert "annualized_return" not in {
        metric.name for metric in result.normalized_metrics
    }


def test_report_consumes_r4f_local_run_artifact_as_advisory_status(
    tmp_path: Path,
) -> None:
    _write_local_run_artifact(
        tmp_path,
        {
            "configured_bundle_path": "/Users/atlas/.rqalpha/bundle",
            "resolved_bundle_path": "/Users/atlas/.rqalpha/bundle/bundle",
            "bundle_exists": True,
            "minimal_local_run_attempted": True,
            "minimal_local_run_succeeded": True,
            "status": "output_metrics_missing",
            "explicit_metrics": {},
            "observed_trade_rows": None,
            "warnings": ["observed_trade_rows is evidence metadata only."],
            "conclusion": (
                "RQAlpha isolated local run returned without explicit allowed metrics."
            ),
        },
    )

    report = build_rqalpha_isolated_prototype_runner_review_report(tmp_path)
    local_summary = report["local_run_artifact_summary"]

    assert report["status"] == RqalphaIsolatedPrototypeStatus.OUTPUT_METRICS_MISSING.value
    assert report["production_ready"] is False
    assert report["blocks_other_frameworks"] is False
    assert local_summary["configured_bundle_path"] == "/Users/atlas/.rqalpha/bundle"
    assert local_summary["resolved_bundle_path"] == "/Users/atlas/.rqalpha/bundle/bundle"
    assert local_summary["bundle_exists"] is True
    assert local_summary["minimal_local_run_attempted"] is True
    assert local_summary["minimal_local_run_succeeded"] is True
    assert local_summary["status"] == "output_metrics_missing"
    assert local_summary["explicit_metrics"] == {}
    assert local_summary["observed_trade_rows"] is None
    assert "without explicit allowed metrics" in str(local_summary["conclusion"])


def test_observed_trade_rows_are_not_inferred_as_trade_count(tmp_path: Path) -> None:
    _write_local_run_artifact(
        tmp_path,
        {
            "status": "output_metrics_missing",
            "minimal_local_run_attempted": True,
            "minimal_local_run_succeeded": True,
            "explicit_metrics": {},
            "observed_trade_rows": 3,
        },
    )

    report = build_rqalpha_isolated_prototype_runner_review_report(tmp_path)
    artifact_summary = report["artifact_review_summary"]

    assert artifact_summary["observed_trade_rows"] == 3
    assert artifact_summary["explicit_metrics"] == {}
    assert artifact_summary["normalized_metric_names"] == ()
    assert artifact_summary["metrics_available"] is False


def test_report_includes_review_warning_and_next_actions(tmp_path: Path) -> None:
    report = build_rqalpha_isolated_prototype_runner_review_report(tmp_path)

    assert report["status"] == RqalphaIsolatedPrototypeStatus.EVIDENCE_MISSING.value
    assert report["next_actions"]
    assert report["production_ready"] is False
    assert report["blocks_other_frameworks"] is False
    assert any("does not run RQAlpha" in item for item in report["warnings"])


def test_package_exports_expected_symbols() -> None:
    module = importlib.import_module(
        "quantpilot_core.rqalpha_isolated_prototype_runner_review"
    )

    assert hasattr(module, "RqalphaIsolatedPrototypeStatus")
    assert hasattr(module, "RqalphaPrototypeCommandSpec")
    assert hasattr(module, "RqalphaPrototypeArtifactSchema")
    assert hasattr(module, "RqalphaPrototypeArtifactReviewResult")
    assert hasattr(module, "RqalphaIsolatedPrototypeReviewResult")
    assert hasattr(module, "review_rqalpha_isolated_prototype_runner")
    assert hasattr(module, "review_rqalpha_prototype_artifact")
    assert hasattr(module, "build_rqalpha_isolated_prototype_runner_review_report")


def test_production_package_contains_no_runtime_or_mutation_surfaces() -> None:
    package_root = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "quantpilot_core"
        / "rqalpha_isolated_prototype_runner_review"
    )
    forbidden_fragments = (
        "import rqalpha",
        "from rqalpha",
        "subprocess",
        "requests",
        "urllib",
        "httpx",
        "socket",
        "os.system",
        ".write_text",
        ".write(",
        "open(",
    )
    violations: list[str] = []

    for path in package_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        for fragment in forbidden_fragments:
            if fragment in text:
                violations.append(f"{path.name}: {fragment}")

    assert violations == []
