"""Shared intraday prediction engine for replay and live shadow."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
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
    IntradayProbabilityProvider,
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
from quantpilot_core.daily_paper_loop.state import payload_digest


CALIBRATION_LABEL = "deterministic_untrained_atr_scaled_probability_mapping_v1"

ENTRY_PROBABILITY_THRESHOLD = 0.62
EXIT_PROBABILITY_THRESHOLD = 0.66
INVALIDATION_EXIT_PROBABILITY_THRESHOLD = 0.80

PREDICTION_STATE_LABEL_ZH = {
    PredictionState.WATCH.value: "观察",
    PredictionState.ENTRY.value: "买",
    PredictionState.HOLD.value: "持",
    PredictionState.WEAKENING.value: "弱",
    PredictionState.EXIT.value: "卖",
    PredictionState.INVALIDATED.value: "失效",
}


@dataclass
class _SignalLifecycle:
    active: bool = False
    previous_entry_setup: bool = False
    sequence: int = 0
    lifecycle_id: str | None = None
    invalidation_price: float | None = None


@dataclass(frozen=True)
class _LifecycleTransition:
    state: PredictionState
    lifecycle_id: str | None
    invalidation_price: float
    reason_code: str
    started: bool = False
    completed: bool = False


class TDXPredictionEngineV1:
    """Apply fixed intraday features to completed higher-timeframe bars."""

    def __init__(
        self,
        symbols: Sequence[str],
        *,
        config: PredictionEngineConfig | None = None,
        context: PredictionContext | None = None,
        probability_provider: IntradayProbabilityProvider | None = None,
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
        if self.config.prediction_provider not in {
            "deterministic_baseline",
            "v4_walk_forward",
        }:
            raise ValueError(
                "prediction_provider must be deterministic_baseline or v4_walk_forward"
            )
        if self.config.prediction_horizon_bars not in {5, 15, 30}:
            raise ValueError("prediction_horizon_bars must be 5, 15, or 30")
        if (
            probability_provider is not None
            and probability_provider.provider_id != self.config.prediction_provider
        ):
            raise ValueError("probability provider does not match prediction_provider")
        self.context = context or PredictionContext()
        if self.context.deepseek_live_calls_enabled:
            raise ValueError("TDX prediction integration does not permit live DeepSeek calls")
        self.probability_provider = probability_provider
        self._minute_bars: dict[str, list[NormalizedIntradayBar]] = {
            symbol: [] for symbol in self.symbols
        }
        self._minute_keys: set[tuple[str, datetime]] = set()
        self._last_feature_end: dict[str, datetime] = {}
        self._last_material: dict[str, PredictionSignal] = {}
        self._all_predictions: list[PredictionSignal] = []
        self._material_signals: list[PredictionSignal] = []
        self._visible_transition_signals: list[PredictionSignal] = []
        self._last_visible_state: dict[str, str] = {}
        self._lifecycles = {
            symbol: _SignalLifecycle() for symbol in self.symbols
        }
        self._lifecycle_started_count = 0
        self._lifecycle_completed_count = 0
        self._lifecycle_exit_count = 0
        self._lifecycle_invalidation_count = 0

    @property
    def all_predictions(self) -> tuple[PredictionSignal, ...]:
        return tuple(self._all_predictions)

    @property
    def material_signals(self) -> tuple[PredictionSignal, ...]:
        return tuple(self._material_signals)

    @property
    def visible_transition_signals(self) -> tuple[PredictionSignal, ...]:
        """Chart-facing lifecycle transitions, excluding WATCH and repeated states."""

        return tuple(self._visible_transition_signals)

    @property
    def lifecycle_counts(self) -> Mapping[str, int]:
        return {
            "lifecycle_started_count": self._lifecycle_started_count,
            "lifecycle_completed_count": self._lifecycle_completed_count,
            "open_lifecycle_count": sum(
                lifecycle.active for lifecycle in self._lifecycles.values()
            ),
            "exit_count": self._lifecycle_exit_count,
            "invalidation_count": self._lifecycle_invalidation_count,
        }

    @property
    def prediction_provider_status(self) -> Mapping[str, Any]:
        provider = self.probability_provider
        qualified = bool(provider is not None and provider.qualified)
        reason = self.config.prediction_provider_unavailable_reason
        if (
            self.config.prediction_provider != "deterministic_baseline"
            and provider is None
            and reason is None
        ):
            reason = "probability_provider_not_configured"
        if provider is not None and not qualified:
            reason = provider.fallback_reason or "model_artifact_not_qualified"
        if self.config.prediction_provider == "deterministic_baseline":
            reason = None
        return {
            "requested": self.config.prediction_provider,
            "active_when_applicable": (
                self.config.prediction_provider
                if qualified or self.config.prediction_provider == "deterministic_baseline"
                else "deterministic_baseline"
            ),
            "qualified": qualified,
            "fallback_active": (
                self.config.prediction_provider != "deterministic_baseline"
                and not qualified
            ),
            "fallback_reason": reason,
            "artifact": (
                dict(provider.artifact_metadata) if provider is not None else None
            ),
        }

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
                if (
                    signal.state != PredictionState.WATCH.value
                    and self._last_visible_state.get(symbol) != signal.state
                ):
                    self._last_visible_state[symbol] = signal.state
                    self._visible_transition_signals.append(signal)
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
        if self.config.prediction_start_timestamp is not None:
            start = datetime.fromisoformat(self.config.prediction_start_timestamp)
            if start.tzinfo is None:
                start = start.replace(tzinfo=cutoff.tzinfo)
            if cutoff < start.astimezone(cutoff.tzinfo):
                return ()
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
        deterministic = normalize_intraday_score_v1(features, candidate=candidate)
        deterministic_probabilities = {
            str(horizon): round(float(deterministic["entry_probability"]), 8)
            for horizon in (5, 15, 30)
        }
        requested_provider = self.config.prediction_provider
        provider = self.probability_provider
        active_provider = "deterministic_baseline"
        provider_qualified = False
        provider_fallback = requested_provider != "deterministic_baseline"
        provider_fallback_reason = (
            self.config.prediction_provider_unavailable_reason
            if provider_fallback else None
        )
        if provider_fallback and provider is None and provider_fallback_reason is None:
            provider_fallback_reason = "probability_provider_not_configured"
        model_artifact_digest = None
        provider_components: tuple[str, ...] = ()
        provider_reasons: tuple[str, ...] = ()
        calibration_label = CALIBRATION_LABEL
        horizon_probabilities = dict(deterministic_probabilities)
        if requested_provider != "deterministic_baseline" and provider is not None:
            provider_qualified = bool(provider.qualified)
            if not provider_qualified:
                provider_fallback_reason = (
                    provider.fallback_reason or "model_artifact_not_qualified"
                )
            else:
                output = provider.predict(
                    features,
                    decision_timestamp=feature_bar.end.isoformat(),
                )
                if output is None:
                    provider_fallback_reason = "qualified_model_not_applicable_at_timestamp"
                else:
                    required = {"5", "15", "30"}
                    if required - set(output.horizon_probabilities):
                        raise ValueError("trained provider omitted a required horizon probability")
                    candidate_probabilities = {
                        key: float(output.horizon_probabilities[key]) for key in required
                    }
                    if not all(
                        math.isfinite(value) and 0.0 <= value <= 1.0
                        for value in candidate_probabilities.values()
                    ):
                        raise ValueError("trained provider returned an invalid probability")
                    horizon_probabilities = {
                        key: round(value, 8)
                        for key, value in candidate_probabilities.items()
                    }
                    active_provider = output.provider_id
                    provider_fallback = False
                    provider_fallback_reason = None
                    model_artifact_digest = output.model_artifact_digest
                    provider_components = output.source_components
                    provider_reasons = output.reason_codes
                    calibration_label = output.calibration_label
        primary_probability = float(
            horizon_probabilities[str(self.config.prediction_horizon_bars)]
        )
        if active_provider == "deterministic_baseline":
            entry_probability = float(deterministic["entry_probability"])
            continuation_probability = float(deterministic["continuation_probability"])
            exit_probability = float(deterministic["exit_probability"])
            expected_move = float(deterministic["expected_move"])
            intraday_score = float(deterministic["intraday_score"])
        else:
            entry_probability = primary_probability
            continuation_probability = float(horizon_probabilities["5"])
            exit_probability = 1.0 - primary_probability
            expected_move = _clip(
                (2.0 * primary_probability - 1.0)
                * max(float(features.atr_14_fraction_of_close), 0.0005)
                * math.sqrt(float(self.config.prediction_horizon_bars)),
                -0.10,
                0.10,
            )
            intraday_score = primary_probability - 0.5
        volatility = max(features.atr_14_fraction_of_close, 0.0)
        width = _clip(max(0.003, volatility * 1.5), 0.003, 0.02)
        invalidation_fraction = _clip(max(0.01, volatility * 2.5), 0.01, 0.06)
        target_fraction = _clip(max(0.015, abs(expected_move) * 1.75), 0.015, 0.10)
        provisional_invalidation_price = feature_bar.close * (
            1.0 - invalidation_fraction
        )
        transition = _advance_signal_lifecycle_v1(
            self._lifecycles[features.symbol],
            symbol=features.symbol,
            decision_timestamp=feature_bar.end.isoformat(),
            completed_bar_low=float(feature_bar.low),
            entry_probability=entry_probability,
            continuation_probability=continuation_probability,
            exit_probability=exit_probability,
            expected_move=expected_move,
            proposed_invalidation_price=provisional_invalidation_price,
        )
        if transition.started:
            self._lifecycle_started_count += 1
        if transition.completed:
            self._lifecycle_completed_count += 1
            if transition.state is PredictionState.EXIT:
                self._lifecycle_exit_count += 1
            else:
                self._lifecycle_invalidation_count += 1
        reasons = (
            list(deterministic["reason_codes"])
            if active_provider == "deterministic_baseline"
            else ["deterministic_baseline_computed_for_benchmark_only"]
        )
        reasons.extend(provider_reasons)
        reasons.append(f"prediction_provider_requested:{requested_provider}")
        reasons.append(f"prediction_provider_used:{active_provider}")
        if provider_fallback:
            reasons.append("trained_probability_provider_fallback")
            if provider_fallback_reason:
                reasons.append(f"provider_fallback_reason:{provider_fallback_reason}")
        reasons.append(transition.reason_code)
        if transition.lifecycle_id is not None:
            reasons.append(f"signal_lifecycle_id:{transition.lifecycle_id}")
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
            (
                CALIBRATION_LABEL
                if active_provider == "deterministic_baseline"
                else f"benchmark_only:{CALIBRATION_LABEL}"
            ),
        ]
        components.extend(provider_components)
        if candidate is not None:
            reasons.append(
                "daily_candidate_prior_present"
                if active_provider == "deterministic_baseline"
                else "daily_candidate_context_present_not_trained_model_feature"
            )
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
        decision_timestamp = feature_bar.end.isoformat()
        state = transition.state.value
        signal_id = "tdx-signal-" + payload_digest(
            {
                "symbol": features.symbol,
                "decision_timestamp": decision_timestamp,
                "state": state,
                "experience_plan_id": (
                    candidate.experience_plan_id if candidate is not None else None
                ),
            }
        )[:24]
        return PredictionSignal(
            symbol=features.symbol,
            decision_timestamp=decision_timestamp,
            data_cutoff_timestamp=decision_timestamp,
            state=state,
            entry_probability=round(entry_probability, 6),
            continuation_probability=round(continuation_probability, 6),
            exit_probability=round(exit_probability, 6),
            expected_move=round(expected_move, 6),
            expected_return=round(expected_move, 6),
            entry_zone_low=round(feature_bar.close * (1.0 - width), 4),
            entry_zone_high=round(feature_bar.close * (1.0 + width * 0.35), 4),
            invalidation_price=round(transition.invalidation_price, 4),
            first_target_price=round(feature_bar.close * (1.0 + target_fraction), 4),
            reason_codes=tuple(dict.fromkeys(reasons)),
            evidence_refs=tuple(dict.fromkeys(evidence_refs)),
            context_data_asofs=tuple(dict.fromkeys(context_data_asofs)),
            source_components=tuple(dict.fromkeys(components)),
            intraday_score=round(intraday_score, 6),
            calibration_label=calibration_label,
            prediction_provider=active_provider,
            prediction_provider_requested=requested_provider,
            provider_qualified=provider_qualified,
            provider_fallback=provider_fallback,
            provider_fallback_reason=provider_fallback_reason,
            horizon_probabilities=horizon_probabilities,
            deterministic_baseline_probabilities=deterministic_probabilities,
            model_artifact_digest=model_artifact_digest,
            signal_id=signal_id,
            state_label_zh=PREDICTION_STATE_LABEL_ZH[state],
            decision_price=round(float(feature_bar.close), 4),
            candidate_name=candidate.name if candidate is not None else None,
            candidate_rank=(
                candidate.candidate_rank if candidate is not None else None
            ),
            after_close_quant_score=(
                candidate.quant_score if candidate is not None else None
            ),
            deepseek_stance=(
                candidate.deepseek_stance if candidate is not None else "neutral"
            ),
            deepseek_stance_provenance=(
                candidate.deepseek_stance_provenance
                if candidate is not None
                else "not_structured"
            ),
            after_close_ai_stance=(
                candidate.after_close_ai_stance if candidate is not None else "neutral"
            ),
            stance_provenance=(
                candidate.stance_provenance if candidate is not None else "not_available"
            ),
            experience_plan_id=(
                candidate.experience_plan_id if candidate is not None else None
            ),
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
    """Map causal, signed ATR-scaled features around a neutral 0.5 state.

    ATR is used only as a price-return scale. Relative volume is directionless,
    so it can amplify or attenuate price evidence but cannot create a bullish or
    bearish sign on its own. No statistic is fitted to the replay sample.
    """

    risk_unit = _clip(features.atr_14_fraction_of_close, 0.0005, 0.05)
    primary_minutes = max(1, int(features.primary_interval_minutes))
    fast = _risk_scaled_return(
        features.momentum_3_feature_bars,
        risk_unit=risk_unit,
        horizon_primary_bars=3.0,
    )
    slow = _risk_scaled_return(
        features.momentum_12_feature_bars,
        risk_unit=risk_unit,
        horizon_primary_bars=12.0,
    )
    trend = _risk_scaled_return(
        features.trend_sma_3_over_sma_12_return,
        risk_unit=risk_unit,
        horizon_primary_bars=6.0,
    )
    vwap = _risk_scaled_return(
        features.close_to_session_vwap_return,
        risk_unit=risk_unit,
        horizon_primary_bars=4.0,
    )
    momentum_15m = _risk_scaled_return(
        float(features.momentum_2x15m_bars or 0.0),
        risk_unit=risk_unit,
        horizon_primary_bars=30.0 / primary_minutes,
    )
    momentum_30m = _risk_scaled_return(
        float(features.momentum_2x30m_bars or 0.0),
        risk_unit=risk_unit,
        horizon_primary_bars=60.0 / primary_minutes,
    )
    drawdown = _risk_scaled_return(
        min(features.session_drawdown_from_high, 0.0),
        risk_unit=risk_unit,
        horizon_primary_bars=16.0,
    )
    relative_volume = max(float(features.relative_volume_20_feature_bars), 0.01)
    volume_activity = math.tanh(math.log(relative_volume))
    volume_confidence_multiplier = 1.0 + 0.15 * volume_activity
    price_direction = (
        0.22 * fast
        + 0.16 * slow
        + 0.18 * trend
        + 0.14 * vwap
        + 0.12 * momentum_15m
        + 0.10 * momentum_30m
        + 0.08 * drawdown
    )
    daily_prior = 0.0
    if candidate is not None:
        daily_prior = 0.10 * (
            (candidate.confidence - 0.5)
            + (candidate.factor_composite_score - 0.5)
        )
    direction_score = _clip(
        price_direction * volume_confidence_multiplier + daily_prior,
        -1.25,
        1.25,
    )
    continuation_score = _clip(
        (
            0.30 * fast
            + 0.20 * slow
            + 0.25 * trend
            + 0.15 * momentum_15m
            + 0.10 * momentum_30m
        )
        * volume_confidence_multiplier,
        -1.25,
        1.25,
    )
    entry = _neutral_probability(direction_score)
    exit_probability = 1.0 - entry
    continuation = _neutral_probability(continuation_score)
    expected_move = _clip(direction_score * risk_unit, -0.10, 0.10)
    reasons = [
        "intraday_trend_positive" if trend > 0 else "intraday_trend_nonpositive",
        (
            "intraday_momentum_positive"
            if fast > 0
            else "intraday_momentum_nonpositive"
        ),
        (
            "price_above_session_vwap"
            if vwap >= 0
            else "price_below_session_vwap"
        ),
        (
            "relative_volume_above_one"
            if relative_volume > 1.0
            else "relative_volume_at_or_below_one"
        ),
        (
            "session_drawdown_guard"
            if features.session_drawdown_from_high <= -0.05
            else "session_drawdown_within_guard"
        ),
        "atr_scaled_signed_feature_mapping",
        "relative_volume_modulates_but_does_not_set_direction",
        "probabilities_are_untrained_deterministic_normalization",
    ]
    return {
        "intraday_score": entry,
        "entry_probability": entry,
        "continuation_probability": continuation,
        "exit_probability": exit_probability,
        "expected_move": expected_move,
        "direction_score": direction_score,
        "continuation_score": continuation_score,
        "risk_unit": risk_unit,
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
            candidate_rank=int(signal.factor_rank) or None,
            quant_score=float(signal.factor_composite_score_raw),
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


def _advance_signal_lifecycle_v1(
    lifecycle: _SignalLifecycle,
    *,
    symbol: str,
    decision_timestamp: str,
    completed_bar_low: float,
    entry_probability: float,
    continuation_probability: float,
    exit_probability: float,
    expected_move: float,
    proposed_invalidation_price: float,
) -> _LifecycleTransition:
    """Advance a signal-only lifecycle without consulting account holdings."""

    bullish_setup = (
        entry_probability >= ENTRY_PROBABILITY_THRESHOLD
        and continuation_probability >= 0.50
        and expected_move > 0
    )
    if not lifecycle.active:
        if bullish_setup and not lifecycle.previous_entry_setup:
            lifecycle.sequence += 1
            lifecycle.active = True
            lifecycle.lifecycle_id = f"{symbol}:{lifecycle.sequence}:{decision_timestamp}"
            lifecycle.invalidation_price = float(proposed_invalidation_price)
            lifecycle.previous_entry_setup = True
            return _LifecycleTransition(
                state=PredictionState.ENTRY,
                lifecycle_id=lifecycle.lifecycle_id,
                invalidation_price=lifecycle.invalidation_price,
                reason_code="signal_lifecycle_started_on_bullish_setup_cross",
                started=True,
            )
        lifecycle.previous_entry_setup = bullish_setup
        return _LifecycleTransition(
            state=PredictionState.WATCH,
            lifecycle_id=None,
            invalidation_price=float(proposed_invalidation_price),
            reason_code=(
                "signal_lifecycle_waiting_for_new_setup_cross"
                if bullish_setup
                else "signal_lifecycle_inactive_neutral"
            ),
        )

    lifecycle_id = lifecycle.lifecycle_id
    invalidation_price = float(
        lifecycle.invalidation_price or proposed_invalidation_price
    )
    price_breached = completed_bar_low <= invalidation_price
    evidence_breached = (
        exit_probability >= INVALIDATION_EXIT_PROBABILITY_THRESHOLD
    )
    if price_breached or evidence_breached:
        _close_lifecycle(lifecycle, bullish_setup=bool(bullish_setup))
        return _LifecycleTransition(
            state=PredictionState.INVALIDATED,
            lifecycle_id=lifecycle_id,
            invalidation_price=invalidation_price,
            reason_code=(
                "signal_lifecycle_invalidated_by_setup_price"
                if price_breached
                else "signal_lifecycle_invalidated_by_strong_downside_evidence"
            ),
            completed=True,
        )
    if exit_probability >= EXIT_PROBABILITY_THRESHOLD:
        _close_lifecycle(lifecycle, bullish_setup=bool(bullish_setup))
        return _LifecycleTransition(
            state=PredictionState.EXIT,
            lifecycle_id=lifecycle_id,
            invalidation_price=invalidation_price,
            reason_code="signal_lifecycle_completed_by_exit_evidence",
            completed=True,
        )
    lifecycle.previous_entry_setup = bullish_setup
    if (
        exit_probability > entry_probability
        or continuation_probability < 0.50
        or expected_move <= 0
    ):
        return _LifecycleTransition(
            state=PredictionState.WEAKENING,
            lifecycle_id=lifecycle_id,
            invalidation_price=invalidation_price,
            reason_code="signal_lifecycle_active_but_weakening",
        )
    return _LifecycleTransition(
        state=PredictionState.HOLD,
        lifecycle_id=lifecycle_id,
        invalidation_price=invalidation_price,
        reason_code="signal_lifecycle_active_and_valid",
    )


def _close_lifecycle(
    lifecycle: _SignalLifecycle,
    *,
    bullish_setup: bool,
) -> None:
    lifecycle.active = False
    lifecycle.previous_entry_setup = bullish_setup
    lifecycle.lifecycle_id = None
    lifecycle.invalidation_price = None


def intraday_probability_mapping_semantics() -> Mapping[str, Any]:
    return {
        "mapping": CALIBRATION_LABEL,
        "neutral_probability": 0.5,
        "signed_scaling": (
            "price-return features divided by causal ATR fraction times the square "
            "root of their fixed bar horizon, then bounded with tanh"
        ),
        "direction_weights": {
            "momentum_3_feature_bars": 0.22,
            "momentum_12_feature_bars": 0.16,
            "trend_sma_3_over_sma_12_return": 0.18,
            "close_to_session_vwap_return": 0.14,
            "momentum_2x15m_bars": 0.12,
            "momentum_2x30m_bars": 0.10,
            "session_drawdown_from_high": 0.08,
        },
        "relative_volume": (
            "dimensionless confidence multiplier in [0.85, 1.15]; never assigns "
            "direction by itself"
        ),
        "atr": (
            "causal volatility scale with fixed [0.0005, 0.05] fraction bounds; "
            "never a directional contribution"
        ),
        "probability_transform": "0.5 + 0.45 * tanh(1.5 * signed_score)",
        "exit_probability": "one minus entry/upside probability",
        "sample_fitted_parameters": False,
        "entry_threshold": ENTRY_PROBABILITY_THRESHOLD,
        "exit_threshold": EXIT_PROBABILITY_THRESHOLD,
        "invalidation_exit_probability_threshold": (
            INVALIDATION_EXIT_PROBABILITY_THRESHOLD
        ),
    }


def _risk_scaled_return(
    value: float,
    *,
    risk_unit: float,
    horizon_primary_bars: float,
) -> float:
    denominator = risk_unit * math.sqrt(max(1.0, float(horizon_primary_bars)))
    return math.tanh(float(value) / denominator)


def _neutral_probability(signed_score: float) -> float:
    return 0.5 + 0.45 * math.tanh(1.5 * float(signed_score))


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
