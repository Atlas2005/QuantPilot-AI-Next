"""Deterministic information agents over INFO1 normalized frames."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pandas as pd

from quantpilot_core.information_agents.contracts import (
    InformationAgentRole,
    InformationAgentSignal,
    InformationDecisionReport,
    InformationDirection,
    InformationHorizon,
)

POSITIVE_TERMS = (
    "beat",
    "buyback",
    "contract",
    "dividend",
    "earnings",
    "growth",
    "increase",
    "profit",
    "support",
    "upgrade",
)
NEGATIVE_TERMS = (
    "default",
    "downgrade",
    "fine",
    "investigation",
    "lawsuit",
    "loss",
    "penalty",
    "pledge",
    "risk",
    "warning",
)


def run_news_impact_agent(
    news_events: pd.DataFrame | None = None,
    announcement_events: pd.DataFrame | None = None,
    *,
    target: str | None = None,
) -> InformationAgentSignal:
    """Infer event-impact direction from normalized news and announcement facts."""

    news = _optional_frame(news_events, "news_events")
    announcements = _optional_frame(announcement_events, "announcement_events")
    _require_columns(news, ("datetime", "symbol", "evidence_text", "sentiment_score", "importance_score"), "news_events")
    _require_columns(announcements, ("datetime", "symbol", "evidence_text", "announcement_type", "title", "importance_score"), "announcement_events")

    resolved_target = target or _resolve_target((news, announcements))
    rows: list[tuple[float, float, str]] = []
    for row in news.to_dict("records"):
        importance = _numeric(row.get("importance_score"), 0.5)
        sentiment = _numeric(row.get("sentiment_score"), 0.0)
        contribution = _clamp(sentiment, -1.0, 1.0) * _clamp(importance, 0.0, 1.0)
        rows.append((contribution, importance, _evidence("news", row)))
    for row in announcements.to_dict("records"):
        importance = _numeric(row.get("importance_score"), 0.5)
        severity = _keyword_direction(
            row.get("announcement_type", ""),
            row.get("title", ""),
            row.get("evidence_text", ""),
        )
        rows.append((severity * _clamp(importance, 0.0, 1.0), importance, _evidence("announcement", row)))

    score, confidence = _weighted_score(rows)
    direction = _signed_direction(score, positive=InformationDirection.POSITIVE, negative=InformationDirection.NEGATIVE)
    if rows and _has_opposing_evidence(row[0] for row in rows) and abs(score) < 0.25:
        direction = InformationDirection.MIXED
        regime = "event_conflict"
    else:
        regime = "event_supportive" if score > 0.1 else "event_adverse" if score < -0.1 else "event_balanced"

    return InformationAgentSignal(
        agent_role=InformationAgentRole.NEWS_IMPACT,
        target=resolved_target,
        direction=direction,
        score=score,
        confidence=confidence,
        horizon=InformationHorizon.SHORT_TERM,
        regime=regime,
        evidence=tuple(item[2] for item in rows[:6]) or ("No normalized news or announcement rows were supplied.",),
        limitations=(
            "Announcement impact uses deterministic keyword severity when no sentiment field is present.",
            "This signal is an information summary only and does not assert outcome accuracy.",
        ),
    )


def run_northbound_flow_agent(
    northbound_holdings: pd.DataFrame,
    *,
    target: str | None = None,
) -> InformationAgentSignal:
    """Infer accumulation, distribution, or neutral state from holding changes."""

    frame = _required_frame(northbound_holdings, "northbound_holdings")
    _require_columns(
        frame,
        ("date", "symbol", "holding_shares", "holding_value", "holding_ratio", "net_buy_value", "evidence_text"),
        "northbound_holdings",
    )
    resolved_target = target or _resolve_target((frame,))
    if target and "symbol" in frame:
        frame = frame[frame["symbol"].astype(str) == target].copy()
    if frame.empty:
        return _neutral_signal(
            InformationAgentRole.NORTHBOUND_FLOW,
            resolved_target,
            InformationHorizon.MEDIUM_TERM,
            "northbound_no_matching_rows",
            ("No matching northbound holding rows were supplied.",),
            _northbound_limitations(),
        )

    frame = frame.sort_values(["symbol", "date"], kind="stable")
    scores: list[tuple[float, float, str]] = []
    for symbol, group in frame.groupby("symbol", sort=True):
        first = group.iloc[0]
        last = group.iloc[-1]
        share_delta = _numeric(last["holding_shares"], 0.0) - _numeric(first["holding_shares"], 0.0)
        value_delta = _numeric(last["holding_value"], 0.0) - _numeric(first["holding_value"], 0.0)
        ratio_delta = _numeric(last["holding_ratio"], 0.0) - _numeric(first["holding_ratio"], 0.0)
        net_buy = float(pd.to_numeric(group["net_buy_value"], errors="coerce").fillna(0.0).sum())
        denominator = max(abs(_numeric(first["holding_value"], 0.0)), abs(_numeric(last["holding_value"], 0.0)), 1.0)
        raw = (value_delta / denominator) + (ratio_delta * 4.0) + _clamp(net_buy / denominator, -1.0, 1.0) * 0.5
        if value_delta == 0 and share_delta != 0:
            raw += 0.2 if share_delta > 0 else -0.2
        score = _clamp(raw, -1.0, 1.0)
        evidence = (
            f"northbound:{symbol}:{first['date']}->{last['date']}:"
            f"value_delta={value_delta:.4g},ratio_delta={ratio_delta:.4g},net_buy={net_buy:.4g}"
        )
        scores.append((score, min(1.0, 0.45 + 0.1 * len(group)), evidence))

    score, confidence = _weighted_score(scores)
    direction = _signed_direction(
        score,
        positive=InformationDirection.ACCUMULATION,
        negative=InformationDirection.DISTRIBUTION,
    )
    regime = "northbound_accumulation" if score > 0.1 else "northbound_distribution" if score < -0.1 else "northbound_neutral"
    return InformationAgentSignal(
        agent_role=InformationAgentRole.NORTHBOUND_FLOW,
        target=resolved_target,
        direction=direction,
        score=score,
        confidence=confidence,
        horizon=InformationHorizon.MEDIUM_TERM,
        regime=regime,
        evidence=tuple(item[2] for item in scores[:6]),
        limitations=_northbound_limitations(),
    )


def run_liquidity_regime_agent(
    macro_policy_events: pd.DataFrame | None = None,
    margin_trading_snapshots: pd.DataFrame | None = None,
    moneyflow_snapshots: pd.DataFrame | None = None,
    stabilization_flow_clues: pd.DataFrame | None = None,
    *,
    target: str = "market",
) -> InformationAgentSignal:
    """Infer broad liquidity expansion, contraction, or neutral regime."""

    macro = _optional_frame(macro_policy_events, "macro_policy_events")
    margin = _optional_frame(margin_trading_snapshots, "margin_trading_snapshots")
    moneyflow = _optional_frame(moneyflow_snapshots, "moneyflow_snapshots")
    stabilization = _optional_frame(stabilization_flow_clues, "stabilization_flow_clues")
    _require_columns(macro, ("date", "impact_direction", "importance_score", "evidence_text"), "macro_policy_events")
    _require_columns(margin, ("date", "financing_balance", "financing_buy_value", "repayment_value", "evidence_text"), "margin_trading_snapshots")
    _require_columns(moneyflow, ("date", "main_net_inflow", "large_net_inflow", "retail_net_inflow", "evidence_text"), "moneyflow_snapshots")
    _require_columns(stabilization, ("date", "flow_value", "flow_direction", "confidence_score", "evidence_text"), "stabilization_flow_clues")

    rows: list[tuple[float, float, str]] = []
    for row in macro.to_dict("records"):
        direction = _policy_direction(row.get("impact_direction", ""))
        importance = _numeric(row.get("importance_score"), 0.5)
        rows.append((direction * _clamp(importance, 0.0, 1.0), importance, _evidence("macro", row)))

    rows.extend(_balance_change_scores(margin, "financing_balance", "margin"))
    for row in moneyflow.to_dict("records"):
        main = _numeric(row.get("main_net_inflow"), 0.0)
        large = _numeric(row.get("large_net_inflow"), 0.0)
        retail = _numeric(row.get("retail_net_inflow"), 0.0)
        scale = max(abs(main), abs(large), abs(retail), 1.0)
        score = _clamp((main + large * 0.7 - retail * 0.2) / scale, -1.0, 1.0)
        rows.append((score, 0.65, _evidence("moneyflow", row)))

    for row in stabilization.to_dict("records"):
        direction = _policy_direction(row.get("flow_direction", ""))
        confidence = _clamp(_numeric(row.get("confidence_score"), 0.5), 0.0, 1.0)
        amount = _numeric(row.get("flow_value"), 0.0)
        signed = direction if amount >= 0 else -direction
        rows.append((signed * confidence, confidence, _evidence("stabilization", row)))

    score, confidence = _weighted_score(rows)
    direction = _signed_direction(
        score,
        positive=InformationDirection.EXPANSION,
        negative=InformationDirection.CONTRACTION,
    )
    regime = "liquidity_expansion" if score > 0.1 else "liquidity_contraction" if score < -0.1 else "liquidity_neutral"
    return InformationAgentSignal(
        agent_role=InformationAgentRole.LIQUIDITY_REGIME,
        target=target,
        direction=direction,
        score=score,
        confidence=confidence,
        horizon=InformationHorizon.SHORT_TERM,
        regime=regime,
        evidence=tuple(item[2] for item in rows[:8]) or ("No normalized liquidity-related rows were supplied.",),
        limitations=(
            "Liquidity regime is a deterministic synthesis of supplied normalized rows only.",
            "This signal is not a macro forecast or execution instruction.",
        ),
    )


def build_information_decision_report(
    signals: Iterable[InformationAgentSignal],
    *,
    target: str | None = None,
) -> InformationDecisionReport:
    """Aggregate deterministic information-agent signals and expose conflicts."""

    material = tuple(signals)
    if not material:
        raise ValueError("signals must contain at least one InformationAgentSignal")
    if not all(isinstance(signal, InformationAgentSignal) for signal in material):
        raise TypeError("signals must contain only InformationAgentSignal values")

    aggregate_target = target or _common_signal_target(material)
    weighted = sum(signal.score * max(signal.confidence, 0.0) for signal in material)
    weight = sum(max(signal.confidence, 0.0) for signal in material) or float(len(material))
    aggregate_score = round(_clamp(weighted / weight, -1.0, 1.0), 6)
    aggregate_bias = _signed_direction(
        aggregate_score,
        positive=InformationDirection.POSITIVE,
        negative=InformationDirection.NEGATIVE,
    )
    conflicts = _signal_conflicts(material)
    if conflicts and abs(aggregate_score) < 0.25:
        aggregate_bias = InformationDirection.MIXED
    confidence = round(_clamp(weight / len(material), 0.0, 1.0), 6)
    limitations = tuple(dict.fromkeys(limit for signal in material for limit in signal.limitations))

    return InformationDecisionReport(
        target=aggregate_target,
        aggregate_bias=aggregate_bias,
        aggregate_score=aggregate_score,
        confidence=confidence,
        regime="conflicted" if conflicts else "aligned",
        signals=material,
        conflicts=conflicts,
        limitations=limitations,
    )


def _optional_frame(frame: pd.DataFrame | None, label: str) -> pd.DataFrame:
    if frame is None:
        return pd.DataFrame()
    return _required_frame(frame, label)


def _required_frame(frame: pd.DataFrame, label: str) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"{label} must be a pandas DataFrame")
    return frame.copy()


def _require_columns(frame: pd.DataFrame, columns: tuple[str, ...], label: str) -> None:
    if frame.empty:
        return
    missing = tuple(column for column in columns if column not in frame.columns)
    if missing:
        raise ValueError(f"{label} missing normalized columns: {', '.join(missing)}")


def _resolve_target(frames: Iterable[pd.DataFrame]) -> str:
    symbols = sorted(
        {
            str(symbol)
            for frame in frames
            if "symbol" in frame.columns
            for symbol in frame["symbol"].dropna().unique()
        }
    )
    if len(symbols) == 1:
        return symbols[0]
    if len(symbols) > 1:
        return "multi_symbol"
    return "market"


def _common_signal_target(signals: tuple[InformationAgentSignal, ...]) -> str:
    targets = sorted({signal.target for signal in signals})
    return targets[0] if len(targets) == 1 else "multi_target"


def _numeric(value: Any, default: float) -> float:
    if pd.isna(value):
        return default
    return float(value)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _weighted_score(rows: Iterable[tuple[float, float, str]]) -> tuple[float, float]:
    material = tuple(rows)
    if not material:
        return 0.0, 0.0
    weighted = sum(score * max(weight, 0.0) for score, weight, _ in material)
    total_weight = sum(max(weight, 0.0) for _, weight, _ in material) or float(len(material))
    score = round(_clamp(weighted / total_weight, -1.0, 1.0), 6)
    confidence = round(_clamp((total_weight / len(material)) * min(1.0, len(material) / 3.0), 0.0, 1.0), 6)
    return score, confidence


def _signed_direction(
    score: float,
    *,
    positive: InformationDirection,
    negative: InformationDirection,
) -> InformationDirection:
    if score > 0.1:
        return positive
    if score < -0.1:
        return negative
    return InformationDirection.NEUTRAL


def _keyword_direction(*values: object) -> float:
    text = " ".join(str(value).lower() for value in values)
    positive_hits = sum(term in text for term in POSITIVE_TERMS)
    negative_hits = sum(term in text for term in NEGATIVE_TERMS)
    if positive_hits > negative_hits:
        return 1.0
    if negative_hits > positive_hits:
        return -1.0
    return 0.0


def _policy_direction(value: object) -> float:
    normalized = str(value).strip().lower()
    if normalized in {"supportive", "positive", "inflow", "expansion", "easing", "loose", "accumulation"}:
        return 1.0
    if normalized in {"restrictive", "negative", "outflow", "contraction", "tightening", "distribution"}:
        return -1.0
    return _keyword_direction(normalized)


def _balance_change_scores(frame: pd.DataFrame, value_column: str, label: str) -> tuple[tuple[float, float, str], ...]:
    if frame.empty:
        return ()
    sort_columns = [column for column in ("symbol", "date") if column in frame.columns]
    ordered = frame.sort_values(sort_columns, kind="stable") if sort_columns else frame
    scores: list[tuple[float, float, str]] = []
    groups = ordered.groupby("symbol", sort=True) if "symbol" in ordered.columns else (("market", ordered),)
    for symbol, group in groups:
        first = group.iloc[0]
        last = group.iloc[-1]
        delta = _numeric(last[value_column], 0.0) - _numeric(first[value_column], 0.0)
        buys = float(pd.to_numeric(group.get("financing_buy_value", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum())
        repayments = float(pd.to_numeric(group.get("repayment_value", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum())
        denominator = max(abs(_numeric(first[value_column], 0.0)), abs(_numeric(last[value_column], 0.0)), 1.0)
        score = _clamp((delta + buys - repayments) / denominator, -1.0, 1.0)
        scores.append((score, min(1.0, 0.5 + 0.1 * len(group)), f"{label}:{symbol}:delta={delta:.4g},net_activity={(buys - repayments):.4g}"))
    return tuple(scores)


def _has_opposing_evidence(values: Iterable[float]) -> bool:
    material = tuple(values)
    return any(value > 0.1 for value in material) and any(value < -0.1 for value in material)


def _evidence(prefix: str, row: dict[str, Any]) -> str:
    timestamp = row.get("datetime", row.get("date", ""))
    symbol = row.get("symbol", "market")
    text = str(row.get("evidence_text", "")).strip()
    return f"{prefix}:{symbol}:{timestamp}:{text}"[:280]


def _neutral_signal(
    role: InformationAgentRole,
    target: str,
    horizon: InformationHorizon,
    regime: str,
    evidence: tuple[str, ...],
    limitations: tuple[str, ...],
) -> InformationAgentSignal:
    return InformationAgentSignal(
        agent_role=role,
        target=target,
        direction=InformationDirection.NEUTRAL,
        score=0.0,
        confidence=0.0,
        horizon=horizon,
        regime=regime,
        evidence=evidence,
        limitations=limitations,
    )


def _northbound_limitations() -> tuple[str, ...]:
    return (
        "Northbound holding frequency may be quarterly after 2024-08-19.",
        "Holding changes are information evidence only and do not identify causal price impact.",
    )


def _signal_conflicts(signals: tuple[InformationAgentSignal, ...]) -> tuple[str, ...]:
    positive = tuple(signal.agent_role.value for signal in signals if signal.score > 0.1)
    negative = tuple(signal.agent_role.value for signal in signals if signal.score < -0.1)
    if positive and negative:
        return (f"positive agents {positive} conflict with negative agents {negative}",)
    directional = {signal.direction for signal in signals if signal.direction is not InformationDirection.NEUTRAL}
    if InformationDirection.ACCUMULATION in directional and InformationDirection.CONTRACTION in directional:
        return ("northbound accumulation conflicts with liquidity contraction",)
    if InformationDirection.DISTRIBUTION in directional and InformationDirection.EXPANSION in directional:
        return ("northbound distribution conflicts with liquidity expansion",)
    return ()
