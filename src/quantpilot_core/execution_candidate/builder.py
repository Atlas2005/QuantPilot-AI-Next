"""Build EXEC1 candidates from research, Qlib-style, and information signals."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any

from quantpilot_core.execution_candidate.contracts import (
    ExecutionCandidate,
    ExecutionCandidateReport,
    ExecutionDirection,
)


DEFAULT_EXEC1_TIMESTAMP = datetime(1970, 1, 1, tzinfo=UTC)


class ExecutionCandidateBuilder:
    """Deterministic transformer from research output to execution intent."""

    def __init__(
        self,
        *,
        strategy_id: str = "EXEC1",
        top_n: int = 5,
        signal_weight: float = 1.0,
        info_weight: float = 1.0,
        research_weight: float = 1.0,
        timestamp: datetime = DEFAULT_EXEC1_TIMESTAMP,
    ) -> None:
        if top_n <= 0:
            raise ValueError("top_n must be positive")
        if signal_weight < 0 or info_weight < 0 or research_weight < 0:
            raise ValueError("score weights must be non-negative")
        if signal_weight + info_weight + research_weight <= 0:
            raise ValueError("at least one score weight must be positive")

        self.strategy_id = strategy_id
        self.top_n = top_n
        self.signal_weight = signal_weight
        self.info_weight = info_weight
        self.research_weight = research_weight
        self.timestamp = timestamp

    def build(
        self,
        *,
        qlib_signals: Any,
        info_signals: Any,
        research_committee_output: Any,
    ) -> ExecutionCandidateReport:
        """Build a deterministic top-N candidate report."""

        signal_scores = _extract_scores(
            qlib_signals,
            score_fields=("signal_score", "score", "prediction", "pred", "value"),
            direction_fields=(),
        )
        info_scores = _extract_scores(
            info_signals,
            score_fields=("info_score", "aggregate_score", "score", "value"),
            direction_fields=("direction", "aggregate_bias"),
        )
        research_scores = _extract_scores(
            research_committee_output,
            score_fields=("research_score", "composite_score", "score"),
            direction_fields=("committee_stance", "stance"),
        )
        liquidity_scores = _extract_scores(
            info_signals,
            score_fields=("liquidity_score", "liquidity", "volume_score"),
            direction_fields=(),
            default_sign=1.0,
        )
        liquidity_scores.update(
            _extract_scores(
                qlib_signals,
                score_fields=("liquidity_score", "liquidity", "volume_score"),
                direction_fields=(),
                default_sign=1.0,
            )
        )

        symbols = tuple(sorted(set(signal_scores) | set(info_scores) | set(research_scores)))
        if not symbols:
            raise ValueError("at least one input signal with a symbol is required")

        scored = []
        for symbol in symbols:
            combined = _weighted_score(
                signal_scores.get(symbol, 0.0),
                info_scores.get(symbol, 0.0),
                research_scores.get(symbol, 0.0),
                signal_weight=self.signal_weight,
                info_weight=self.info_weight,
                research_weight=self.research_weight,
            )
            liquidity_score = _clamp(liquidity_scores.get(symbol, 1.0), 0.0, 1.0)
            confidence = _clamp(abs(combined), 0.0, 1.0)
            risk_score = _clamp(1.0 - (confidence * 0.7) - (liquidity_score * 0.3), 0.0, 1.0)
            scored.append(
                (
                    symbol,
                    combined,
                    ExecutionCandidate(
                        symbol=symbol,
                        direction=_direction(combined),
                        confidence=round(confidence, 6),
                        expected_return=round(combined, 6),
                        risk_score=round(risk_score, 6),
                        liquidity_score=round(liquidity_score, 6),
                        timestamp=self.timestamp,
                        lot_size=100,
                        metadata=MappingProxyType(
                            {
                                "market": "A-share",
                                "lot_constraint": "100_share_lot_metadata_only",
                                "lot_constraint_enforced": False,
                                "vectorbt_ready": True,
                                "score_components": {
                                    "signal_score": round(signal_scores.get(symbol, 0.0), 6),
                                    "info_score": round(info_scores.get(symbol, 0.0), 6),
                                    "research_score": round(research_scores.get(symbol, 0.0), 6),
                                },
                            }
                        ),
                    ),
                )
            )

        ranked = sorted(scored, key=lambda item: (-abs(item[1]), -item[1], item[0]))
        candidates = tuple(item[2] for item in ranked[: self.top_n])
        aggregate_score = _mean(candidate.expected_return for candidate in candidates)
        return ExecutionCandidateReport(
            candidates=candidates,
            aggregate_score=round(aggregate_score, 6),
            strategy_id=self.strategy_id,
        )


def build_execution_candidate_report(
    qlib_signals: Any,
    info_signals: Any,
    research_committee_output: Any,
    *,
    strategy_id: str = "EXEC1",
    top_n: int = 5,
    timestamp: datetime = DEFAULT_EXEC1_TIMESTAMP,
) -> ExecutionCandidateReport:
    """Compatibility wrapper for registry/tool use."""

    return ExecutionCandidateBuilder(strategy_id=strategy_id, top_n=top_n, timestamp=timestamp).build(
        qlib_signals=qlib_signals,
        info_signals=info_signals,
        research_committee_output=research_committee_output,
    )


def build_execution_candidate(
    qlib_signals: Any,
    info_signals: Any,
    research_committee_output: Any,
    *,
    strategy_id: str = "EXEC1",
    timestamp: datetime = DEFAULT_EXEC1_TIMESTAMP,
) -> ExecutionCandidate:
    """Return the top candidate from an EXEC1 candidate report."""

    report = build_execution_candidate_report(
        qlib_signals,
        info_signals,
        research_committee_output,
        strategy_id=strategy_id,
        top_n=1,
        timestamp=timestamp,
    )
    return report.candidates[0]


def _extract_scores(
    source: Any,
    *,
    score_fields: tuple[str, ...],
    direction_fields: tuple[str, ...],
    default_sign: float | None = None,
) -> dict[str, float]:
    scores: dict[str, float] = {}
    for row in _rows(source):
        symbol = _symbol(row)
        if symbol is None:
            continue
        score = _first_number(row, score_fields)
        if score is None:
            continue
        direction_value = _first_value(row, direction_fields)
        sign = default_sign if default_sign is not None else _direction_sign(direction_value)
        signed_score = score if direction_value is None else abs(score) * sign
        scores[symbol] = round(_clamp(signed_score, -1.0, 1.0), 6)
    return scores


def _rows(source: Any) -> tuple[Any, ...]:
    if source is None:
        return ()
    if hasattr(source, "to_dict") and callable(source.to_dict):
        try:
            records = source.to_dict("records")
        except TypeError:
            records = None
        if records is not None:
            return tuple(records)
    if isinstance(source, Mapping):
        if _looks_like_row(source):
            return (source,)
        return tuple({"symbol": key, **_value_mapping(value)} for key, value in source.items())
    if is_dataclass(source) or hasattr(source, "target"):
        return (source,)
    if isinstance(source, Iterable) and not isinstance(source, (str, bytes)):
        return tuple(source)
    return ()


def _value_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if is_dataclass(value):
        return asdict(value)
    return {"score": value}


def _looks_like_row(value: Mapping[str, Any]) -> bool:
    return any(key in value for key in ("symbol", "instrument", "target", "code"))


def _symbol(row: Any) -> str | None:
    value = _first_value(row, ("symbol", "instrument", "target", "code"))
    return str(value) if value not in (None, "") else None


def _first_number(row: Any, fields: tuple[str, ...]) -> float | None:
    value = _first_value(row, fields)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_value(row: Any, fields: tuple[str, ...]) -> Any:
    if not fields:
        return None
    if is_dataclass(row):
        row = asdict(row)
    if isinstance(row, Mapping):
        for field in fields:
            if field in row:
                return row[field]
        return None
    for field in fields:
        if hasattr(row, field):
            return getattr(row, field)
    return None


def _direction_sign(value: Any) -> float:
    normalized = _enum_value(value).lower()
    if normalized in {"bear", "negative", "distribution", "contraction", "short"}:
        return -1.0
    if normalized in {"neutral", "mixed", "flat"}:
        return 0.0
    return 1.0


def _enum_value(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def _weighted_score(
    signal_score: float,
    info_score: float,
    research_score: float,
    *,
    signal_weight: float,
    info_weight: float,
    research_weight: float,
) -> float:
    total_weight = signal_weight + info_weight + research_weight
    weighted = (
        signal_score * signal_weight
        + info_score * info_weight
        + research_score * research_weight
    ) / total_weight
    return round(_clamp(weighted, -1.0, 1.0), 6)


def _direction(score: float) -> ExecutionDirection:
    if score > 0:
        return "long"
    if score < 0:
        return "short"
    return "flat"


def _mean(values: Iterable[float]) -> float:
    items = tuple(values)
    if not items:
        return 0.0
    return sum(items) / len(items)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))
