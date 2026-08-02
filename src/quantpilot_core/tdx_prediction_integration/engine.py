"""Shared factor-backed prediction engine for replay and live shadow."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, replace
from datetime import datetime
from typing import Any

import pandas as pd

from quantpilot_core.deepseek_multi_agent import (
    AgentFinding,
    AgentRiskFlag,
    AgentRole,
    validate_agent_finding,
)
from quantpilot_core.evaluation import (
    FactorRankingBaselineConfig,
    run_factor_ranking_baseline_v1,
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


CALIBRATION_LABEL = "deterministic_untrained_factor_score_calibration_v1"


class TDXPredictionEngineV1:
    """Apply the existing factor baseline to completed higher-timeframe bars."""

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
        if self.config.min_feature_bars < 11:
            raise ValueError("min_feature_bars must be at least 11")
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
            scores = self._factor_scores(cutoff)
            for symbol in due_symbols:
                score = scores.get(symbol)
                feature_bar = self._latest_complete_feature_bar(symbol, cutoff)
                if score is None or feature_bar is None:
                    continue
                signal = self._prediction(score, feature_bar)
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

    def _factor_scores(self, cutoff: datetime) -> Mapping[str, Any]:
        rows: list[Mapping[str, Any]] = []
        for symbol in self.symbols:
            for bar in self._feature_bars(symbol, cutoff):
                rows.append(
                    {
                        "date": bar.end.replace(tzinfo=None),
                        "symbol": symbol,
                        "open": bar.open,
                        "high": bar.high,
                        "low": bar.low,
                        "close": bar.close,
                        "volume": bar.volume,
                        "amount": bar.amount,
                    }
                )
        if not rows:
            return {}
        report = run_factor_ranking_baseline_v1(
            pd.DataFrame(rows),
            FactorRankingBaselineConfig(
                ranking_mode=self.config.factor_ranking_mode,
                target_symbol_count=len(self.symbols),
                as_of_date=cutoff.replace(tzinfo=None).isoformat(),
                min_liquidity_percentile=0.0,
                artifact_path=None,
                metadata={
                    "provider": "tdx_level1_intraday_adapter",
                    "run_context": "tdx_prediction_integration",
                    "symbols_requested": self.symbols,
                },
            ),
        )
        return {score.symbol: score for score in report.factor_scores}

    def _prediction(self, factor: Any, feature_bar: NormalizedIntradayBar) -> PredictionSignal:
        candidate = _candidate_for_cutoff(
            self.context.candidates.get(factor.symbol),
            feature_bar.end,
        )
        calibrated = calibrate_factor_score_v1(factor, candidate=candidate)
        entry_probability = calibrated["entry_probability"]
        continuation_probability = calibrated["continuation_probability"]
        exit_probability = calibrated["exit_probability"]
        expected_move = calibrated["expected_move"]
        volatility = max(float(factor.volatility_20d or 0.0), 0.0)
        drawdown = float(factor.drawdown_20d or 0.0)
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
            f"factor_windows_use_completed_{self.config.feature_interval_minutes}m_bars"
        )
        evidence_refs = [
            f"tdx_factor_score:{factor.symbol}:{feature_bar.end.isoformat()}"
        ]
        context_data_asofs: list[str] = []
        components = [
            "quantpilot_core.evaluation.factor_ranking_baseline.run_factor_ranking_baseline_v1",
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
            factor.symbol,
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
            symbol=factor.symbol,
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
            factor_score=round(float(factor.composite_score), 6),
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


def calibrate_factor_score_v1(
    factor: Any,
    *,
    candidate: CandidateEvidence | None = None,
) -> Mapping[str, Any]:
    """Bound factor outputs into probabilities without claiming trained calibration."""

    momentum_20 = float(factor.momentum_20d or 0.0)
    momentum_60 = float(factor.momentum_60d or 0.0)
    volatility = max(float(factor.volatility_20d or 0.0), 0.0)
    drawdown = min(float(factor.drawdown_20d or 0.0), 0.0)
    composite = float(factor.composite_score)
    daily_prior = 0.0
    if candidate is not None:
        daily_prior = 0.10 * (candidate.confidence - 0.5) + 0.08 * (
            candidate.factor_composite_score - 0.5
        )
    strength = (
        1.15 * (composite - 0.5)
        + 2.8 * momentum_20
        + 1.2 * momentum_60
        + (0.04 if factor.trend_filter else -0.04)
        + daily_prior
        + 1.4 * drawdown
        - min(0.15, volatility * 1.5)
    )
    expected_move = _clip(0.35 * momentum_20 + 0.15 * momentum_60 - 0.4 * volatility, -0.10, 0.10)
    entry = _clip(0.5 + strength, 0.02, 0.98)
    exit_probability = _clip(0.5 - strength - 0.8 * drawdown, 0.02, 0.98)
    continuation = _clip(
        0.5 + 1.8 * momentum_20 + (0.06 if factor.trend_filter else -0.06) - volatility,
        0.02,
        0.98,
    )
    reasons = [
        "factor_trend_positive" if factor.trend_filter else "factor_trend_nonpositive",
        "factor_momentum_positive" if momentum_20 > 0 else "factor_momentum_nonpositive",
        "factor_drawdown_guard" if drawdown <= -0.03 else "factor_drawdown_within_guard",
        "probabilities_are_untrained_deterministic_normalization",
    ]
    return {
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
        "factor_ranking_baseline_v1",
        "intraday_aggregation.aggregate_intraday_bars",
        "tdx_manual_signal_bridge.export_signals",
        "deepseek_multi_agent.AgentFinding_validation",
    )
