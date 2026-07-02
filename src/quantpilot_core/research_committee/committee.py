"""Deterministic research committee over information signals and replay metrics."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import pandas as pd

from quantpilot_core.information_agents import (
    InformationAgentSignal,
    InformationDirection,
    build_information_decision_report,
)
from quantpilot_core.research_committee.contracts import (
    ResearchCandidateRanking,
    ResearchCommitteeReport,
    ResearchCommitteeStance,
    ResearchCommitteeView,
    ResearchEvidenceBucket,
)


POSITIVE_DIRECTIONS = {
    InformationDirection.POSITIVE,
    InformationDirection.ACCUMULATION,
    InformationDirection.EXPANSION,
}
NEGATIVE_DIRECTIONS = {
    InformationDirection.NEGATIVE,
    InformationDirection.DISTRIBUTION,
    InformationDirection.CONTRACTION,
}
NEUTRAL_DIRECTIONS = {InformationDirection.NEUTRAL, InformationDirection.MIXED}


def build_research_committee_report(
    information_signals: Iterable[InformationAgentSignal],
    replay_metrics: Mapping[str, Any] | pd.Series | pd.DataFrame,
    *,
    target: str | None = None,
) -> ResearchCommitteeReport:
    """Build a deterministic research diagnostic report from in-memory inputs."""

    signals = tuple(information_signals)
    if not signals:
        raise ValueError("information_signals must contain at least one InformationAgentSignal")
    if not all(isinstance(signal, InformationAgentSignal) for signal in signals):
        raise TypeError("information_signals must contain only InformationAgentSignal values")

    info_report = build_information_decision_report(signals, target=target)
    metrics = _coerce_replay_metrics(replay_metrics)
    report_target = target or _metric_target(metrics) or info_report.target

    information_score = info_report.aggregate_score
    replay_score = _replay_score(metrics)
    composite_score = round(_clamp((0.6 * information_score) + (0.4 * replay_score), -1.0, 1.0), 6)
    confidence = round(
        _clamp((0.6 * info_report.confidence) + (0.4 * _replay_confidence(metrics)), 0.0, 1.0),
        6,
    )

    bull_evidence = _information_buckets(signals, POSITIVE_DIRECTIONS, "bull") + _positive_replay_buckets(metrics)
    bear_evidence = _information_buckets(signals, NEGATIVE_DIRECTIONS, "bear") + _weak_replay_buckets(metrics)
    neutral_evidence = _information_buckets(signals, NEUTRAL_DIRECTIONS, "neutral")
    if not neutral_evidence and confidence < 0.45:
        neutral_evidence = (
            ResearchEvidenceBucket(
                source="committee_confidence",
                stance="neutral",
                score=0.0,
                confidence=confidence,
                evidence=("Committee confidence is low relative to supplied information and replay evidence.",),
                limitations=("Low confidence requires additional offline diagnostics before interpretation.",),
            ),
        )

    conflicts = _committee_conflicts(signals, information_score, replay_score, info_report.conflicts)
    views = (
        _information_view(info_report),
        _replay_view(metrics, replay_score),
        _committee_view(composite_score, confidence, conflicts),
    )

    dominant_thesis = _dominant_thesis(bull_evidence, bear_evidence, neutral_evidence)
    risk_thesis = _risk_thesis(metrics, confidence, conflicts, bear_evidence)
    limitations = tuple(
        dict.fromkeys(
            (
                *info_report.limitations,
                "Research committee output is diagnostic only and does not assert prediction accuracy.",
                "Replay metrics are computed from supplied in-memory inputs and are not production-readiness evidence.",
                "No execution, broker, API, credential, or model-service path is invoked.",
            )
        )
    )

    report = ResearchCommitteeReport(
        target=report_target,
        committee_stance=_stance_from_score(composite_score, conflicts),
        composite_score=composite_score,
        confidence=confidence,
        views=views,
        bull_evidence=bull_evidence,
        bear_evidence=bear_evidence,
        neutral_evidence=neutral_evidence,
        conflicts=conflicts,
        dominant_thesis=dominant_thesis,
        risk_thesis=risk_thesis,
        candidate_rankings=(),
        next_experiment_plan=_next_experiment_plan(metrics, conflicts, neutral_evidence),
        limitations=limitations,
    )
    ranking = _ranking_from_report(report, rank=1)
    return ResearchCommitteeReport(
        target=report.target,
        committee_stance=report.committee_stance,
        composite_score=report.composite_score,
        confidence=report.confidence,
        views=report.views,
        bull_evidence=report.bull_evidence,
        bear_evidence=report.bear_evidence,
        neutral_evidence=report.neutral_evidence,
        conflicts=report.conflicts,
        dominant_thesis=report.dominant_thesis,
        risk_thesis=report.risk_thesis,
        candidate_rankings=(ranking,),
        next_experiment_plan=report.next_experiment_plan,
        limitations=report.limitations,
    )


def rank_research_candidates(
    candidates: Iterable[ResearchCommitteeReport | Mapping[str, Any]],
) -> tuple[ResearchCandidateRanking, ...]:
    """Rank multiple research candidates by deterministic composite score."""

    reports: list[ResearchCommitteeReport] = []
    for candidate in candidates:
        if isinstance(candidate, ResearchCommitteeReport):
            reports.append(candidate)
            continue
        if not isinstance(candidate, Mapping):
            raise TypeError("candidates must contain ResearchCommitteeReport or mapping values")
        reports.append(
            build_research_committee_report(
                candidate["information_signals"],
                candidate["replay_metrics"],
                target=candidate.get("target"),
            )
        )
    if not reports:
        raise ValueError("candidates must contain at least one candidate")

    ordered = sorted(reports, key=lambda item: (-item.composite_score, -item.confidence, item.target))
    return tuple(_ranking_from_report(report, rank=index + 1) for index, report in enumerate(ordered))


def _coerce_replay_metrics(metrics: Mapping[str, Any] | pd.Series | pd.DataFrame) -> dict[str, Any]:
    if isinstance(metrics, pd.DataFrame):
        if metrics.empty:
            raise ValueError("replay_metrics DataFrame must be non-empty")
        if len(metrics) > 1:
            raise ValueError("replay_metrics DataFrame must contain exactly one row")
        return metrics.iloc[0].to_dict()
    if isinstance(metrics, pd.Series):
        return metrics.to_dict()
    if isinstance(metrics, Mapping):
        return dict(metrics)
    raise TypeError("replay_metrics must be a mapping, pandas Series, or one-row pandas DataFrame")


def _metric_target(metrics: Mapping[str, Any]) -> str | None:
    for key in ("target", "symbol", "instrument"):
        value = metrics.get(key)
        if value is not None and not pd.isna(value):
            return str(value)
    return None


def _replay_score(metrics: Mapping[str, Any]) -> float:
    total_return = _metric_float(metrics, "total_return", 0.0)
    sharpe = _metric_float(metrics, "sharpe", _metric_float(metrics, "sharpe_ratio", 0.0))
    max_drawdown = abs(_metric_float(metrics, "max_drawdown", 0.0))
    win_rate = _metric_float(metrics, "win_rate", 0.5)
    turnover = _metric_float(metrics, "turnover", 0.0)
    trades = _metric_float(metrics, "trades", _metric_float(metrics, "trade_count", 0.0))

    score = 0.0
    score += _clamp(total_return / 0.20, -1.0, 1.0) * 0.35
    score += _clamp(sharpe / 2.0, -1.0, 1.0) * 0.25
    score += _clamp((win_rate - 0.5) / 0.25, -1.0, 1.0) * 0.15
    score -= _clamp(max_drawdown / 0.20, 0.0, 1.0) * 0.15
    score -= _clamp(turnover / 2.0, 0.0, 1.0) * 0.05
    if trades <= 0:
        score -= 0.05
    return round(_clamp(score, -1.0, 1.0), 6)


def _replay_confidence(metrics: Mapping[str, Any]) -> float:
    known = sum(
        _has_metric(metrics, key)
        for key in ("total_return", "max_drawdown", "win_rate", "turnover")
    )
    known += int(_has_metric(metrics, "sharpe") or _has_metric(metrics, "sharpe_ratio"))
    known += int(_has_metric(metrics, "trades") or _has_metric(metrics, "trade_count"))
    trades = _metric_float(metrics, "trades", _metric_float(metrics, "trade_count", 0.0))
    trade_component = _clamp(trades / 5.0, 0.0, 1.0)
    return round(_clamp((known / 6.0) * 0.75 + trade_component * 0.25, 0.0, 1.0), 6)


def _information_buckets(
    signals: tuple[InformationAgentSignal, ...],
    directions: set[InformationDirection],
    stance: ResearchCommitteeStance,
) -> tuple[ResearchEvidenceBucket, ...]:
    buckets: list[ResearchEvidenceBucket] = []
    for signal in signals:
        if signal.direction not in directions:
            continue
        bucket_stance = "neutral" if signal.direction is InformationDirection.MIXED else stance
        buckets.append(
            ResearchEvidenceBucket(
                source=signal.agent_role.value,
                stance=bucket_stance,
                score=round(_clamp(signal.score, -1.0, 1.0), 6),
                confidence=round(_clamp(signal.confidence, 0.0, 1.0), 6),
                evidence=signal.evidence,
                limitations=signal.limitations,
            )
        )
    return tuple(buckets)


def _positive_replay_buckets(metrics: Mapping[str, Any]) -> tuple[ResearchEvidenceBucket, ...]:
    evidence: list[str] = []
    if _metric_float(metrics, "total_return", 0.0) > 0:
        evidence.append(f"Replay total_return is {_metric_float(metrics, 'total_return', 0.0):.4g}.")
    if _metric_float(metrics, "sharpe", _metric_float(metrics, "sharpe_ratio", 0.0)) > 0.5:
        evidence.append("Replay risk-adjusted metric is positive.")
    if _metric_float(metrics, "win_rate", 0.5) > 0.55:
        evidence.append(f"Replay win_rate is {_metric_float(metrics, 'win_rate', 0.5):.4g}.")
    if not evidence:
        return ()
    return (
        ResearchEvidenceBucket(
            source="replay_metrics",
            stance="bull",
            score=_replay_score(metrics),
            confidence=_replay_confidence(metrics),
            evidence=tuple(evidence),
            limitations=("Replay evidence is historical diagnostic output from supplied in-memory metrics.",),
        ),
    )


def _weak_replay_buckets(metrics: Mapping[str, Any]) -> tuple[ResearchEvidenceBucket, ...]:
    evidence: list[str] = []
    total_return = _metric_float(metrics, "total_return", 0.0)
    sharpe = _metric_float(metrics, "sharpe", _metric_float(metrics, "sharpe_ratio", 0.0))
    max_drawdown = abs(_metric_float(metrics, "max_drawdown", 0.0))
    turnover = _metric_float(metrics, "turnover", 0.0)
    trades = _metric_float(metrics, "trades", _metric_float(metrics, "trade_count", 0.0))
    if total_return < 0:
        evidence.append(f"Replay total_return is {total_return:.4g}.")
    if sharpe < 0:
        evidence.append("Replay risk-adjusted metric is negative.")
    if max_drawdown > 0.12:
        evidence.append(f"Replay max_drawdown magnitude is {max_drawdown:.4g}.")
    if turnover > 1.5:
        evidence.append(f"Replay turnover is {turnover:.4g}.")
    if trades <= 0:
        evidence.append("Replay metrics include no completed trades.")
    if not evidence:
        return ()
    return (
        ResearchEvidenceBucket(
            source="replay_metrics",
            stance="bear",
            score=_replay_score(metrics),
            confidence=_replay_confidence(metrics),
            evidence=tuple(evidence),
            limitations=("Replay weakness requires offline stress testing before interpretation.",),
        ),
    )


def _committee_conflicts(
    signals: tuple[InformationAgentSignal, ...],
    information_score: float,
    replay_score: float,
    information_conflicts: tuple[str, ...],
) -> tuple[str, ...]:
    conflicts = list(information_conflicts)
    if any(signal.direction in POSITIVE_DIRECTIONS for signal in signals) and any(
        signal.direction in NEGATIVE_DIRECTIONS for signal in signals
    ):
        conflicts.append("Committee received opposing positive and negative information signals.")
    if information_score > 0.2 and replay_score < -0.1:
        conflicts.append("Information score is supportive while replay score is weak.")
    if information_score < -0.2 and replay_score > 0.1:
        conflicts.append("Information score is pressured while replay score is supportive.")
    return tuple(dict.fromkeys(conflicts))


def _information_view(info_report: Any) -> ResearchCommitteeView:
    return ResearchCommitteeView(
        view_name="information_committee",
        stance=_stance_from_information_direction(info_report.aggregate_bias),
        score=info_report.aggregate_score,
        confidence=info_report.confidence,
        evidence=tuple(
            f"{signal.agent_role.value}:{signal.direction.value}:{signal.score:.4g}"
            for signal in info_report.signals
        ),
        risks=info_report.conflicts,
        limitations=info_report.limitations,
    )


def _replay_view(metrics: Mapping[str, Any], replay_score: float) -> ResearchCommitteeView:
    risks = tuple(bucket.evidence[0] for bucket in _weak_replay_buckets(metrics) if bucket.evidence)
    return ResearchCommitteeView(
        view_name="replay_committee",
        stance=_stance_from_score(replay_score, ()),
        score=replay_score,
        confidence=_replay_confidence(metrics),
        evidence=_replay_summary(metrics),
        risks=risks,
        limitations=("Replay view only summarizes supplied metrics; it does not validate live robustness.",),
    )


def _committee_view(
    composite_score: float,
    confidence: float,
    conflicts: tuple[str, ...],
) -> ResearchCommitteeView:
    return ResearchCommitteeView(
        view_name="synthesis_committee",
        stance=_stance_from_score(composite_score, conflicts),
        score=composite_score,
        confidence=confidence,
        evidence=(f"Composite score combines information and replay diagnostics: {composite_score:.4g}.",),
        risks=conflicts,
        limitations=("Synthesis is deterministic and bounded to offline research diagnostics.",),
    )


def _replay_summary(metrics: Mapping[str, Any]) -> tuple[str, ...]:
    fields = ("total_return", "sharpe", "sharpe_ratio", "max_drawdown", "win_rate", "turnover", "trades", "trade_count")
    return tuple(f"{field}={metrics[field]}" for field in fields if field in metrics and not pd.isna(metrics[field]))


def _dominant_thesis(
    bull_evidence: tuple[ResearchEvidenceBucket, ...],
    bear_evidence: tuple[ResearchEvidenceBucket, ...],
    neutral_evidence: tuple[ResearchEvidenceBucket, ...],
) -> str:
    bull_strength = _bucket_strength(bull_evidence)
    bear_strength = _bucket_strength(bear_evidence)
    neutral_strength = _bucket_strength(neutral_evidence)
    if bull_strength > max(bear_strength, neutral_strength):
        return _bucket_summary("Supportive evidence dominates", bull_evidence)
    if bear_strength > max(bull_strength, neutral_strength):
        return _bucket_summary("Pressure evidence dominates", bear_evidence)
    if neutral_evidence:
        return _bucket_summary("Neutral or mixed evidence dominates", neutral_evidence)
    return "No dominant evidence bucket is available from supplied inputs."


def _risk_thesis(
    metrics: Mapping[str, Any],
    confidence: float,
    conflicts: tuple[str, ...],
    bear_evidence: tuple[ResearchEvidenceBucket, ...],
) -> str:
    risks: list[str] = []
    drawdown = abs(_metric_float(metrics, "max_drawdown", 0.0))
    turnover = _metric_float(metrics, "turnover", 0.0)
    if drawdown > 0.12:
        risks.append(f"drawdown magnitude {drawdown:.4g}")
    if turnover > 1.5:
        risks.append(f"turnover {turnover:.4g}")
    if confidence < 0.5:
        risks.append(f"committee confidence {confidence:.4g}")
    if conflicts:
        risks.append("committee conflicts")
    if bear_evidence and not risks:
        risks.append("pressure evidence")
    return "Risk focus: " + ", ".join(risks) + "." if risks else "Risk focus: monitor replay fragility and missing evidence."


def _next_experiment_plan(
    metrics: Mapping[str, Any],
    conflicts: tuple[str, ...],
    neutral_evidence: tuple[ResearchEvidenceBucket, ...],
) -> tuple[str, ...]:
    plan = [
        "Extend replay window with the same deterministic signal construction.",
        "Stress transaction costs and slippage assumptions offline.",
        "Test capacity sensitivity using supplied turnover and volume diagnostics.",
        "Compare alternative signal thresholds in an offline replay matrix.",
    ]
    if conflicts:
        plan.append("Isolate conflicting information frames and rerun the committee synthesis.")
    if neutral_evidence:
        plan.append("Add missing or low-confidence information frames before broad interpretation.")
    if _metric_float(metrics, "turnover", 0.0) > 1.5:
        plan.append("Run a turnover-reduction sensitivity study on the replay inputs.")
    return tuple(dict.fromkeys(plan))


def _ranking_from_report(report: ResearchCommitteeReport, rank: int) -> ResearchCandidateRanking:
    info_view = next(view for view in report.views if view.view_name == "information_committee")
    replay_view = next(view for view in report.views if view.view_name == "replay_committee")
    evidence = tuple(
        bucket.evidence[0]
        for bucket in (*report.bull_evidence, *report.bear_evidence, *report.neutral_evidence)
        if bucket.evidence
    )[:6]
    return ResearchCandidateRanking(
        target=report.target,
        rank=rank,
        composite_score=report.composite_score,
        information_score=info_view.score,
        replay_score=replay_view.score,
        confidence=report.confidence,
        dominant_thesis=report.dominant_thesis,
        risk_thesis=report.risk_thesis,
        evidence=evidence,
        limitations=report.limitations,
    )


def _bucket_strength(buckets: tuple[ResearchEvidenceBucket, ...]) -> float:
    return round(sum(abs(bucket.score) * max(bucket.confidence, 0.0) for bucket in buckets), 6)


def _bucket_summary(prefix: str, buckets: tuple[ResearchEvidenceBucket, ...]) -> str:
    sources = ", ".join(bucket.source for bucket in buckets[:3])
    return f"{prefix}: {sources}."


def _stance_from_information_direction(direction: InformationDirection) -> ResearchCommitteeStance:
    if direction in POSITIVE_DIRECTIONS:
        return "bull"
    if direction in NEGATIVE_DIRECTIONS:
        return "bear"
    if direction is InformationDirection.MIXED:
        return "mixed"
    return "neutral"


def _stance_from_score(score: float, conflicts: tuple[str, ...]) -> ResearchCommitteeStance:
    if conflicts and abs(score) < 0.35:
        return "mixed"
    if score > 0.15:
        return "bull"
    if score < -0.15:
        return "bear"
    return "neutral"


def _metric_float(metrics: Mapping[str, Any], key: str, default: float) -> float:
    value = metrics.get(key, default)
    if value is None or pd.isna(value):
        return default
    return float(value)


def _has_metric(metrics: Mapping[str, Any], key: str) -> bool:
    return key in metrics and metrics[key] is not None and not pd.isna(metrics[key])


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
