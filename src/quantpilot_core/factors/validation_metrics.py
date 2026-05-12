from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from statistics import mean

from quantpilot_core.factors.evaluation import simple_rank_correlation


class EvidenceQuality(str, Enum):
    toy_only = "toy_only"
    insufficient_sample = "insufficient_sample"
    exploratory = "exploratory"
    candidate = "candidate"
    rejected = "rejected"


class ValidationMetricStatus(str, Enum):
    not_computed = "not_computed"
    computed_toy_only = "computed_toy_only"
    invalid = "invalid"
    deferred = "deferred"


@dataclass(frozen=True)
class FactorMetricResult:
    factor_name: str
    metric_name: str
    metric_value: float | None
    status: ValidationMetricStatus
    evidence_quality: EvidenceQuality
    sample_size: int
    warnings: list[str]
    limitations: list[str]


@dataclass(frozen=True)
class FactorValidationReport:
    factor_name: str
    observation_count: int
    forward_return_count: int
    metric_results: list[FactorMetricResult]
    evidence_quality: EvidenceQuality
    alpha_claim_allowed: bool = False
    trading_ready: bool = False
    recommended_next_action: str = "needs_more_data"


PHASE_7B_LIMITATIONS = [
    "fake fixture only",
    "tiny sample",
    "no transaction costs",
    "no A-share execution rules",
    "no OOS",
    "no walk-forward",
    "no paper feedback",
    "no statistical significance",
]


def _evidence_quality_for_sample(sample_size: int) -> EvidenceQuality:
    if sample_size < 3:
        return EvidenceQuality.insufficient_sample
    return EvidenceQuality.toy_only


def compute_toy_information_coefficient(
    factor_values: list[float], forward_returns: list[float]
) -> FactorMetricResult:
    sample_size = min(len(factor_values), len(forward_returns))
    aligned_factors = factor_values[:sample_size]
    aligned_returns = forward_returns[:sample_size]
    warnings: list[str] = []

    if len(factor_values) != len(forward_returns):
        warnings.append("factor and forward-return lengths differ; truncated to aligned sample")
    if sample_size < 3:
        warnings.append("sample size is too small for meaningful inference")

    metric_value = simple_rank_correlation(aligned_factors, aligned_returns)
    status = ValidationMetricStatus.computed_toy_only
    if metric_value is None:
        status = ValidationMetricStatus.invalid
        warnings.append("toy IC-like metric unavailable or unstable")

    warnings.append("toy metric only; no statistical significance is claimed")

    return FactorMetricResult(
        factor_name="unknown",
        metric_name="toy_information_coefficient",
        metric_value=metric_value,
        status=status,
        evidence_quality=_evidence_quality_for_sample(sample_size),
        sample_size=sample_size,
        warnings=warnings,
        limitations=PHASE_7B_LIMITATIONS.copy(),
    )


def compute_grouped_forward_returns(
    factor_values: list[float], forward_returns: list[float], group_count: int = 3
) -> dict:
    if group_count < 1:
        raise ValueError("group_count must be at least 1")

    sample_size = min(len(factor_values), len(forward_returns))
    if sample_size < group_count or sample_size < 2:
        return {
            "groups": [],
            "warnings": ["sample size is too small for grouped forward returns"],
            "sample_size": sample_size,
        }

    paired = sorted(
        zip(factor_values[:sample_size], forward_returns[:sample_size]),
        key=lambda item: item[0],
    )
    groups = []
    for group_index in range(group_count):
        start = group_index * sample_size // group_count
        end = (group_index + 1) * sample_size // group_count
        bucket = paired[start:end]
        if not bucket:
            continue
        groups.append(
            {
                "group": group_index + 1,
                "count": len(bucket),
                "average_forward_return": mean(value for _, value in bucket),
            }
        )

    return {
        "groups": groups,
        "warnings": ["toy grouping only; no quantile significance is claimed"],
        "sample_size": sample_size,
    }


def build_factor_validation_report(
    factor_name: str, factor_values: list[float], forward_returns: list[float]
) -> FactorValidationReport:
    metric = compute_toy_information_coefficient(factor_values, forward_returns)
    metric = FactorMetricResult(
        factor_name=factor_name,
        metric_name=metric.metric_name,
        metric_value=metric.metric_value,
        status=metric.status,
        evidence_quality=metric.evidence_quality,
        sample_size=metric.sample_size,
        warnings=metric.warnings,
        limitations=metric.limitations,
    )

    evidence_quality = metric.evidence_quality
    if metric.sample_size < 3:
        evidence_quality = EvidenceQuality.insufficient_sample

    return FactorValidationReport(
        factor_name=factor_name,
        observation_count=len(factor_values),
        forward_return_count=len(forward_returns),
        metric_results=[metric],
        evidence_quality=evidence_quality,
        alpha_claim_allowed=False,
        trading_ready=False,
        recommended_next_action="needs_more_data",
    )
