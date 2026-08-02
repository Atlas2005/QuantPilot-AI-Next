"""Build one PIT-safe, manifest-bounded Continuous Paper input payload."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import math
from pathlib import Path
import re
from typing import Any, Callable, Mapping, Sequence

import pandas as pd

from quantpilot_core.a_share_tradability_metadata import (
    AShareTradabilityMetadataConfig,
    enrich_market_rows,
)
from quantpilot_core.all_a_share_snapshot import (
    SnapshotLoader,
    validate_snapshot,
)
from quantpilot_core.continuous_paper.manifest_bridge import (
    PRODUCTION_INPUT_PAYLOAD_FIELDS,
    normalize_production_input_payload,
)
from quantpilot_core.evaluation import (
    FactorRankingBaselineConfig,
    run_factor_ranking_baseline_v1,
)
from quantpilot_core.production_candidate import load_runtime_manifest
from quantpilot_core.real_data_provider import (
    DailyBarRequest,
    ProviderName,
    SnapshotDailyBarProvider,
    TradingCalendar,
)


DAILY_PRODUCTION_INPUT_VERSION = "daily_production_input_v1"
AUTHORITATIVE_PRODUCTION_PRESELECTOR = "defensive_composite_v1"
_PRODUCTION_SYMBOL = re.compile(r"\d{6}\.(?:SH|SZ)")
_FACTOR_SESSION_COUNT = 61


class DailyProductionInputError(ValueError):
    """Raised when authoritative daily input cannot be built safely."""


@dataclass(frozen=True)
class DailyProductionInputConfig:
    production_manifest: Any
    snapshot_root: str | Path
    requested_decision_session: str
    runtime_code_revision: str | None = None


@dataclass(frozen=True)
class DailyProductionInputResult:
    payload: Mapping[str, Any]
    requested_decision_session: str
    decision_session: str
    execution_session: str
    selected_symbols: tuple[str, ...]
    tradable_universe_size: int
    snapshot_digest: str
    manifest_digest: str
    ranking_method: str


def build_daily_production_input_v1(
    config: DailyProductionInputConfig,
    *,
    calendar: TradingCalendar | None = None,
    snapshot_loader: Any | None = None,
    bar_provider: Any | None = None,
    snapshot_validation: Any | None = None,
    ranking_runner: Callable[..., Any] = run_factor_ranking_baseline_v1,
) -> DailyProductionInputResult:
    """Compose existing snapshot, tradability, factor, and manifest contracts.

    Dependency arguments are intentionally injectable so tests and cached
    qualification never need Tushare or another external runtime.
    """

    manifest = load_runtime_manifest(config.production_manifest)
    target_count, max_count = _manifest_symbol_counts(manifest)
    selection_count = min(target_count, max_count)

    root = Path(config.snapshot_root)
    validation = snapshot_validation or validate_snapshot(root)
    if not validation.ok or validation.manifest.get("status") != "completed":
        details = "; ".join(validation.errors) or str(
            validation.manifest.get("status", "missing")
        )
        raise DailyProductionInputError(f"no valid PIT snapshot is available: {details}")
    snapshot_manifest = dict(validation.manifest)
    _require_tradability_capabilities(snapshot_manifest)

    loader = snapshot_loader or SnapshotLoader(root)
    provider = bar_provider or SnapshotDailyBarProvider(
        root, validation_result=validation
    )
    source_calendar = calendar or _snapshot_calendar(loader)
    requested = _parse_iso_date(
        config.requested_decision_session, "requested_decision_session"
    )
    _reject_stale_cached_request(requested, snapshot_manifest, calendar is None)
    try:
        decision = source_calendar.previous_session(requested, inclusive=True)
        factor_start = source_calendar.shift_session(decision, -(_FACTOR_SESSION_COUNT - 1))
        execution = source_calendar.next_session(decision)
    except Exception as exc:
        raise DailyProductionInputError(
            "loaded A-share calendar cannot resolve 61 factor sessions and D+1 "
            f"for {requested.isoformat()}"
        ) from exc
    factor_sessions = source_calendar.sessions_between(factor_start, decision)
    if len(factor_sessions) != _FACTOR_SESSION_COUNT:
        raise DailyProductionInputError(
            f"factor window must contain exactly {_FACTOR_SESSION_COUNT} sessions"
        )

    decision_key = decision.strftime("%Y%m%d")
    listed_symbols = {
        str(row.get("ts_code", "")) for row in loader.listed_universe(decision_key)
    }
    if not listed_symbols:
        raise DailyProductionInputError(
            f"PIT-listed universe is empty on {decision.isoformat()}"
        )
    daily_symbols = {
        str(row.get("ts_code", "")) for row in loader.daily(decision_key)
    }
    candidate_symbols = tuple(
        sorted(
            symbol
            for symbol in listed_symbols.intersection(daily_symbols)
            if _PRODUCTION_SYMBOL.fullmatch(symbol)
        )
    )
    if not candidate_symbols:
        raise DailyProductionInputError(
            f"no SH/SZ PIT-listed daily rows survive on {decision.isoformat()}"
        )

    decision_bars, missing_decision = provider.fetch_many_daily_bars_with_empty_symbols(
        tuple(DailyBarRequest(symbol, decision, decision) for symbol in candidate_symbols)
    )
    decision_rows = {
        bar.symbol: _bar_payload(bar, is_suspended=False) for bar in decision_bars
    }
    metadata = provider.tradability_metadata(decision, decision)
    metadata_config = AShareTradabilityMetadataConfig.from_metadata(metadata)
    enriched = enrich_market_rows(decision_rows, config=metadata_config)
    tradable_symbols, filter_counts = _tradable_symbols(
        candidate_symbols, enriched, missing_decision
    )
    if not tradable_symbols:
        raise DailyProductionInputError(
            f"tradable A-share universe is empty on {decision.isoformat()}"
        )

    factor_bars, _ = provider.fetch_many_daily_bars_with_empty_symbols(
        tuple(
            DailyBarRequest(symbol, factor_start, decision)
            for symbol in tradable_symbols
        )
    )
    factor_frame = pd.DataFrame(_bar_payload(bar, is_suspended=False) for bar in factor_bars)
    if factor_frame.empty:
        raise DailyProductionInputError("snapshot returned no PIT factor rows")
    if any(pd.to_datetime(factor_frame["date"]).dt.date > decision):
        raise DailyProductionInputError("factor input contains rows after decision session")

    ranking_report = ranking_runner(
        factor_frame,
        FactorRankingBaselineConfig(
            ranking_mode=AUTHORITATIVE_PRODUCTION_PRESELECTOR,
            target_symbol_count=selection_count,
            as_of_date=decision.isoformat(),
            artifact_path=None,
            metadata={
                "provider": ProviderName.SNAPSHOT.value,
                "run_context": "daily_production_input_v1",
                "symbols_requested": tradable_symbols,
                "date_range": (factor_start.isoformat(), decision.isoformat()),
            },
        ),
    )
    selected = tuple(ranking_report.selected_symbols[:selection_count])
    if len(selected) < selection_count:
        raise DailyProductionInputError(
            "fewer symbols survived factor evidence than required by the manifest: "
            f"{len(selected)} < {selection_count}"
        )
    if len(selected) > max_count:
        raise DailyProductionInputError(
            "selected symbol count exceeds manifest max_execution_symbols"
        )

    selected_set = set(selected)
    output_bars = []
    for bar in factor_bars:
        if bar.symbol not in selected_set:
            continue
        is_suspended = bool(
            enriched.get(bar.symbol, {}).get("is_suspended", False)
        ) if bar.trade_date == decision else False
        output_bars.append(_bar_payload(bar, is_suspended=is_suspended))
    output_bars.sort(key=lambda row: (str(row["date"]), str(row["symbol"])))
    if not output_bars or any(date.fromisoformat(row["date"]) > decision for row in output_bars):
        raise DailyProductionInputError("serialized bars are empty or contain future data")

    scores = {
        score.symbol: float(score.composite_score)
        for score in ranking_report.factor_scores
        if score.symbol in selected_set
    }
    snapshot_digest = str(snapshot_manifest.get("digest") or "")
    if not snapshot_digest:
        raise DailyProductionInputError("validated snapshot is missing its digest")
    code_revision = (
        str(config.runtime_code_revision).strip()
        if config.runtime_code_revision
        else str(manifest.code_revision or "")
    )
    provenance = {
        "bridge_version": DAILY_PRODUCTION_INPUT_VERSION,
        "decision_session": decision.isoformat(),
        "decision_cutoff": f"{decision.isoformat()}T15:00:00+08:00",
        "requested_decision_session": requested.isoformat(),
        "snapshot_session": decision.isoformat(),
        "snapshot_digest": snapshot_digest,
        "snapshot_actual_date_range": dict(
            snapshot_manifest.get("actual_date_range", {})
        ),
        "pit_boundary_enforced": True,
        "future_market_rows_serialized": 0,
        "listed_universe_size": len(listed_symbols),
        "daily_row_universe_size": len(daily_symbols),
        "tradable_universe_size": len(tradable_symbols),
        "filters_applied": (
            "pit_listed_on_decision_session",
            "sh_sz_six_digit_equity_contract",
            "decision_daily_bar_present",
            "existing_snapshot_suspension_metadata",
            "existing_valid_ohlc_enrichment",
            "positive_decision_volume",
        ),
        "filter_counts": filter_counts,
        "ranking_method": AUTHORITATIVE_PRODUCTION_PRESELECTOR,
        "ranking_component": (
            "quantpilot_core.evaluation.factor_ranking_baseline."
            "run_factor_ranking_baseline_v1"
        ),
        "selected_order": selected,
        "selected_scores": {symbol: scores[symbol] for symbol in selected},
        "manifest_target_symbol_count": target_count,
        "manifest_max_execution_symbols": max_count,
        "manifest_digest": manifest.manifest_digest,
        "manifest_code_revision": manifest.code_revision,
        "code_revision": code_revision,
        "external_model_calls": 0,
        "broker_calls": 0,
    }
    calendar_sessions = tuple(
        session.isoformat()
        for session in source_calendar.sessions_between(factor_start, execution)
    )
    payload = {
        "symbols": list(selected),
        "bars": output_bars,
        "information_signals": [],
        "information_provenance": {
            "source": DAILY_PRODUCTION_INPUT_VERSION,
            "decision_session": decision.isoformat(),
            "decision_cutoff": f"{decision.isoformat()}T15:00:00+08:00",
            "pit_safe": True,
            "daily_production_input_v1": provenance,
        },
        "advisory_provenance": {
            "mode": "disabled_during_input_construction",
            "deepseek_live_call": False,
            "external_model_calls": 0,
        },
        "quant_firm_context": {
            "daily_production_input_v1": {
                "calendar_sessions": calendar_sessions,
                "calendar_provider": source_calendar.provider.value,
                "decision_session": decision.isoformat(),
                "execution_session": execution.isoformat(),
                "ranking_method": AUTHORITATIVE_PRODUCTION_PRESELECTOR,
                "selected_order": selected,
                "manifest_digest": manifest.manifest_digest,
                "snapshot_digest": snapshot_digest,
            },
            "candidate_selection": {
                "component": "factor_ranking_baseline_v1",
                "ranking_method": AUTHORITATIVE_PRODUCTION_PRESELECTOR,
                "selected_order": selected,
                "allocation_method": manifest.execution_ranking_mode,
            },
        },
    }
    if set(payload) != set(PRODUCTION_INPUT_PAYLOAD_FIELDS):
        raise AssertionError("daily production input schema drifted")
    normalize_production_input_payload(payload)
    return DailyProductionInputResult(
        payload=payload,
        requested_decision_session=requested.isoformat(),
        decision_session=decision.isoformat(),
        execution_session=execution.isoformat(),
        selected_symbols=selected,
        tradable_universe_size=len(tradable_symbols),
        snapshot_digest=snapshot_digest,
        manifest_digest=manifest.manifest_digest,
        ranking_method=AUTHORITATIVE_PRODUCTION_PRESELECTOR,
    )


def _manifest_symbol_counts(manifest: Any) -> tuple[int, int]:
    strategy = dict(manifest.frozen_strategy_parameters)
    try:
        target = int(strategy["target_symbol_count"])
        maximum = int(strategy["max_execution_symbols"])
    except (KeyError, TypeError, ValueError) as exc:
        raise DailyProductionInputError(
            "production manifest is missing valid symbol-count parameters"
        ) from exc
    if target <= 0 or maximum <= 0 or target > maximum or maximum > 6:
        raise DailyProductionInputError(
            "production manifest symbol counts conflict: require "
            "1 <= target_symbol_count <= max_execution_symbols <= 6"
        )
    return target, maximum


def _require_tradability_capabilities(manifest: Mapping[str, Any]) -> None:
    capabilities = dict(manifest.get("capabilities", {}))
    missing = tuple(
        name for name in ("suspend", "limits") if capabilities.get(name) != "available"
    )
    if missing:
        raise DailyProductionInputError(
            "snapshot lacks required tradability capabilities: " + ", ".join(missing)
        )


def _snapshot_calendar(loader: Any) -> TradingCalendar:
    try:
        sessions = tuple(
            date(int(value[:4]), int(value[4:6]), int(value[6:8]))
            for value in loader.sessions()
        )
    except (TypeError, ValueError) as exc:
        raise DailyProductionInputError("snapshot calendar is malformed") from exc
    if not sessions:
        raise DailyProductionInputError("snapshot calendar has no sessions")
    return TradingCalendar(sessions, ProviderName.SNAPSHOT)


def _reject_stale_cached_request(
    requested: date, manifest: Mapping[str, Any], cached_mode: bool
) -> None:
    if not cached_mode:
        return
    requested_range = dict(manifest.get("requested_date_range", {}))
    end = str(requested_range.get("end", "")).replace("-", "")
    if len(end) != 8 or not end.isdigit():
        raise DailyProductionInputError("snapshot requested date range is missing")
    end_date = date(int(end[:4]), int(end[4:6]), int(end[6:8]))
    if requested > end_date:
        raise DailyProductionInputError(
            "cached snapshot is stale for requested decision session: "
            f"coverage ends {end_date.isoformat()}"
        )


def _tradable_symbols(
    candidate_symbols: Sequence[str],
    enriched_rows: Mapping[str, Mapping[str, Any]],
    missing_decision: Sequence[str],
) -> tuple[tuple[str, ...], Mapping[str, int]]:
    missing = set(missing_decision)
    counts = {
        "pit_and_symbol_contract": len(candidate_symbols),
        "missing_decision_bar": 0,
        "suspended_or_unknown": 0,
        "invalid_ohlc": 0,
        "nonpositive_volume": 0,
        "survived": 0,
    }
    survived = []
    for symbol in candidate_symbols:
        row = enriched_rows.get(symbol)
        if symbol in missing or row is None:
            counts["missing_decision_bar"] += 1
            continue
        if row.get("tradable") is not True:
            counts["suspended_or_unknown"] += 1
            continue
        if row.get("valid_ohlc") is not True:
            counts["invalid_ohlc"] += 1
            continue
        volume = _finite_float(row.get("volume"))
        if volume is None or volume <= 0:
            counts["nonpositive_volume"] += 1
            continue
        survived.append(symbol)
    counts["survived"] = len(survived)
    return tuple(survived), counts


def _bar_payload(bar: Any, *, is_suspended: bool) -> dict[str, Any]:
    return {
        "symbol": str(bar.symbol),
        "date": bar.trade_date.isoformat(),
        "open": float(bar.open),
        "high": float(bar.high),
        "low": float(bar.low),
        "close": float(bar.close),
        "previous_close": (
            None if bar.previous_close is None else float(bar.previous_close)
        ),
        "volume": float(bar.volume),
        "amount": (
            float(bar.amount)
            if bar.amount is not None
            else float(bar.close) * float(bar.volume)
        ),
        "is_suspended": bool(is_suspended),
        "provider": (
            bar.provider.value if hasattr(bar.provider, "value") else str(bar.provider)
        ),
    }


def _finite_float(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _parse_iso_date(value: str, label: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise DailyProductionInputError(f"{label} must use YYYY-MM-DD") from exc
