"""Announcement signal event-study evaluation with post-availability labels."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import date, time
from statistics import median
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

import pandas as pd

from quantpilot_core.announcement_intelligence.contracts import AnnouncementImpactAssessment
from quantpilot_core.announcement_intelligence.research_committee_integration import (
    ANNOUNCEMENT_CONTENT_QUALITY_POLICY_VERSION,
    ANNOUNCEMENT_STRUCTURED_OUTPUT_SCHEMA_VERSION,
    assess_announcement_event_with_keyword_fallback,
)
from quantpilot_core.data_provider_normalization import canonicalize_a_share_symbol
from quantpilot_core.real_data_provider import CalendarError, NormalizedDailyBar, TradingCalendar


EVENT_STUDY_EVALUATOR_VERSION = "announcement_event_study_v1"
SIGNAL_IMPLEMENTATION_VERSION = f"keyword:{ANNOUNCEMENT_CONTENT_QUALITY_POLICY_VERSION};deepseek:{ANNOUNCEMENT_STRUCTURED_OUTPUT_SCHEMA_VERSION}"
LABEL_NAME = "post_availability_close_to_close"
HORIZONS = (1, 5, 20)
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
IDENTITY_LINEAGE_KEYS = {
    "deduplication_key",
    "event_id",
    "source_url",
    "source_url_or_lineage",
    "source_identifier",
    "raw_content_hash",
    "content_hash",
    "content_cache_key",
}


class EventStudyDataError(ValueError):
    """Raised when supplied event-study market data is internally inconsistent."""


@dataclass(frozen=True)
class EventSignalRecord:
    event_key: str
    event_id: str | None
    canonical_symbol: str
    normalized_pit_timestamp: str | None
    reference_session: date | None
    content_source: str
    content_quality_status: str
    full_text_available: bool
    keyword_direction: str
    keyword_confidence: float
    deepseek_direction: str | None
    deepseek_confidence: float | None
    deepseek_available: bool
    production_direction: str
    production_confidence: float
    production_source: str
    matching_status: str
    matching_method: str
    matching_reason: str | None
    assessment_metadata: Mapping[str, Any]


@dataclass(frozen=True)
class ForwardExcessReturnLabel:
    event_key: str
    horizon_sessions: int
    label_name: str
    label_status: str
    unavailable_reason: str | None
    reference_session: date | None
    exit_session: date | None
    stock_forward_return: float | None
    benchmark_forward_return: float | None
    excess_return: float | None
    outcome_direction: str | None
    used_sessions: tuple[date, ...] = ()


@dataclass(frozen=True)
class _MatchResult:
    assessment: AnnouncementImpactAssessment | None
    status: str
    method: str
    reason: str | None
    metadata: Mapping[str, Any]


def evaluate_announcement_event_study(
    events: Sequence[Mapping[str, Any]],
    assessments: Sequence[AnnouncementImpactAssessment] = (),
    *,
    calendar: TradingCalendar,
    stock_bars_by_symbol: Mapping[str, Sequence[NormalizedDailyBar]],
    benchmark_bars: Sequence[NormalizedDailyBar],
    benchmark_symbol: str = "000300.SH",
    benchmark_provenance: Mapping[str, Any] | None = None,
    stock_bar_provenance: Mapping[str, Any] | None = None,
    neutral_threshold: float = 0.0,
    run_config: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    """Evaluate comparable keyword, supplied DeepSeek, and production-selected arms."""

    _validate_neutral_threshold(neutral_threshold)
    raw_rows = [dict(item) for item in events]
    unique_rows, duplicate_audit = _dedupe_events(raw_rows, calendar)
    stock_indexes = {
        canonicalize_a_share_symbol(symbol): _bars_by_session(bars)
        for symbol, bars in stock_bars_by_symbol.items()
    }
    benchmark_index = _bars_by_session(benchmark_bars)
    records: list[EventSignalRecord] = []
    labels: dict[str, dict[str, ForwardExcessReturnLabel]] = {str(horizon): {} for horizon in HORIZONS}
    label_session_pairs: list[Mapping[str, Any]] = []

    event_key_counts: dict[str, int] = {}
    for row in unique_rows:
        symbol = _event_symbol(row)
        normalized_pit = _normalized_pit_text(row)
        reference_session = _safe_reference_session(row, calendar)
        keyword = assess_announcement_event_with_keyword_fallback(row)
        match = _match_deepseek_assessment(row, assessments)
        deepseek = match.assessment
        production = deepseek if deepseek is not None else keyword
        event_key = _unique_event_key(row, symbol, reference_session, event_key_counts)
        records.append(
            EventSignalRecord(
                event_key=event_key,
                event_id=_event_id(row),
                canonical_symbol=symbol,
                normalized_pit_timestamp=normalized_pit,
                reference_session=reference_session,
                content_source=str(row.get("content_source") or keyword.content_source),
                content_quality_status=str(row.get("content_quality_status") or keyword.content_quality_status),
                full_text_available=bool(row.get("full_text_available", keyword.full_text_available)),
                keyword_direction=keyword.event_impact_direction,
                keyword_confidence=keyword.confidence,
                deepseek_direction=deepseek.event_impact_direction if deepseek else None,
                deepseek_confidence=deepseek.confidence if deepseek else None,
                deepseek_available=deepseek is not None,
                production_direction=production.event_impact_direction,
                production_confidence=production.confidence,
                production_source=production.impact_assessment_source,
                matching_status=match.status,
                matching_method=match.method,
                matching_reason=match.reason,
                assessment_metadata=match.metadata,
            )
        )
        for horizon in HORIZONS:
            label = _label_for_event(
                event_key,
                reference_session=reference_session,
                horizon=horizon,
                calendar=calendar,
                stock_bars=stock_indexes.get(symbol, {}),
                benchmark_bars=benchmark_index,
                neutral_threshold=neutral_threshold,
            )
            labels[str(horizon)][event_key] = label
            if label.label_status == "available":
                label_session_pairs.append(
                    {"event_key": event_key, "horizon": horizon, "stock_sessions": label.used_sessions, "benchmark_sessions": label.used_sessions}
                )

    metrics = {
        arm: {str(horizon): _metrics_for_arm(records, labels[str(horizon)], arm, horizon=horizon) for horizon in HORIZONS}
        for arm in ("keyword_baseline", "deepseek_structured", "production_selected")
    }
    paired = {str(horizon): _paired_incremental_value(records, labels[str(horizon)]) for horizon in HORIZONS}
    base_benchmark_limitations = [
        "Benchmark choice is configurable; no one index perfectly represents every A-share style.",
        "Results use provider price-return fields and are not guaranteed total returns with dividend reinvestment.",
        "Corporate-action semantics depend on provider normalization.",
    ]
    supplied_benchmark = dict(benchmark_provenance or {})
    supplied_limitations = list(supplied_benchmark.pop("limitations", ()))
    benchmark_report = {
        "requested_benchmark_symbol": benchmark_symbol,
        "bar_count": len(benchmark_bars),
        "adjustment": "none",
        "return_methodology": "provider price-return fields: normalized pct_change percent units when present; otherwise close/previous_close - 1; compounded over exact real sessions",
        "adjustment_return_methodology": "provider price-return fields: normalized pct_change percent units when present; otherwise close/previous_close - 1; compounded over exact real sessions",
        "limitations": tuple(dict.fromkeys(base_benchmark_limitations + supplied_limitations)),
        **supplied_benchmark,
    }
    return {
        "run_config": {
            "label_name": LABEL_NAME,
            "neutral_threshold": neutral_threshold,
            "benchmark_symbol": benchmark_symbol,
            **dict(run_config or {}),
        },
        "event_universe": {
            "event_count": len(raw_rows),
            "unique_event_count": len(unique_rows),
            "unique_symbol_reference_session_count": duplicate_audit["unique_symbol_reference_session_count"],
        },
        "calendar_provenance": {"provider": calendar.provider.value, "session_count": len(calendar.sessions)},
        "stock_bar_provenance": _stock_bar_provenance(stock_indexes, stock_bar_provenance),
        "benchmark_provenance": benchmark_report,
        "arms": {
            "keyword_baseline": "canonical deterministic keyword fallback applied to every eligible event",
            "deepseek_structured": "supplied valid structured model assessments only; missing is unavailable",
            "production_selected": "valid structured model assessment when present, otherwise keyword baseline",
        },
        "event_records": [asdict(record) for record in records],
        "labels_by_horizon": {horizon: {key: asdict(label) for key, label in by_event.items()} for horizon, by_event in labels.items()},
        "metrics_by_arm_horizon": metrics,
        "paired_incremental_value": paired,
        "coverage": _coverage(records, labels),
        "duplicate_audit": duplicate_audit,
        "leakage_audit": _leakage_audit(records, labels, label_session_pairs, benchmark_symbol=benchmark_symbol),
        "limitations": [
            "This is a historical signal diagnostic, not a profitability, tradability, or statistical-significance claim.",
            "Repeated same-symbol/session announcements are retained and not treated as independent significance evidence.",
        ],
    }


def resolve_reference_session(pit_availability_timestamp: Any, calendar: TradingCalendar) -> date:
    """First real session whose close is strictly later than PIT availability."""

    ts = _shanghai_timestamp(pit_availability_timestamp)
    session = calendar.next_session(ts.date(), inclusive=True)
    if ts.date() == session and ts.time() < time(15, 0):
        return session
    return calendar.next_session(ts.date(), inclusive=False)


def _validate_neutral_threshold(value: Any) -> None:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("neutral_threshold must be numeric, finite, and non-negative") from exc
    if not math.isfinite(numeric) or numeric < 0:
        raise ValueError("neutral_threshold must be numeric, finite, and non-negative")


def decimal_session_return(bar: NormalizedDailyBar) -> float:
    """Return one decimal session return without forward filling or stale-price substitution."""

    if not _valid_close(bar.close):
        raise ValueError("invalid_close")
    if str(bar.trade_status or "1").strip() == "0":
        raise ValueError("suspended_or_non_trading")
    if bar.pct_change is not None:
        try:
            value = float(bar.pct_change)
        except (TypeError, ValueError):
            raise ValueError("malformed_pct_change")
        if not math.isfinite(value):
            raise ValueError("malformed_pct_change")
        decimal = value / 100.0
        if decimal <= -1.0:
            raise ValueError("return_below_minus_one")
        return decimal
    previous_close = _finite_positive_float(bar.previous_close)
    if previous_close is not None:
        decimal = (float(bar.close) / previous_close) - 1.0
        if decimal <= -1.0:
            raise ValueError("return_below_minus_one")
        return decimal
    if bar.previous_close is not None:
        raise ValueError("invalid_previous_close")
    raise ValueError("missing_return_field")


def _label_for_event(
    event_key: str,
    *,
    reference_session: date | None,
    horizon: int,
    calendar: TradingCalendar,
    stock_bars: Mapping[date, NormalizedDailyBar],
    benchmark_bars: Mapping[date, NormalizedDailyBar],
    neutral_threshold: float,
) -> ForwardExcessReturnLabel:
    if reference_session is None:
        return _unavailable_label(event_key, horizon, "reference_session_unavailable", None, None)
    reference_check = _validate_reference_anchor(reference_session, stock_bars, benchmark_bars)
    if reference_check is not None:
        return _unavailable_label(event_key, horizon, reference_check, reference_session, None)
    try:
        exit_session = calendar.shift_session(reference_session, horizon)
        sessions = tuple(session for session in calendar.sessions if reference_session < session <= exit_session)
        if len(sessions) != horizon:
            return _unavailable_label(event_key, horizon, "exit_session_unavailable", reference_session, None)
        stock_return = _compound_sessions(stock_bars, sessions, "stock")
        benchmark_return = _compound_sessions(benchmark_bars, sessions, "benchmark")
    except CalendarError:
        return _unavailable_label(event_key, horizon, "exit_session_unavailable", reference_session, None)
    except ValueError as exc:
        reason = str(exc).split(":", 1)[0][:80]
        return _unavailable_label(event_key, horizon, reason, reference_session, locals().get("exit_session"))
    excess = stock_return - benchmark_return
    return ForwardExcessReturnLabel(
        event_key=event_key,
        horizon_sessions=horizon,
        label_name=LABEL_NAME,
        label_status="available",
        unavailable_reason=None,
        reference_session=reference_session,
        exit_session=exit_session,
        stock_forward_return=round(stock_return, 10),
        benchmark_forward_return=round(benchmark_return, 10),
        excess_return=round(excess, 10),
        outcome_direction=_outcome_direction(excess, neutral_threshold),
        used_sessions=sessions,
    )


def _validate_reference_anchor(
    reference_session: date,
    stock_bars: Mapping[date, NormalizedDailyBar],
    benchmark_bars: Mapping[date, NormalizedDailyBar],
) -> str | None:
    stock = stock_bars.get(reference_session)
    if stock is None:
        return "missing_reference_stock_bar"
    if str(stock.trade_status or "1").strip() == "0":
        return "suspended_reference_stock_bar"
    if not _valid_close(stock.close):
        return "invalid_reference_stock_close"
    benchmark = benchmark_bars.get(reference_session)
    if benchmark is None:
        return "missing_reference_benchmark_bar"
    if not _valid_close(benchmark.close):
        return "invalid_reference_benchmark_close"
    return None


def _valid_close(value: Any) -> bool:
    return _finite_positive_float(value) is not None


def _finite_positive_float(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric) or numeric <= 0:
        return None
    return numeric


def _compound_sessions(bars: Mapping[date, NormalizedDailyBar], sessions: Sequence[date], label: str) -> float:
    compounded = 1.0
    for session in sessions:
        bar = bars.get(session)
        if bar is None:
            raise ValueError(f"missing_{label}_session")
        try:
            session_return = decimal_session_return(bar)
        except ValueError as exc:
            raise ValueError(f"{str(exc)}_{label}") from exc
        compounded *= 1.0 + session_return
    return compounded - 1.0


def _metrics_for_arm(records: Sequence[EventSignalRecord], labels: Mapping[str, ForwardExcessReturnLabel], arm: str, *, horizon: int) -> Mapping[str, Any]:
    eligible = list(records)
    label_available = [record for record in eligible if labels[record.event_key].label_status == "available"]
    signal_records = [record for record in eligible if _arm_direction(record, arm) is not None]
    pairs = [(record, labels[record.event_key]) for record in signal_records if labels[record.event_key].label_status == "available"]
    directional = [(record, label) for record, label in pairs if _prediction_direction(_arm_direction(record, arm)) in {"positive", "negative"}]
    hits = [(record, label) for record, label in directional if _prediction_direction(_arm_direction(record, arm)) == label.outcome_direction]
    return {
        "eligible_event_count": len(eligible),
        "label_available_count": len(label_available),
        "label_unavailable_count": len(eligible) - len(label_available),
        "signal_available_count": len(signal_records),
        "signal_unavailable_count": len(eligible) - len(signal_records),
        "signal_and_label_available_count": len(pairs),
        "prediction_coverage": _rate(len(signal_records), len(eligible)),
        "non_neutral_prediction_count": len(directional),
        "directional_hit_count": len(hits),
        "directional_hit_rate": _rate(len(hits), len(directional)),
        "positive_precision": _precision(pairs, arm, "positive"),
        "negative_precision": _precision(pairs, arm, "negative"),
        "balanced_accuracy": _balanced_accuracy(pairs, arm),
        "confusion_matrix": _confusion_matrix(pairs, arm),
        "mean_excess_return_by_predicted_direction": _excess_by_prediction(pairs, arm, mean=True),
        "median_excess_return_by_predicted_direction": _excess_by_prediction(pairs, arm, mean=False),
        "confidence_buckets": _confidence_buckets(eligible, labels, arm),
        "content_source_content_quality_coverage": _content_coverage(signal_records),
        "benchmark_and_horizon_provenance": {"label_name": LABEL_NAME, "horizon_sessions": horizon},
        "neutral_prediction_count": sum(1 for record in signal_records if _prediction_direction(_arm_direction(record, arm)) == "neutral"),
        "neutral_outcome_count": sum(1 for record in label_available if labels[record.event_key].outcome_direction == "neutral"),
    }


def _paired_incremental_value(records: Sequence[EventSignalRecord], labels: Mapping[str, ForwardExcessReturnLabel]) -> Mapping[str, Any]:
    paired_labeled = [
        record
        for record in records
        if record.deepseek_available and _arm_direction(record, "keyword_baseline") is not None and labels[record.event_key].label_status == "available"
    ]
    keyword_directional = [record for record in paired_labeled if _prediction_direction(record.keyword_direction) in {"positive", "negative"}]
    deepseek_directional = [record for record in paired_labeled if _prediction_direction(record.deepseek_direction) in {"positive", "negative"}]
    both_directional = [
        record
        for record in paired_labeled
        if _prediction_direction(record.keyword_direction) in {"positive", "negative"}
        and _prediction_direction(record.deepseek_direction) in {"positive", "negative"}
    ]
    keyword_pairs = [(record, labels[record.event_key]) for record in both_directional]
    deepseek_pairs = keyword_pairs
    keyword_hit = _directional_hit_rate(keyword_pairs, "keyword_baseline")
    deepseek_hit = _directional_hit_rate(deepseek_pairs, "deepseek_structured")
    return {
        "paired_labeled_event_count": len(paired_labeled),
        "paired_event_count": len(paired_labeled),
        "keyword_directional_count": len(keyword_directional),
        "deepseek_directional_count": len(deepseek_directional),
        "both_directional_event_count": len(both_directional),
        "keyword_directional_coverage": _rate(len(keyword_directional), len(paired_labeled)),
        "deepseek_directional_coverage": _rate(len(deepseek_directional), len(paired_labeled)),
        "keyword_hit_rate": keyword_hit,
        "deepseek_hit_rate": deepseek_hit,
        "absolute_hit_rate_lift": None if keyword_hit is None or deepseek_hit is None else round(deepseek_hit - keyword_hit, 6),
        "keyword_directional_excess": _directional_excess_stats(keyword_pairs, "keyword_baseline"),
        "deepseek_directional_excess": _directional_excess_stats(deepseek_pairs, "deepseek_structured"),
    }


def _dedupe_events(rows: Sequence[Mapping[str, Any]], calendar: TradingCalendar) -> tuple[list[Mapping[str, Any]], Mapping[str, Any]]:
    seen: set[str] = set()
    unique: list[Mapping[str, Any]] = []
    symbol_sessions: list[tuple[str, date | None]] = []
    for row in sorted(rows, key=lambda item: (_event_identity(item), _normalized_pit_text(item) or "", _event_symbol(item), _title(item))):
        symbol = _event_symbol(row)
        reference = _safe_reference_session(row, calendar)
        key = _event_identity(row)
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
        symbol_sessions.append((symbol, reference))
    unique_symbol_sessions = set(symbol_sessions)
    return unique, {
        "event_count": len(rows),
        "unique_event_count": len(unique),
        "unique_symbol_reference_session_count": len(unique_symbol_sessions),
        "repeated_symbol_session_count": len(symbol_sessions) - len(unique_symbol_sessions),
        "duplicate_count": len(rows) - len(unique),
    }


def _match_deepseek_assessment(row: Mapping[str, Any], assessments: Sequence[AnnouncementImpactAssessment]) -> _MatchResult:
    event_symbol = _event_symbol(row)
    event_pit = _normalized_pit_text(row)
    if event_pit is None:
        return _no_match("event_pit_unavailable", "not_applicable")
    candidates: list[tuple[AnnouncementImpactAssessment, str, str]] = []
    for item in assessments:
        if item.impact_assessment_source != "model_structured_output" or item.schema_validation_status != "passed":
            continue
        item_symbol = canonicalize_a_share_symbol(item.canonical_symbol)
        item_pit = _normalize_timestamp_text(item.pit_availability_timestamp)
        if item_symbol != event_symbol or item_pit != event_pit:
            continue
        method, token = _assessment_match_token(row, item)
        if method is not None:
            candidates.append((item, method, token))
    if not candidates:
        return _no_match("no_event_safe_assessment_match", "not_found")
    signatures = {_assessment_signature(item) for item, _, _ in candidates}
    if len(signatures) > 1:
        return _no_match("conflicting_duplicate_assessments", "ambiguous")
    method_order = {"deduplication_key": 0, "event_id": 1, "source_lineage": 2, "raw_content_hash": 3, "strict_fallback": 4, "title_only_unique": 5}
    best_rank = min(method_order[method] for _, method, _ in candidates)
    best = [candidate for candidate in candidates if method_order[candidate[1]] == best_rank]
    if len(best) > 1 and best[0][1] == "title_only_unique":
        return _no_match("ambiguous_duplicate_assessments", "ambiguous")
    item, method, _ = best[0]
    return _MatchResult(item, "matched", method, None, _assessment_metadata(item))


def _assessment_match_token(row: Mapping[str, Any], item: AnnouncementImpactAssessment) -> tuple[str | None, str | None]:
    event_tokens = _event_identity_tokens(row)
    assessment_tokens = _assessment_identity_tokens(item)
    for method in ("deduplication_key", "event_id", "source_lineage", "raw_content_hash"):
        overlap = event_tokens.get(method, set()) & assessment_tokens.get(method, set())
        if overlap:
            return method, sorted(overlap)[0]
    strict = _strict_fallback_identity(row)
    if strict and strict in assessment_tokens.get("strict_fallback", set()):
        return "strict_fallback", strict
    title = _title(row)
    if title and title == item.announcement_title and not any(event_tokens.values()):
        return "title_only_unique", title
    return None, None


def _event_identity_tokens(row: Mapping[str, Any]) -> dict[str, set[str]]:
    tokens = {"deduplication_key": set(), "event_id": set(), "source_lineage": set(), "raw_content_hash": set()}
    for key in ("deduplication_key",):
        _add_token(tokens["deduplication_key"], row.get(key))
    _add_token(tokens["event_id"], row.get("event_id"))
    for key in ("source_url", "url", "source_identifier", "source_url_or_lineage", "content_hash", "content_cache_key"):
        _add_token(tokens["source_lineage"], row.get(key))
    for key in ("raw_content_hash",):
        _add_token(tokens["raw_content_hash"], row.get(key))
    lineage = row.get("source_lineage")
    if isinstance(lineage, Mapping):
        for key, value in lineage.items():
            if key in IDENTITY_LINEAGE_KEYS:
                if key == "deduplication_key":
                    _add_token(tokens["deduplication_key"], value)
                elif key == "event_id":
                    _add_token(tokens["event_id"], value)
                elif key == "raw_content_hash":
                    _add_token(tokens["raw_content_hash"], value)
                else:
                    _add_token(tokens["source_lineage"], value)
    return tokens


def _assessment_identity_tokens(item: AnnouncementImpactAssessment) -> dict[str, set[str]]:
    tokens = {"deduplication_key": set(), "event_id": set(), "source_lineage": set(), "raw_content_hash": set(), "strict_fallback": set()}
    _add_token(tokens["source_lineage"], item.source_url_or_lineage)
    lineage = item.source_lineage or {}
    if isinstance(lineage, Mapping):
        for key, value in lineage.items():
            if key == "deduplication_key":
                _add_token(tokens["deduplication_key"], value)
            elif key == "event_id":
                _add_token(tokens["event_id"], value)
            elif key == "raw_content_hash":
                _add_token(tokens["raw_content_hash"], value)
            elif key in IDENTITY_LINEAGE_KEYS:
                _add_token(tokens["source_lineage"], value)
    strict = _strict_fallback_identity(
        {
            "symbol": item.canonical_symbol,
            "title": item.announcement_title,
            "first_available_time": item.pit_availability_timestamp,
            "source_url_or_lineage": item.source_url_or_lineage,
        }
    )
    if strict:
        tokens["strict_fallback"].add(strict)
    return tokens


def _strict_fallback_identity(row: Mapping[str, Any]) -> str | None:
    lineage = _lineage_text(row)
    pit = _normalized_pit_text(row)
    if not lineage or pit is None:
        return None
    return f"strict|{_event_symbol(row)}|{pit}|{_title(row)}|{lineage}"


def _event_identity(row: Mapping[str, Any]) -> str:
    tokens = _event_identity_tokens(row)
    if tokens["deduplication_key"]:
        return "deduplication_key|" + sorted(tokens["deduplication_key"])[0]
    for method in ("event_id", "source_lineage", "raw_content_hash"):
        if tokens[method]:
            return method + "|" + sorted(tokens[method])[0]
    strict = _strict_fallback_identity(row)
    if strict:
        return strict
    return f"fallback|{_event_symbol(row)}|{_normalized_pit_text(row) or 'pit_unavailable'}|{_title(row)}"


def _unique_event_key(row: Mapping[str, Any], symbol: str, reference_session: date | None, counts: dict[str, int]) -> str:
    ref = reference_session.isoformat() if reference_session else "reference_unavailable"
    base = f"{_event_identity(row)}|{symbol}|{ref}"
    count = counts.get(base, 0)
    counts[base] = count + 1
    return base if count == 0 else f"{base}|collision_{count + 1}"


def _safe_reference_session(row: Mapping[str, Any], calendar: TradingCalendar) -> date | None:
    try:
        return resolve_reference_session(_pit_value(row), calendar)
    except Exception:
        return None


def _unavailable_label(event_key: str, horizon: int, reason: str, reference_session: date | None, exit_session: date | None) -> ForwardExcessReturnLabel:
    return ForwardExcessReturnLabel(event_key, horizon, LABEL_NAME, "unavailable", reason[:80], reference_session, exit_session, None, None, None, None)


def _bars_by_session(bars: Sequence[NormalizedDailyBar]) -> dict[date, NormalizedDailyBar]:
    indexed: dict[date, NormalizedDailyBar] = {}
    for bar in bars:
        existing = indexed.get(bar.trade_date)
        if existing is None:
            indexed[bar.trade_date] = bar
        elif existing != bar:
            raise EventStudyDataError(f"conflicting_daily_bar:{bar.symbol}:{bar.trade_date.isoformat()}")
    return indexed


def _event_symbol(row: Mapping[str, Any]) -> str:
    value = row.get("canonical_symbol") or row.get("symbol")
    if value is None:
        affected = row.get("affected_symbols")
        value = affected[0] if isinstance(affected, (list, tuple)) and affected else str(affected or "").split(",", 1)[0]
    return canonicalize_a_share_symbol(str(value or "UNKNOWN"))


def _event_id(row: Mapping[str, Any]) -> str | None:
    value = row.get("event_id")
    return str(value) if value not in (None, "") else None


def _pit_value(row: Mapping[str, Any]) -> Any:
    return row.get("pit_availability_timestamp") or row.get("first_available_time") or row.get("publish_time")


def _normalized_pit_text(row: Mapping[str, Any]) -> str | None:
    return _normalize_timestamp_text(_pit_value(row))


def _normalize_timestamp_text(value: Any) -> str | None:
    try:
        return _shanghai_timestamp(value).isoformat()
    except Exception:
        return None


def _shanghai_timestamp(value: Any) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize(SHANGHAI_TZ)
    else:
        ts = ts.tz_convert(SHANGHAI_TZ)
    return ts


def _title(row: Mapping[str, Any]) -> str:
    return str(row.get("title") or row.get("headline") or "untitled announcement")


def _lineage_text(row: Mapping[str, Any]) -> str | None:
    for key in ("deduplication_key", "source_url", "url", "source_identifier", "source_url_or_lineage", "raw_content_hash", "content_hash"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _add_token(target: set[str], value: Any) -> None:
    if value in (None, ""):
        return
    target.add(str(value))


def _assessment_signature(item: AnnouncementImpactAssessment) -> tuple[Any, ...]:
    return _freeze(asdict(item))


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return tuple((key, _freeze(value[key])) for key in sorted(value))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _assessment_metadata(item: AnnouncementImpactAssessment) -> Mapping[str, Any]:
    return {
        "impact_assessment_source": item.impact_assessment_source,
        "model_status": item.model_status,
        "schema_validation_status": item.schema_validation_status,
        "cache_status": item.cache_status,
        "assessment_pit_timestamp": _normalize_timestamp_text(item.pit_availability_timestamp),
        "assessment_symbol": canonicalize_a_share_symbol(item.canonical_symbol),
        "source_url_or_lineage": item.source_url_or_lineage,
        "source_lineage": dict(item.source_lineage or {}),
    }


def _no_match(reason: str, method: str) -> _MatchResult:
    return _MatchResult(None, "unavailable", method, reason[:80], {})


def _outcome_direction(excess: float, threshold: float) -> str:
    if excess > threshold:
        return "positive"
    if excess < -threshold:
        return "negative"
    return "neutral"


def _prediction_direction(value: str | None) -> str | None:
    if value is None:
        return None
    return value if value in {"positive", "negative"} else "neutral"


def _arm_direction(record: EventSignalRecord, arm: str) -> str | None:
    if arm == "keyword_baseline":
        return record.keyword_direction
    if arm == "deepseek_structured":
        return record.deepseek_direction
    return record.production_direction


def _arm_confidence(record: EventSignalRecord, arm: str) -> float | None:
    if arm == "keyword_baseline":
        return record.keyword_confidence
    if arm == "deepseek_structured":
        return record.deepseek_confidence
    return record.production_confidence


def _rate(num: int, denom: int) -> float | None:
    return round(num / denom, 6) if denom else None


def _precision(pairs: Sequence[tuple[EventSignalRecord, ForwardExcessReturnLabel]], arm: str, direction: str) -> float | None:
    selected = [(record, label) for record, label in pairs if _prediction_direction(_arm_direction(record, arm)) == direction]
    return _rate(sum(1 for _, label in selected if label.outcome_direction == direction), len(selected))


def _balanced_accuracy(pairs: Sequence[tuple[EventSignalRecord, ForwardExcessReturnLabel]], arm: str) -> float | None:
    recalls = []
    for direction in ("positive", "negative"):
        actual = [(record, label) for record, label in pairs if label.outcome_direction == direction]
        if actual:
            recalls.append(sum(1 for record, _ in actual if _prediction_direction(_arm_direction(record, arm)) == direction) / len(actual))
    return round(sum(recalls) / len(recalls), 6) if recalls else None


def _confusion_matrix(pairs: Sequence[tuple[EventSignalRecord, ForwardExcessReturnLabel]], arm: str) -> Mapping[str, Mapping[str, int]]:
    matrix = {pred: {actual: 0 for actual in ("positive", "negative", "neutral")} for pred in ("positive", "negative", "neutral")}
    for record, label in pairs:
        matrix[_prediction_direction(_arm_direction(record, arm)) or "neutral"][label.outcome_direction or "neutral"] += 1
    return matrix


def _excess_by_prediction(pairs: Sequence[tuple[EventSignalRecord, ForwardExcessReturnLabel]], arm: str, *, mean: bool) -> Mapping[str, float | None]:
    result = {}
    for direction in ("positive", "negative", "neutral"):
        values = [label.excess_return for record, label in pairs if _prediction_direction(_arm_direction(record, arm)) == direction and label.excess_return is not None]
        result[direction] = _aggregate(values, mean=mean)
    return result


def _confidence_buckets(records: Sequence[EventSignalRecord], labels: Mapping[str, ForwardExcessReturnLabel], arm: str) -> Mapping[str, Mapping[str, int | float | None]]:
    buckets = {
        "0.00-0.33": _empty_bucket(),
        "0.33-0.66": _empty_bucket(),
        "0.66-1.00": _empty_bucket(),
        "unavailable": _empty_bucket(),
    }
    for record in records:
        confidence = _arm_confidence(record, arm)
        key = "unavailable" if confidence is None else "0.00-0.33" if confidence < 0.33 else "0.33-0.66" if confidence < 0.66 else "0.66-1.00"
        bucket = buckets[key]
        bucket["signal_count"] += 1
        label = labels[record.event_key]
        if label.label_status == "available":
            bucket["label_available_count"] += 1
            if _prediction_direction(_arm_direction(record, arm)) in {"positive", "negative"}:
                bucket["directional_prediction_count"] += 1
                if _prediction_direction(_arm_direction(record, arm)) == label.outcome_direction:
                    bucket["directional_hit_count"] += 1
    for bucket in buckets.values():
        bucket["directional_hit_rate"] = _rate(bucket["directional_hit_count"], bucket["directional_prediction_count"])
    return buckets


def _empty_bucket() -> dict[str, int | float | None]:
    return {
        "signal_count": 0,
        "label_available_count": 0,
        "directional_prediction_count": 0,
        "directional_hit_count": 0,
        "directional_hit_rate": None,
    }


def _content_coverage(records: Sequence[EventSignalRecord]) -> Mapping[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        key = f"{record.content_source}:{record.content_quality_status}"
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _directional_hit_rate(pairs: Sequence[tuple[EventSignalRecord, ForwardExcessReturnLabel]], arm: str) -> float | None:
    directional = [(record, label) for record, label in pairs if _prediction_direction(_arm_direction(record, arm)) in {"positive", "negative"}]
    return _rate(sum(1 for record, label in directional if _prediction_direction(_arm_direction(record, arm)) == label.outcome_direction), len(directional))


def _directional_excess_stats(pairs: Sequence[tuple[EventSignalRecord, ForwardExcessReturnLabel]], arm: str) -> Mapping[str, Any]:
    values = []
    for record, label in pairs:
        pred = _prediction_direction(_arm_direction(record, arm))
        if pred not in {"positive", "negative"} or label.excess_return is None:
            continue
        values.append(label.excess_return if pred == "positive" else -label.excess_return)
    return {"sample_count": len(values), "mean": _aggregate(values, mean=True), "median": _aggregate(values, mean=False)}


def _aggregate(values: Sequence[float | None], *, mean: bool) -> float | None:
    clean = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    if not clean:
        return None
    return round((sum(clean) / len(clean)) if mean else median(clean), 10)


def _coverage(records: Sequence[EventSignalRecord], labels: Mapping[str, Mapping[str, ForwardExcessReturnLabel]]) -> Mapping[str, Any]:
    return {
        "deepseek_available_count": sum(1 for record in records if record.deepseek_available),
        "keyword_available_count": len(records),
        "label_available_count_by_horizon": {
            horizon: sum(1 for item in by_event.values() if item.label_status == "available")
            for horizon, by_event in labels.items()
        },
    }


def _stock_bar_provenance(stock_indexes: Mapping[str, Mapping[date, NormalizedDailyBar]], supplied: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if supplied:
        return dict(supplied)
    return {
        "symbols": {
            symbol: {
                "requested_symbol": symbol,
                "selected_provider": "offline_or_injected",
                "fallback_used": False,
                "provider_attempts": [],
                "bar_count": len(bars),
                "date_range": [min(bars).isoformat(), max(bars).isoformat()] if bars else None,
                "adjustment": "none",
                "limitations": ["provider provenance was not supplied by caller"],
            }
            for symbol, bars in stock_indexes.items()
        }
    }


def _leakage_audit(
    records: Sequence[EventSignalRecord],
    labels: Mapping[str, Mapping[str, ForwardExcessReturnLabel]],
    label_session_pairs: Sequence[Mapping[str, Any]],
    *,
    benchmark_symbol: str,
) -> Mapping[str, Any]:
    return {
        "event_pit_timestamp_parse": _audit_count(
            [record.normalized_pit_timestamp is not None for record in records],
            unavailable=[record.normalized_pit_timestamp is None for record in records],
        ),
        "matched_deepseek_pit_equals_event_pit": _audit_count(
            [record.assessment_metadata.get("assessment_pit_timestamp") == record.normalized_pit_timestamp for record in records if record.deepseek_available],
        ),
        "matched_assessment_symbol_equals_event_symbol": _audit_count(
            [record.assessment_metadata.get("assessment_symbol") == record.canonical_symbol for record in records if record.deepseek_available],
        ),
        "reference_session_derived_from_pit": _audit_count(
            [record.reference_session is not None for record in records],
            unavailable=[record.reference_session is None for record in records],
        ),
        "exit_session_strictly_after_reference": _audit_count(
            [
                label.reference_session is not None and label.exit_session is not None and label.exit_session > label.reference_session
                for by_event in labels.values()
                for label in by_event.values()
                if label.label_status == "available"
            ],
        ),
        "stock_and_benchmark_sessions_identical": {
            "checked_count": len(label_session_pairs),
            "passed_count": len(label_session_pairs),
            "failed_count": 0,
            "unavailable_count": 0,
            "status": "enforced_by_constructor",
            "failure_reasons": [],
            "enforcement": "The same TradingCalendar session sequence is applied to stock and benchmark labels, and both bars must exist for every used session.",
        },
        "deepseek_assessments_supplied_inputs": {
            "checked_count": sum(1 for record in records if record.matching_status == "matched"),
            "passed_count": sum(1 for record in records if record.matching_status == "matched"),
            "failed_count": 0,
            "unavailable_count": 0,
            "status": "passed" if any(record.matching_status == "matched" for record in records) else "not_applicable",
            "failure_reasons": [],
            "cache_status_counts": _cache_status_counts(records),
        },
        "deepseek_assessments_cached": _deepseek_cache_audit(records),
        "no_live_deepseek_call_path": {
            "checked_count": 1,
            "passed_count": 1,
            "failed_count": 0,
            "unavailable_count": 0,
            "status": "enforced_by_constructor",
            "failure_reasons": [],
        },
        "evaluator_version": EVENT_STUDY_EVALUATOR_VERSION,
        "signal_implementation_version": SIGNAL_IMPLEMENTATION_VERSION,
        "benchmark_symbol": benchmark_symbol,
        "event_record_count": len(records),
        "assessment_metadata": [record.assessment_metadata for record in records if record.assessment_metadata],
    }


def _audit_count(values: Sequence[bool], unavailable: Sequence[bool] = ()) -> Mapping[str, Any]:
    unavailable_count = sum(1 for item in unavailable if item)
    checked = len(values)
    passed = sum(1 for item in values if item)
    failed = checked - passed
    if checked == 0 and unavailable_count == 0:
        status = "not_applicable"
    elif failed:
        status = "failed"
    elif unavailable_count and checked == 0:
        status = "not_verified"
    else:
        status = "passed"
    return {
        "checked_count": checked,
        "passed_count": passed,
        "failed_count": failed,
        "unavailable_count": unavailable_count,
        "status": status,
        "failure_reasons": ["audit_check_failed"] if failed else [],
    }


def _cache_status_counts(records: Sequence[EventSignalRecord]) -> Mapping[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        status = record.assessment_metadata.get("cache_status")
        if status:
            counts[str(status)] = counts.get(str(status), 0) + 1
    return dict(sorted(counts.items()))


def _deepseek_cache_audit(records: Sequence[EventSignalRecord]) -> Mapping[str, Any]:
    matched = [record for record in records if record.deepseek_available]
    cached = [record for record in matched if record.assessment_metadata.get("cache_status") == "cache_hit"]
    return {
        "checked_count": len(matched),
        "passed_count": len(cached),
        "failed_count": 0,
        "unavailable_count": len(matched) - len(cached),
        "status": "passed" if matched and len(cached) == len(matched) else "not_verified" if matched else "not_applicable",
        "failure_reasons": [],
    }
