"""Local artifact loader for P44 manual isolated Qlib result imports."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

from quantpilot_core.controlled_optional_qlib_runtime_spike.contracts import (
    QlibRuntimeExecutionMode,
    QlibRuntimeResultRecord,
)
from quantpilot_core.manual_isolated_qlib_runtime_result_import_trial.contracts import (
    QlibImportTrialStatus,
    QlibResultArtifactLoadResult,
    QlibResultArtifactSourceType,
)


FACTOR_METRIC_FIELDS = ("ic", "rank_ic")
COST_AWARE_FIELDS = ("cost_aware_return_proxy", "cost_adjusted_score")


def load_qlib_result_artifact(
    artifact: Mapping[str, Any] | object | str | Path,
    *,
    source_type: str = QlibResultArtifactSourceType.DETERMINISTIC_FIXTURE.value,
) -> QlibResultArtifactLoadResult:
    """Load and normalize a local runtime-like result artifact."""

    blockers: list[str] = []
    warnings: list[str] = []
    if source_type not in {item.value for item in QlibResultArtifactSourceType}:
        blockers.append(f"unsupported_source_type:{source_type}")

    raw_artifact, artifact_source, source_blockers = _read_artifact(artifact)
    blockers.extend(source_blockers)

    if raw_artifact:
        blockers.extend(_artifact_blockers(raw_artifact))
        warnings.extend(_to_string_tuple(raw_artifact.get("warnings", ())))

    record = None
    if raw_artifact and not blockers:
        record = QlibRuntimeResultRecord(
            result_source=str(raw_artifact["result_source"]),
            dataset_id=str(raw_artifact["dataset_id"]),
            workflow_config_id=str(raw_artifact["workflow_config_id"]),
            metrics=_to_float_dict(raw_artifact.get("metrics", {})),
            missing_metric_reasons=_to_string_dict(raw_artifact.get("missing_metric_reasons", {})),
            profitability_claim=bool(raw_artifact.get("profitability_claim", False)),
            benchmark=str(raw_artifact["benchmark"]),
            stock_count=int(raw_artifact["stock_count"]),
            etf_count=int(raw_artifact["etf_count"]),
            execution_mode=str(raw_artifact["execution_mode"]),
            warnings=tuple(sorted(set(warnings))),
        )

    ok = record is not None and not blockers
    return QlibResultArtifactLoadResult(
        ok=ok,
        source_type=source_type,
        status=(
            QlibImportTrialStatus.ARTIFACT_LOADED.value
            if ok
            else QlibImportTrialStatus.IMPORT_REJECTED.value
        ),
        artifact_source=artifact_source,
        normalized_record=record,
        blockers=tuple(sorted(set(blockers))),
        warnings=tuple(sorted(set(warnings))),
        raw_artifact=raw_artifact,
    )


def _read_artifact(artifact: Mapping[str, Any] | object | str | Path) -> tuple[dict[str, Any], str, list[str]]:
    blockers: list[str] = []
    if isinstance(artifact, str | Path):
        source = str(artifact)
        if _is_remote(source):
            return {}, source, ["remote_artifact_source_rejected"]
        path = Path(artifact)
        if not path.exists():
            return {}, source, ["local_artifact_file_missing"]
        if not path.is_file():
            return {}, source, ["local_artifact_source_not_file"]
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return {}, source, [f"local_artifact_json_invalid:{exc.lineno}"]
        if not isinstance(loaded, dict):
            return {}, source, ["local_artifact_json_not_object"]
        return dict(loaded), source, blockers

    if is_dataclass(artifact):
        return asdict(artifact), "in_memory_dataclass", blockers
    if isinstance(artifact, Mapping):
        return dict(artifact), "in_memory_mapping", blockers
    return {}, "unsupported_artifact_object", ["artifact_object_not_supported"]


def _artifact_blockers(artifact: Mapping[str, Any]) -> tuple[str, ...]:
    blockers: list[str] = []
    required_fields = (
        "dataset_id",
        "workflow_config_id",
        "benchmark",
        "stock_count",
        "etf_count",
        "result_source",
        "execution_mode",
        "profitability_claim",
    )
    for field in required_fields:
        if field not in artifact:
            blockers.append(f"{field}_missing")

    if blockers:
        return tuple(blockers)

    for field in ("dataset_id", "workflow_config_id", "benchmark", "result_source"):
        if not str(artifact[field]).strip():
            blockers.append(f"{field}_missing")

    if _is_remote(str(artifact["result_source"])):
        blockers.append("remote_result_source_rejected")

    for field in ("stock_count", "etf_count"):
        try:
            if int(artifact[field]) < 0:
                blockers.append(f"{field}_negative")
        except (TypeError, ValueError):
            blockers.append(f"{field}_not_integer")

    if str(artifact["execution_mode"]) not in {
        QlibRuntimeExecutionMode.MANUAL_LOCAL_ONLY.value,
        QlibRuntimeExecutionMode.IMPORT_RESULT_ONLY.value,
    }:
        blockers.append("execution_mode_not_manual_or_import_only")

    if bool(artifact["profitability_claim"]):
        blockers.append("profitability_claim_rejected")

    metrics = artifact.get("metrics", {})
    missing_reasons = artifact.get("missing_metric_reasons", {})
    if not isinstance(metrics, Mapping):
        blockers.append("metrics_not_mapping")
    if not isinstance(missing_reasons, Mapping):
        blockers.append("missing_metric_reasons_not_mapping")
    if not isinstance(metrics, Mapping) or not isinstance(missing_reasons, Mapping):
        return tuple(blockers)

    metric_blockers = _metric_blockers(metrics, missing_reasons)
    blockers.extend(metric_blockers)
    try:
        _to_float_dict(metrics)
    except (TypeError, ValueError) as exc:
        blockers.append(str(exc))

    return tuple(blockers)


def _metric_blockers(metrics: Mapping[str, Any], missing_reasons: Mapping[str, Any]) -> tuple[str, ...]:
    blockers: list[str] = []
    if not any(field in metrics for field in FACTOR_METRIC_FIELDS):
        if not str(missing_reasons.get("ic_rank_ic", "")).strip():
            blockers.append("ic_rankic_metric_or_reason_missing")
    if not any(field in metrics for field in COST_AWARE_FIELDS):
        if not str(missing_reasons.get("cost_aware_metric", "")).strip():
            blockers.append("cost_aware_metric_or_reason_missing")
    return tuple(blockers)


def _to_float_dict(values: Mapping[str, Any]) -> dict[str, float]:
    converted: dict[str, float] = {}
    for key, value in values.items():
        try:
            converted[str(key)] = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"metric_not_numeric:{key}") from exc
    return converted


def _to_string_dict(values: Mapping[str, Any]) -> dict[str, str]:
    return {str(key): str(value) for key, value in values.items()}


def _to_string_tuple(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        return (values,)
    return tuple(str(value) for value in values)


def _is_remote(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"}
