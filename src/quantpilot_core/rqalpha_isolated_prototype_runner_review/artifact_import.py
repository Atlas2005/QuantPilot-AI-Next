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
            configured_bundle_path=None,
            resolved_bundle_path=None,
            bundle_exists=None,
            minimal_local_run_attempted=None,
            minimal_local_run_succeeded=None,
            explicit_metrics={},
            observed_trade_rows=None,
            conclusion=None,
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
            configured_bundle_path=None,
            resolved_bundle_path=None,
            bundle_exists=None,
            minimal_local_run_attempted=None,
            minimal_local_run_succeeded=None,
            explicit_metrics={},
            observed_trade_rows=None,
            conclusion=None,
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
            configured_bundle_path=None,
            resolved_bundle_path=None,
            bundle_exists=None,
            minimal_local_run_attempted=None,
            minimal_local_run_succeeded=None,
            explicit_metrics={},
            observed_trade_rows=None,
            conclusion=None,
            normalized_metrics=(),
            warnings=(),
            errors=("Artifact root must be a JSON object.",),
        )

    metrics = _extract_explicit_metrics(loaded)
    metrics_available = bool(metrics)
    explicit_metrics = _extract_explicit_metric_mapping(loaded)
    artifact_status = _artifact_status(loaded, metrics_available)
    return RqalphaPrototypeArtifactReviewResult(
        status=artifact_status,
        artifact_path=relative_artifact_path,
        exists=True,
        metrics_available=metrics_available,
        configured_bundle_path=_optional_string(loaded.get("configured_bundle_path")),
        resolved_bundle_path=_optional_string(loaded.get("resolved_bundle_path")),
        bundle_exists=_optional_bool(loaded.get("bundle_exists")),
        minimal_local_run_attempted=_optional_bool(
            loaded.get("minimal_local_run_attempted")
        ),
        minimal_local_run_succeeded=_optional_bool(
            loaded.get("minimal_local_run_succeeded")
        ),
        explicit_metrics=explicit_metrics,
        observed_trade_rows=_optional_int(loaded.get("observed_trade_rows")),
        conclusion=_optional_string(loaded.get("conclusion")),
        normalized_metrics=metrics,
        warnings=tuple(
            _string_items(loaded.get("warnings"))
            + [
                "Only explicit artifact metrics were imported; missing metrics were not created.",
            ]
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


def _extract_explicit_metric_mapping(artifact: dict[str, Any]) -> dict[str, object]:
    source_metrics = artifact.get("explicit_metrics")
    if not isinstance(source_metrics, dict):
        source_metrics = artifact.get("metrics")
    if not isinstance(source_metrics, dict):
        return {}
    return {
        key: value
        for key, value in source_metrics.items()
        if key in ACCEPTED_METRIC_KEYS
        and (isinstance(value, (int, float, str, bool)) or value is None)
    }


def _artifact_status(artifact: dict[str, Any], metrics_available: bool) -> str:
    status = artifact.get("status")
    if status in {item.value for item in RqalphaIsolatedPrototypeStatus}:
        return str(status)
    if status == "rqalpha_run_failed":
        return RqalphaIsolatedPrototypeStatus.LOCAL_RUN_FAILED.value
    if status == "local_run_succeeded":
        return RqalphaIsolatedPrototypeStatus.LOCAL_RUN_SUCCEEDED.value
    return (
        RqalphaIsolatedPrototypeStatus.LOCAL_RUN_SUCCEEDED.value
        if metrics_available
        else RqalphaIsolatedPrototypeStatus.OUTPUT_METRICS_MISSING.value
    )


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _string_items(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]
