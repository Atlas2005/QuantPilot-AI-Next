"""Shared intraday prediction engine for replay and live shadow."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, replace
from datetime import datetime
from typing import Any

from quantpilot_core.deepseek_multi_agent import (
    AgentFinding,
    AgentRiskFlag,
    AgentRole,
    validate_agent_finding,
)
from quantpilot_core.real_data_provider import (
    NormalizedIntradayBar,
    aggregate_intraday_bars,
    canonicalize_tdx_level1_symbol,
)
from quantpilot_core.tdx_manual_signal_bridge import export_signals
from quantpilot_core.tdx_prediction_integration.contracts import (
    CachedDeepSeekEvidence,
    CandidateEvidence,
    PredictionContext,
    PredictionEngineConfig,
    PredictionSignal,
    PredictionState,
    TDX_PREDICTION_ENGINE_VERSION,
)
from quantpilot_core.tdx_prediction_integration.intraday_features import (
    IntradayFeatureSnapshot,
    compute_intraday_features_v1,
)


CALIBRATION_LABEL = "deterministic_untrained_intraday_score_normalization_v1"


class TDXPredictionEngineV1:
    """Apply fixed intraday features to completed higher-timeframe bars."""

    def __init__(
        self,
        symbols: Sequence[str],
        *,
        config: PredictionEngineConfig | None = None,
        context: PredictionContext | None = None,
    ) -> None:
        self.symbols = tuple(
            dict.fromkeys(
                canonicalize_tdx_level1_symbol(symbol)
                for symbol in symbols
                if str(symbol).strip()
            )
        )
        if not self.symbols:
            raise ValueError("symbols must contain at least one symbol")
        self.config = config or PredictionEngineConfig()
        if self.config.feature_interval_minutes not in {3, 5, 15, 30}:
            raise ValueError("feature_interval_minutes must be 3, 5, 15, or 30")
        if self.config.min_feature_bars < 15:
            raise ValueError("min_feature_bars must be at least 15")
        if not 0 < self.config.material_probability_delta <= 1:
            raise ValueError("material_probability_delta must be in (0, 1]")
        if self.config.material_expected_move_delta <= 0:
            raise ValueError("material_expected_move_delta must be positive")
        self.context = context or PredictionContext()
        if self.context.deepseek_live_calls_enabled:
            raise ValueError("TDX prediction integration does not permit live DeepSeek calls")
        self._minute_bars: dict[str, list[NormalizedIntradayBar]] = {
            symbol: [] for symbol in self.symbols
        }
        self._minute_keys: set[tuple[str, datetime]] = set()
        self._last_feature_end: dict[str, datetime] = {}
        self._last_material: dict[str, PredictionSignal] = {}
        self._all_predictions: list[PredictionSignal] = []
        self._material_signals: list[PredictionSignal] = []

    @property
    def all_predictions(self) -> tuple[PredictionSignal, ...]:
        return tuple(self._all_predictions)

    @property
    def material_signals(self) -> tuple[PredictionSignal, ...]:
        return tuple(self._material_signals)

    def process_completed_bars(
        self,
        bars: Sequence[NormalizedIntradayBar],
    ) -> tuple[PredictionSignal, ...]:
        """Consume only immutable one-minute bars and return material changes."""

        accepted: list[NormalizedIntradayBar] = []
        for bar in sorted(bars, key=lambda item: (item.end, item.symbol, item.start)):
            if bar.symbol not in self._minute_bars:
                continue
            if bar.interval_minutes != 1:
                raise ValueError("prediction engine requires one-minute source bars")
            if bar.partial:
                continue
            key = (bar.symbol, bar.start)
            if key in self._minute_keys:
                continue
            existing = self._minute_bars[bar.symbol]
            if existing and bar.start < existing[-1].start:
                raise ValueError(f"out-of-order replay bar for {bar.symbol}")
            self._minute_keys.add(key)
            existing.append(bar)
            accepted.append(bar)
        if not accepted:
            return ()

        emitted: list[PredictionSignal] = []
        for cutoff in sorted({bar.end for bar in accepted}):
            due_symbols = self._due_symbols(cutoff)
            if not due_symbols:
                continue
            for symbol in due_symbols:
                feature_bar = self._latest_complete_feature_bar(symbol, cutoff)
                features = compute_intraday_features_v1(
                    self._minute_bars[symbol],
                    primary_interval_minutes=self.config.feature_interval_minutes,
                    cutoff=cutoff,
                )
                if features is None or feature_bar is None:
                    continue
                signal = self._prediction(features, feature_bar)
                material = self._is_material(signal)
                signal = replace(signal, material_change=material)
                self._all_predictions.append(signal)
                if material:
                    self._last_material[symbol] = signal
                    self._material_signals.append(signal)
                    emitted.append(signal)
        return tuple(emitted)

    def _feature_bars(
        self,
        symbol: str,
        cutoff: datetime,
    ) -> tuple[NormalizedIntradayBar, ...]:
        source = tuple(bar for bar in self._minute_bars[symbol] if bar.end <= cutoff)
        aggregated = aggregate_intraday_bars(
            source,
            interval_minutes=self.config.feature_interval_minutes,
        )
        return tuple(bar for bar in aggregated if not bar.partial and bar.end <= cutoff)

    def _latest_complete_feature_bar(
        self,
        symbol: str,
        cutoff: datetime,
    ) -> NormalizedIntradayBar | None:
        bars = self._feature_bars(symbol, cutoff)
        return bars[-1] if bars else None

    def _due_symbols(self, cutoff: datetime) -> tuple[str, ...]:
        due: list[str] = []
        for symbol in self.symbols:
            features = self._feature_bars(symbol, cutoff)
            if len(features) < self.config.min_feature_bars:
                continue
            latest = features[-1]
            if latest.end != cutoff or self._last_feature_end.get(symbol) == latest.end:
                continue
            self._last_feature_end[symbol] = latest.end
            due.append(symbol)
        return tuple(due)

    def _prediction(
        self,
        features: IntradayFeatureSnapshot,
        feature_bar: NormalizedIntradayBar,
    ) -> PredictionSignal:
        candidate = _candidate_for_cutoff(
            self.context.candidates.get(features.symbol),
            feature_bar.end,
        )
        calibrated = normalize_intraday_score_v1(features, candidate=candidate)
        entry_probability = calibrated["entry_probability"]
        continuation_probability = calibrated["continuation_probability"]
        exit_probability = calibrated["exit_probability"]
        expected_move = calibrated["expected_move"]
        volatility = max(features.atr_14_fraction_of_close, 0.0)
        drawdown = features.session_drawdown_from_high
        width = _clip(max(0.003, volatility * 1.5), 0.003, 0.02)
        invalidation_fraction = _clip(max(0.01, volatility * 2.5), 0.01, 0.06)
        target_fraction = _clip(max(0.015, abs(expected_move) * 1.75), 0.015, 0.10)
        state = _prediction_state(
            entry_probability=entry_probability,
            continuation_probability=continuation_probability,
            exit_probability=exit_probability,
            expected_move=expected_move,
            drawdown=drawdown,
        )
        reasons = list(calibrated["reason_codes"])
        reasons.append(
            f"intraday_primary_interval:{self.config.feature_interval_minutes}m"
        )
        evidence_refs = [
            f"tdx_intraday_features:{features.symbol}:{feature_bar.end.isoformat()}"
        ]
        context_data_asofs: list[str] = []
        components = [
            "quantpilot_core.tdx_prediction_integration.intraday_features.compute_intraday_features_v1",
            "quantpilot_core.real_data_provider.aggregate_intraday_bars",
            CALIBRATION_LABEL,
        ]
        if candidate is not None:
            reasons.append("daily_candidate_prior_present")
            reasons.append(
                f"daily_candidate_decision_session:{candidate.decision_session}"
            )
            evidence_refs.extend(candidate.evidence_refs)
            context_data_asofs.append(candidate.data_asof)
            components.append(candidate.source)
        cached = _deepseek_for_symbol(
            self.context.deepseek_evidence,
            features.symbol,
            cutoff=feature_bar.end,
        )
        if cached:
            reasons.append("cached_deepseek_evidence_present")
            evidence_refs.extend(
                evidence_ref
                for item in cached
                for evidence_ref in item.evidence_refs
            )
            context_data_asofs.extend(
                item.data_asof for item in cached if item.data_asof is not None
            )
            components.extend(item.source for item in cached)
            reasons.extend(
                f"deepseek_role:{item.role}" for item in cached
            )
            if any(item.risk_flag_count for item in cached):
                reasons.append("cached_deepseek_risk_flags_present")
        return PredictionSignal(
            symbol=features.symbol,
            decision_timestamp=feature_bar.end.isoformat(),
            data_cutoff_timestamp=feature_bar.end.isoformat(),
            state=state.value,
            entry_probability=round(entry_probability, 6),
            continuation_probability=round(continuation_probability, 6),
            exit_probability=round(exit_probability, 6),
            expected_move=round(expected_move, 6),
            expected_return=round(expected_move, 6),
            entry_zone_low=round(feature_bar.close * (1.0 - width), 4),
            entry_zone_high=round(feature_bar.close * (1.0 + width * 0.35), 4),
            invalidation_price=round(feature_bar.close * (1.0 - invalidation_fraction), 4),
            first_target_price=round(feature_bar.close * (1.0 + target_fraction), 4),
            reason_codes=tuple(dict.fromkeys(reasons)),
            evidence_refs=tuple(dict.fromkeys(evidence_refs)),
            context_data_asofs=tuple(dict.fromkeys(context_data_asofs)),
            source_components=tuple(dict.fromkeys(components)),
            intraday_score=round(float(calibrated["intraday_score"]), 6),
            calibration_label=CALIBRATION_LABEL,
        )

    def _is_material(self, current: PredictionSignal) -> bool:
        previous = self._last_material.get(current.symbol)
        if previous is None or previous.state != current.state:
            return True
        probability_delta = max(
            abs(current.entry_probability - previous.entry_probability),
            abs(current.continuation_probability - previous.continuation_probability),
            abs(current.exit_probability - previous.exit_probability),
        )
        return (
            probability_delta >= self.config.material_probability_delta
            or abs(current.expected_move - previous.expected_move)
            >= self.config.material_expected_move_delta
        )


def normalize_intraday_score_v1(
    features: IntradayFeatureSnapshot,
    *,
    candidate: CandidateEvidence | None = None,
) -> Mapping[str, Any]:
    """Bound explicitly intraday features without claiming trained calibration."""

    momentum_fast = _clip(features.momentum_3_feature_bars, -0.06, 0.06)
    momentum_slow = _clip(features.momentum_12_feature_bars, -0.12, 0.12)
    trend = _clip(features.trend_sma_3_over_sma_12_return, -0.06, 0.06)
    vwap_deviation = _clip(features.close_to_session_vwap_return, -0.08, 0.08)
    momentum_15m = _clip(
        float(features.momentum_2x15m_bars or 0.0),
        -0.08,
        0.08,
    )
    momentum_30m = _clip(
        float(features.momentum_2x30m_bars or 0.0),
        -0.12,
        0.12,
    )
    relative_volume = _clip(
        features.relative_volume_20_feature_bars - 1.0,
        -1.0,
        2.0,
    )
    volatility = max(features.atr_14_fraction_of_close, 0.0)
    drawdown = min(features.session_drawdown_from_high, 0.0)
    daily_prior = 0.0
    if candidate is not None:
        daily_prior = 0.10 * (candidate.confidence - 0.5) + 0.08 * (
            candidate.factor_composite_score - 0.5
        )
    strength = (
        3.0 * momentum_fast
        + 1.5 * momentum_slow
        + 2.0 * trend
        + 1.5 * vwap_deviation
        + 1.0 * momentum_15m
        + 0.75 * momentum_30m
        + 0.02 * relative_volume * (1.0 if momentum_fast >= 0 else -1.0)
        + daily_prior
        + 1.2 * drawdown
        - min(0.12, volatility * 0.75)
    )
    expected_move = _clip(
        0.35 * momentum_fast
        + 0.25 * momentum_slow
        + 0.20 * trend
        + 0.10 * momentum_15m
        + 0.10 * momentum_30m
        - 0.15 * volatility,
        -0.10,
        0.10,
    )
    entry = _clip(0.5 + strength, 0.02, 0.98)
    exit_probability = _clip(0.5 - strength - 1.5 * drawdown, 0.02, 0.98)
    continuation = _clip(
        0.5
        + 2.0 * momentum_fast
        + 1.2 * trend
        + 0.6 * momentum_15m
        - volatility,
        0.02,
        0.98,
    )
    reasons = [
        "intraday_trend_positive" if trend > 0 else "intraday_trend_nonpositive",
        (
            "intraday_momentum_positive"
            if momentum_fast > 0
            else "intraday_momentum_nonpositive"
        ),
        (
            "price_above_session_vwap"
            if vwap_deviation >= 0
            else "price_below_session_vwap"
        ),
        (
            "relative_volume_above_one"
            if relative_volume > 0
            else "relative_volume_at_or_below_one"
        ),
        (
            "session_drawdown_guard"
            if drawdown <= -0.05
            else "session_drawdown_within_guard"
        ),
        "probabilities_are_untrained_deterministic_normalization",
    ]
    return {
        "intraday_score": _clip(0.5 + strength, 0.0, 1.0),
        "entry_probability": entry,
        "continuation_probability": continuation,
        "exit_probability": exit_probability,
        "expected_move": expected_move,
        "reason_codes": tuple(reasons),
    }


def candidate_context_from_report(report: Mapping[str, Any] | None) -> Mapping[str, CandidateEvidence]:
    """Reuse the existing manual bridge to normalize daily candidate evidence."""

    if not report:
        return {}
    payload = report
    nested = report.get("daily_paper_loop")
    if isinstance(nested, Mapping):
        payload = nested
    output: dict[str, CandidateEvidence] = {}
    for signal in export_signals(payload):
        decision_session = signal.decision_session[:10]
        try:
            datetime.fromisoformat(decision_session)
        except ValueError as exc:
            raise ValueError(
                f"invalid candidate decision_session: {signal.decision_session}"
            ) from exc
        output[signal.symbol] = CandidateEvidence(
            symbol=signal.symbol,
            decision_session=signal.decision_session,
            data_asof=f"{decision_session}T15:00:00+08:00",
            confidence=_clip(float(signal.candidate_confidence), 0.0, 1.0),
            factor_composite_score=_clip(
                float(signal.factor_composite_score_raw), 0.0, 1.0
            ),
            evidence_refs=tuple(signal.evidence_refs),
        )
    return output


def cached_deepseek_evidence_from_payload(
    payload: Mapping[str, Any] | None,
) -> tuple[CachedDeepSeekEvidence, ...]:
    """Validate cached AgentFinding-shaped evidence without making live calls."""

    if not payload:
        return ()
    rows = payload.get("findings", ())
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        raise ValueError("cached DeepSeek evidence findings must be a sequence")
    output: list[CachedDeepSeekEvidence] = []
    payload_data_asof = payload.get("data_asof")
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise ValueError("cached DeepSeek finding must be a mapping")
        risk_flags = tuple(
            AgentRiskFlag(
                code=str(flag.get("code", "")),
                severity=str(flag.get("severity", "")),
                message=str(flag.get("message", "")),
            )
            for flag in raw.get("risk_flags", ())
            if isinstance(flag, Mapping)
        )
        finding = AgentFinding(
            role=AgentRole(str(raw["role"])),
            summary=str(raw.get("summary", "")),
            confidence=float(raw.get("confidence", 0.0)),
            evidence_refs=tuple(str(item) for item in raw.get("evidence_refs", ())),
            risk_flags=risk_flags,
        )
        errors = validate_agent_finding(finding)
        if errors:
            raise ValueError(f"invalid cached DeepSeek finding: {', '.join(errors)}")
        symbol = raw.get("symbol")
        raw_data_asof = raw.get("data_asof", raw.get("generated_at", payload_data_asof))
        data_asof = str(raw_data_asof) if raw_data_asof not in (None, "") else None
        if data_asof is not None:
            try:
                datetime.fromisoformat(data_asof)
            except ValueError as exc:
                raise ValueError(f"invalid context data_asof: {data_asof}") from exc
        output.append(
            CachedDeepSeekEvidence(
                symbol=str(symbol) if symbol not in (None, "") else None,
                data_asof=data_asof,
                role=finding.role.value,
                confidence=finding.confidence,
                summary=finding.summary,
                evidence_refs=finding.evidence_refs,
                risk_flag_count=len(finding.risk_flags),
            )
        )
    return tuple(output)


def prediction_signal_record(signal: PredictionSignal) -> Mapping[str, Any]:
    return {
        **asdict(signal),
        "timestamp": signal.decision_timestamp,
        "entry_zone": [signal.entry_zone_low, signal.entry_zone_high],
        "invalidation": signal.invalidation_price,
        "target": signal.first_target_price,
        "reason_code": "|".join(signal.reason_codes),
    }


def _deepseek_for_symbol(
    evidence: Sequence[CachedDeepSeekEvidence],
    symbol: str,
    *,
    cutoff: datetime,
) -> tuple[CachedDeepSeekEvidence, ...]:
    return tuple(
        item
        for item in evidence
        if item.symbol in (None, symbol)
        and item.data_asof is not None
        and _parse_context_asof(item.data_asof, cutoff) <= cutoff
    )


def _candidate_for_cutoff(
    candidate: CandidateEvidence | None,
    cutoff: datetime,
) -> CandidateEvidence | None:
    if candidate is None:
        return None
    if _parse_context_asof(candidate.data_asof, cutoff) > cutoff:
        return None
    return candidate


def _parse_context_asof(value: str, cutoff: datetime) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid context data_asof: {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=cutoff.tzinfo)
    return parsed.astimezone(cutoff.tzinfo)


def _prediction_state(
    *,
    entry_probability: float,
    continuation_probability: float,
    exit_probability: float,
    expected_move: float,
    drawdown: float,
) -> PredictionState:
    if drawdown <= -0.05:
        return PredictionState.INVALIDATED
    if exit_probability >= 0.66:
        return PredictionState.EXIT
    if entry_probability >= 0.62 and expected_move > 0:
        return PredictionState.ENTRY
    if continuation_probability >= 0.56 and entry_probability >= exit_probability:
        return PredictionState.HOLD
    if exit_probability >= 0.50 or expected_move < 0:
        return PredictionState.WEAKENING
    return PredictionState.WATCH


def _clip(value: float, minimum: float, maximum: float) -> float:
    if not math.isfinite(float(value)):
        return minimum
    return max(minimum, min(maximum, float(value)))


def engine_source_components() -> tuple[str, ...]:
    return (
        TDX_PREDICTION_ENGINE_VERSION,
        "tdx_prediction_integration.compute_intraday_features_v1",
        "intraday_aggregation.aggregate_intraday_bars",
        "tdx_manual_signal_bridge.export_signals",
        "deepseek_multi_agent.AgentFinding_validation",
    )
