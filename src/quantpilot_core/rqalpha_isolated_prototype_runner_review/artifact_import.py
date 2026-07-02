"""Import isolated prototype result artifacts without creating metrics."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

from quantpilot_core.rqalpha_isolated_prototype_runner_review.contracts import (
    RqalphaIsolatedPrototypeStatus,
    RqalphaPrototypeArtifactReviewResult,
)


DEFAULT_ARTIFACT_PATH = (
    "local_artifacts/backtest_prototypes/rqalpha/rqalpha_local_run_result.json"
)
ACCEPTED_METRIC_KEYS = (
    "total_return",
    "annualized_return",
    "max_drawdown",
    "sharpe",
    "trade_count",
    "turnover",
)


def review_rqalpha_prototype_artifact(
    project_root: Path | str = ".",
    artifact_path: str | None = None,
) -> RqalphaPrototypeArtifactReviewResult:
    """Review an existing JSON artifact and normalize explicit metric fields only."""

    relative_artifact_path = artifact_path or DEFAULT_ARTIFACT_PATH
    path = Path(project_root) / relative_artifact_path
    if not path.exists() or not path.is_file():
        return RqalphaPrototypeArtifactReviewResult(
            status=RqalphaIsolatedPrototypeStatus.EVIDENCE_MISSING.value,
            artifact_path=relative_artifact_path,
            exists=False,
            metrics_available=False,
            normalized_metrics=(),
            warnings=("No isolated prototype result artifact was found.",),
            errors=(),
        )

    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return RqalphaPrototypeArtifactReviewResult(
            status=RqalphaIsolatedPrototypeStatus.LOCAL_RUN_FAILED.value,
            artifact_path=relative_artifact_path,
            exists=True,
            metrics_available=False,
            normalized_metrics=(),
            warnings=(),
            errors=(f"Unable to read JSON artifact: {exc}",),
        )

    if not isinstance(loaded, dict):
        return RqalphaPrototypeArtifactReviewResult(
            status=RqalphaIsolatedPrototypeStatus.LOCAL_RUN_FAILED.value,
            artifact_path=relative_artifact_path,
            exists=True,
            metrics_available=False,
            normalized_metrics=(),
            warnings=(),
            errors=("Artifact root must be a JSON object.",),
        )

    metrics = _extract_explicit_metrics(loaded)
    metrics_available = bool(metrics)
    return RqalphaPrototypeArtifactReviewResult(
        status=(
            RqalphaIsolatedPrototypeStatus.LOCAL_RUN_SUCCEEDED.value
            if metrics_available
            else RqalphaIsolatedPrototypeStatus.OUTPUT_METRICS_MISSING.value
        ),
        artifact_path=relative_artifact_path,
        exists=True,
        metrics_available=metrics_available,
        normalized_metrics=metrics,
        warnings=(
            "Only explicit artifact metrics were imported; missing metrics were not created.",
        ),
        errors=(),
    )


def _extract_explicit_metrics(
    artifact: dict[str, Any],
) -> tuple[object, ...]:
    source_metrics = artifact.get("metrics")
    if not isinstance(source_metrics, dict):
        source_metrics = artifact

    metric_cls = getattr(
        importlib.import_module("quantpilot_core.rqalpha_ashare_backtest_adapter"),
        "RqalphaAshareBacktestMetric",
    )
    metrics: list[object] = []
    for key in ACCEPTED_METRIC_KEYS:
        if key not in source_metrics:
            continue
        value = source_metrics[key]
        if isinstance(value, (int, float, str, bool)) or value is None:
            metrics.append(metric_cls(name=key, value=value))
    return tuple(metrics)
