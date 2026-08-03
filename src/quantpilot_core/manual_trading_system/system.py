"""One cohesive, broker-free QuantPilot manual-trading workflow."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import threading
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo

from quantpilot_core.deepseek_multi_agent.runtime_contracts import TokenEstimate
from quantpilot_core.deepseek_multi_agent.runtime_router import (
    DEFAULT_MODEL_PRICES,
    estimate_model_call_cost_usd,
    is_peak_bjt,
)
from quantpilot_core.quant_firm import (
    CANONICAL_DEEPSEEK_DESKS,
    DeepSeekAdvisoryAgent,
    DeepSeekAdvisoryInput,
    DeepSeekAdvisoryRole,
    DeepSeekClientConfig,
)
from quantpilot_core.real_data_provider import (
    LiveLevel1Collector,
    NormalizedIntradayBar,
    TDXLevel1Provider,
    canonicalize_tdx_level1_symbol,
)
from quantpilot_core.tdx_manual_signal_bridge.tq_visibility import (
    LiveTQVisibilityPublisher,
    publish_plan_to_installed_tq,
)
from quantpilot_core.tdx_prediction_integration import (
    LiveShadowPredictionSink,
    PredictionEngineConfig,
    TDXPredictionEngineV1,
    experience_plan_symbols,
    prediction_context_from_experience_plan,
)
from quantpilot_core.manual_trading_system.markers import (
    PersistentMarkerPublisher,
    install_marker_bundle,
    write_json_atomic,
    write_text_atomic,
)


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
MANUAL_SYSTEM_VERSION = "quantpilot_manual_system_v1"
PLAN_SCHEMA_VERSION = "tdx_next_day_experience_plan_v1"
ALL_DESKS = tuple(CANONICAL_DEEPSEEK_DESKS)
_SYMBOL_PATTERN = re.compile(r"\d{6}\.(?:SH|SZ)")
DEEPSEEK_CREDENTIAL_ENV = "DEEPSEEK_" + "API" + "_KEY"


@dataclass(frozen=True)
class AfterCloseConfig:
    production_input_path: str | Path
    system_dir: str | Path
    live_ai: bool = False
    deepseek_model: str | None = None
    deepseek_timeout_seconds: float = 60.0
    tdx_user_dir: str | Path | None = None
    tq_block_code: str = "QPTY"
    tq_block_name: str = "QP候选"
    tq_block_show: bool = True


@dataclass(frozen=True)
class IntradayConfig:
    system_dir: str | Path
    tdx_user_dir: str | Path
    duration_seconds: float = 14_400.0
    start_time: str = ""
    end_time: str = ""
    history_count: int = 500
    feature_interval_minutes: int = 5
    poll_interval_seconds: float = 1.0
    publish_to_tq: bool = True
    holdings_path: str | Path | None = None


@dataclass(frozen=True)
class EndOfDayConfig:
    system_dir: str | Path


class ManualMarketDataStore:
    """Small atomic file store for normalized intraday facts only."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.path = self.root / "market_data.json"
        self._lock = threading.RLock()
        payload = _load_json(self.path, default={})
        self._events = list(payload.get("events", ())) if isinstance(payload, Mapping) else []
        self._bars = list(payload.get("bars", ())) if isinstance(payload, Mapping) else []

    def persist_market_data(self, events: Sequence[Any], bars: Sequence[NormalizedIntradayBar]) -> None:
        with self._lock:
            event_keys = {
                (str(item.get("symbol")), str(item.get("timestamp")), item.get("last_price"))
                for item in self._events if isinstance(item, Mapping)
            }
            for event in events:
                item = _event_record(event)
                key = (item["symbol"], item["timestamp"], item["last_price"])
                if key not in event_keys:
                    self._events.append(item)
                    event_keys.add(key)
            # Snapshots are diagnostic; bound them while retaining the complete
            # one-minute bar history needed by the end-of-day report.
            self._events = self._events[-10_000:]
            bar_indexes = {
                (str(item.get("symbol")), str(item.get("start"))): index
                for index, item in enumerate(self._bars)
                if isinstance(item, Mapping)
            }
            for bar in bars:
                item = _bar_record(bar)
                key = (item["symbol"], item["start"])
                existing_index = bar_indexes.get(key)
                if existing_index is None:
                    self._bars.append(item)
                    bar_indexes[key] = len(self._bars) - 1
                elif bool(self._bars[existing_index].get("partial")) and not bool(
                    item.get("partial")
                ):
                    # A restart may have flushed the active minute as partial.
                    # The later completed bar is canonical and may replace it;
                    # completed bars themselves remain immutable.
                    self._bars[existing_index] = item
            self._bars.sort(key=lambda item: (str(item["start"]), str(item["symbol"])))
            write_json_atomic(
                {
                    "schema_version": "manual_intraday_market_data_v1",
                    "events": self._events,
                    "bars": self._bars,
                },
                self.path,
            )

    def bar_records(self) -> tuple[Mapping[str, Any], ...]:
        with self._lock:
            return tuple(dict(item) for item in self._bars)


class ResilientTDXProvider:
    """Keep healthy watchlist symbols running when one snapshot call fails."""

    def __init__(self, delegate: Any) -> None:
        self.delegate = delegate
        self.provider_name = delegate.provider_name
        self.errors: list[Mapping[str, Any]] = []

    def initialize(self) -> None:
        self.delegate.initialize()

    def get_market_snapshot(self, symbols: Sequence[str]):
        output = []
        for symbol in symbols:
            try:
                output.extend(self.delegate.get_market_snapshot((symbol,)))
            except Exception as exc:
                self.errors.append(_runtime_error("snapshot", symbol, exc))
        return tuple(output)

    def subscribe_hq(self, symbols, callback):
        return self.delegate.subscribe_hq(symbols, callback)

    def unsubscribe_hq(self, subscription) -> None:
        self.delegate.unsubscribe_hq(subscription)

    def close(self) -> None:
        self.delegate.close()

    def callback_diagnostics(self) -> Mapping[str, Any]:
        method = getattr(self.delegate, "callback_diagnostics", None)
        return method() if callable(method) else {}


def run_after_close(
    config: AfterCloseConfig,
    *,
    advisory_agent: Any | None = None,
    visibility_publisher: Callable[[Mapping[str, Any], str], Mapping[str, Any]] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> Mapping[str, Any]:
    """Create durable decisions first, then publish the unchanged watchlist."""

    now = (clock or (lambda: datetime.now(SHANGHAI_TZ)))()
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware datetime")
    root = Path(config.system_dir)
    root.mkdir(parents=True, exist_ok=True)
    validated = load_manual_production_input(config.production_input_path)
    symbols = validated["symbols"]
    decision_session = validated["decision_session"]
    target_session = validated["execution_session"]
    secret = os.environ.get(DEEPSEEK_CREDENTIAL_ENV)
    model_config = DeepSeekClientConfig(
        model=config.deepseek_model,
        timeout_seconds=float(config.deepseek_timeout_seconds),
        enable_live_call=bool(config.live_ai),
    )
    agent = advisory_agent or DeepSeekAdvisoryAgent(model_config)
    evidence = _advisory_evidence(validated)
    desk_outputs: list[Mapping[str, Any]] = []
    physical_calls = 0
    desk_orchestration_attempts = 0
    estimated_cost = 0.0
    actual_models: set[str] = set()
    successful_desks = 0
    for role in ALL_DESKS:
        if config.live_ai and not secret:
            desk_outputs.append({
                "role": role.value,
                "status": "unavailable",
                "reason": "deepseek_process_credential_missing",
                "physical_call": False,
            })
            continue
        desk_orchestration_attempts += 1
        calls_before = _physical_model_call_count(agent)
        try:
            prior_desk_evidence = tuple(
                {
                    "role": item.get("role"),
                    "status": item.get("status"),
                    "summary": dict(item.get("output", {}) or {}).get(
                        "advisory_summary"
                    ),
                }
                for item in desk_outputs
            )
            output = agent.advise(
                DeepSeekAdvisoryInput(
                    role=role,
                    learning_desk_output=(
                        prior_desk_evidence
                        if role is DeepSeekAdvisoryRole.INVESTMENT_COMMITTEE
                        else None
                    ),
                    quant_firm_decision_report_summary=evidence,
                    research_committee_summary=evidence,
                    information_agent_summary=validated["information_signals"],
                    current_parameters={"manual_workflow": True, "candidate_count": len(symbols)},
                    market_regime="not_supplied",
                    run_label=f"manual:{decision_session}:{role.value}",
                )
            )
            payload = _jsonable(output)
            fallback = bool(payload.get("is_fallback", False))
            call_delta = max(
                0,
                _physical_model_call_count(agent) - calls_before,
            )
            physical_call = bool(call_delta) and not fallback
            if physical_call:
                physical_calls += call_delta
            model = str(payload.get("used_model") or "").strip()
            usage = payload.get("raw_response_usage")
            valid_real_response = bool(
                physical_call
                and not fallback
                and model
                and model != "deterministic_fallback"
                and isinstance(usage, Mapping)
            )
            status = (
                "fallback"
                if fallback
                else "succeeded"
                if valid_real_response
                else "unverified_non_transport_response"
            )
            if valid_real_response:
                successful_desks += 1
                actual_models.add(model)
                estimated_cost += _estimated_output_cost(payload, now)
            desk_outputs.append({
                "role": role.value,
                "status": status,
                "physical_call": physical_call,
                "output": payload,
            })
        except Exception as exc:
            call_delta = max(
                0,
                _physical_model_call_count(agent) - calls_before,
            )
            physical_calls += call_delta
            desk_outputs.append({
                "role": role.value,
                "status": "failed",
                "physical_call": bool(call_delta),
                "error_type": type(exc).__name__,
                "sanitized_error": _sanitize_error(exc, secret),
            })

    candidate_decisions = _manual_candidate_decisions(validated, desk_outputs)
    if successful_desks == len(ALL_DESKS):
        advisory_status = "all_desks_succeeded"
    elif successful_desks > 0:
        advisory_status = "partial_desk_success"
    elif config.live_ai and not secret:
        advisory_status = "credential_unavailable_watchlist_retained"
    else:
        advisory_status = "all_desks_failed_or_fell_back_watchlist_retained"
    plan = _manual_experience_plan(
        validated,
        candidate_decisions,
        desk_outputs,
        generated_at=now.isoformat(),
    )
    plan_path = write_json_atomic(plan, root / "manual_plan.json")
    marker = dict(install_marker_bundle(root / "tdx_marker_bundle"))
    report: dict[str, Any] = {
        "schema_version": MANUAL_SYSTEM_VERSION,
        "phase": "after-close",
        "status": "completed",
        "generated_at": now.isoformat(),
        "production_input_path": str(Path(config.production_input_path)),
        "production_input_validation": validated["validation"],
        "decision_session": decision_session,
        "execution_session": target_session,
        "original_deterministic_candidates": list(symbols),
        "final_watchlist": list(symbols),
        "watchlist_preserved": True,
        "candidate_decisions": candidate_decisions,
        "deepseek": {
            "status": advisory_status,
            "live_enabled": bool(config.live_ai),
            "process_credential_present": bool(secret),
            "desk_count": len(ALL_DESKS),
            "desk_orchestration_attempts": desk_orchestration_attempts,
            "successful_desk_count": successful_desks,
            "failed_or_fallback_desk_count": len(ALL_DESKS) - successful_desks,
            "physical_model_calls": physical_calls,
            "actual_models": sorted(actual_models),
            "estimated_api_cost_usd": round(estimated_cost, 10),
            "cost_is_estimated": True,
            "desks": desk_outputs,
        },
        "experience_plan_path": plan_path,
        "marker_adapter": marker,
        "tdx_publication": {
            "status": "not_attempted_before_durable_report",
            "block_code": config.tq_block_code,
            "block_name": config.tq_block_name,
            "visibility_success": False,
        },
        "obsolete_manual_gates": {
            "account_capability_policy": "not_part_of_manual_workflow",
            "fee_profile": "not_part_of_manual_workflow",
            "manifest_digest_equality": "not_part_of_manual_workflow",
            "continuous_paper": "not_part_of_manual_workflow",
            "postgresql_or_grafana": "not_part_of_manual_workflow",
            "portfolio_or_order_generation": "not_part_of_manual_workflow",
        },
        "broker_calls": 0,
        "order_submission_calls": 0,
    }
    json_path = write_json_atomic(report, root / "after_close_report.json")
    markdown_path = write_text_atomic(_after_close_markdown(report), root / "after_close_report.md")
    report["durable_report_path"] = json_path
    report["human_report_path"] = markdown_path
    report["durable_report_existed_before_tdx_publication"] = Path(json_path).is_file()

    if visibility_publisher is not None:
        try:
            publication = visibility_publisher(plan, json_path)
        except Exception as exc:
            publication = _publication_failure(exc, secret, config)
    elif config.tdx_user_dir is not None:
        try:
            publication = publish_plan_to_installed_tq(
                plan,
                tdx_user_dir=config.tdx_user_dir,
                initialize_path=__file__,
                block_code=config.tq_block_code,
                block_name=config.tq_block_name,
                show=config.tq_block_show,
            )
        except Exception as exc:
            publication = _publication_failure(exc, secret, config)
    else:
        publication = {
            "status": "not_requested",
            "block_code": config.tq_block_code,
            "block_name": config.tq_block_name,
            "published_symbols": [],
            "visibility_success": False,
        }
    report["tdx_publication"] = _jsonable(publication)
    write_json_atomic(report, json_path)
    write_text_atomic(_after_close_markdown(report), markdown_path)
    return report


def run_intraday(
    config: IntradayConfig,
    *,
    provider: Any | None = None,
    tq_publisher: Any | None = None,
    collector_factory: Callable[..., Any] = LiveLevel1Collector,
) -> Mapping[str, Any]:
    """Start Level-1 monitoring without an account, database, or paper cycle."""

    if config.duration_seconds < 0:
        raise ValueError("duration_seconds must be non-negative")
    if config.history_count <= 0:
        raise ValueError("history_count must be positive")
    root = Path(config.system_dir)
    plan = _require_mapping(_load_json(root / "manual_plan.json"), "manual_plan.json")
    symbols = experience_plan_symbols(plan)
    if not symbols:
        raise ValueError("manual plan has no symbols")
    holdings = _load_holdings(config.holdings_path)
    base_provider = provider or TDXLevel1Provider(config.tdx_user_dir)
    resilient = ResilientTDXProvider(base_provider)
    market_store = ManualMarketDataStore(root / "intraday")
    history: list[NormalizedIntradayBar] = []
    history_errors: list[Mapping[str, Any]] = []
    initialized = False
    collector = None
    try:
        resilient.initialize()
        initialized = True
        history = list(_fetch_history_by_symbol(
            base_provider,
            symbols,
            start_time=config.start_time,
            end_time=config.end_time,
            count=config.history_count,
            errors=history_errors,
        ))
        market_store.persist_market_data((), history)
        engine = TDXPredictionEngineV1(
            symbols,
            config=PredictionEngineConfig(
                feature_interval_minutes=int(config.feature_interval_minutes),
                prediction_start_timestamp=f"{plan['target_session']}T09:30:00+08:00",
            ),
            context=prediction_context_from_experience_plan(plan),
        )
        delegate = tq_publisher
        if delegate is None and config.publish_to_tq:
            delegate = LiveTQVisibilityPublisher(api=getattr(base_provider, "_api", None))
        marker_publisher = PersistentMarkerPublisher(
            root / "intraday",
            delegate=delegate,
            holdings=holdings,
        )
        marker_publisher.initialize_wait_states(
            symbols,
            timestamp=f"{plan['target_session']}T09:30:00+08:00",
            reference_prices={
                str(item.get("symbol")): item.get("reference_close")
                for item in plan.get("candidates", ())
                if isinstance(item, Mapping)
            },
        )
        marker_publisher.restore_transport_baseline()
        prediction_sink = LiveShadowPredictionSink(
            market_store,
            engine,
            output_dir=str(root / "intraday"),
            publisher=marker_publisher,
        )
        prediction_sink.prime(tuple(history))
        collector = collector_factory(
            resilient,
            symbols,
            sink=prediction_sink,
            storage_backend="atomic_files",
            poll_interval_seconds=float(config.poll_interval_seconds),
            shadow=True,
        )
        collector_report = collector.run(float(config.duration_seconds))
        initialized = False  # collector owns provider shutdown
        report = {
            "schema_version": MANUAL_SYSTEM_VERSION,
            "phase": "intraday",
            "status": "completed",
            "service_started": True,
            "symbols": list(symbols),
            "experience_plan_id": plan.get("plan_id"),
            "historical_prime_bar_count": len(history),
            "history_errors": history_errors,
            "symbol_runtime_errors": resilient.errors,
            "collector": _jsonable(collector_report),
            "prediction": prediction_sink.report(),
            "marker_adapter": marker_publisher.report(),
            "state_machine": {
                "states": ["WAIT", "ENTRY", "HOLD", "WEAKENING", "EXIT", "INVALIDATED"],
                "engine_wait_alias": "WATCH",
                "initial_wait_persisted": True,
                "visible_markers": ["ENTRY", "HOLD", "WEAKENING", "EXIT", "INVALIDATED"],
            },
            "holdings_optional": True,
            "holdings_supplied": bool(holdings),
            "manual_t1_policy": "exit alerts are annotated with optional sellable quantity; holdings never gate monitoring",
            "market_data_path": str(market_store.path),
            "broker_calls": 0,
            "order_submission_calls": 0,
            "deepseek_live_calls": 0,
        }
    finally:
        if initialized:
            try:
                resilient.close()
            except Exception:
                pass
    report_path = write_json_atomic(report, root / "intraday_report.json")
    report["report_path"] = report_path
    write_json_atomic(report, report_path)
    return report


def run_end_of_day(config: EndOfDayConfig) -> Mapping[str, Any]:
    """Build candidate and signal outcomes from persisted, timestamped facts."""

    root = Path(config.system_dir)
    after = _require_mapping(_load_json(root / "after_close_report.json"), "after_close_report.json")
    plan = _require_mapping(_load_json(root / "manual_plan.json"), "manual_plan.json")
    market = _require_mapping(_load_json(root / "intraday" / "market_data.json", default={}), "market_data.json")
    marker_events = _load_json(root / "intraday" / "marker_events.json", default=[])
    if not isinstance(marker_events, list):
        raise ValueError("marker_events.json must contain an array")
    bars = tuple(item for item in market.get("bars", ()) if isinstance(item, Mapping))
    symbols = tuple(str(item) for item in after.get("original_deterministic_candidates", ()))
    target_session = str(plan.get("target_session", ""))
    by_symbol = {
        symbol: sorted(
            (
                dict(bar) for bar in bars
                if str(bar.get("symbol")) == symbol
                and str(bar.get("start", ""))[:10] == target_session
            ),
            key=lambda item: str(item.get("end", "")),
        )
        for symbol in symbols
    }
    decisions = {
        str(item.get("symbol")): item
        for item in after.get("candidate_decisions", ())
        if isinstance(item, Mapping)
    }
    candidates = []
    for symbol in symbols:
        decision = decisions.get(symbol, {})
        reference = _optional_float(decision.get("reference_close"))
        close = _optional_float(by_symbol[symbol][-1].get("close")) if by_symbol[symbol] else None
        change = close / reference - 1.0 if close is not None and reference and reference > 0 else None
        candidates.append({
            "symbol": symbol,
            "decision_close": reference,
            "target_close": close,
            "close_to_close_return": round(change, 8) if change is not None else None,
            "classification": "hit" if change is not None and change > 0 else "miss" if change is not None else "unresolved",
            "bar_count": len(by_symbol[symbol]),
        })
    transitions = [dict(item) for item in marker_events if isinstance(item, Mapping) and str(item.get("symbol")) in symbols]
    signal_outcomes = [
        _manual_signal_outcome(item, by_symbol.get(str(item.get("symbol")), ()))
        for item in transitions
        if str(item.get("state")) in {"ENTRY", "HOLD", "WEAKENING", "EXIT", "INVALIDATED"}
    ]
    counts = {
        "hit": sum(item["classification"] == "hit" for item in signal_outcomes),
        "miss": sum(item["classification"] == "miss" for item in signal_outcomes),
        "unresolved": sum(item["classification"] == "unresolved" for item in signal_outcomes),
    }
    report = {
        "schema_version": MANUAL_SYSTEM_VERSION,
        "phase": "end-of-day",
        "status": "completed",
        "target_session": target_session,
        "original_deterministic_candidates": list(symbols),
        "deepseek_desks": dict(after.get("deepseek", {})).get("desks", []),
        "final_manual_decisions": after.get("candidate_decisions", []),
        "intraday_state_transitions": transitions,
        "entry_marker_timestamps": [item.get("timestamp") for item in transitions if item.get("state") == "ENTRY"],
        "exit_marker_timestamps": [item.get("timestamp") for item in transitions if item.get("state") in {"EXIT", "INVALIDATED"}],
        "candidate_outcomes": candidates,
        "signal_relative_outcomes": signal_outcomes,
        "candidate_accuracy_counts": {
            "hit": sum(item["classification"] == "hit" for item in candidates),
            "miss": sum(item["classification"] == "miss" for item in candidates),
            "unresolved": sum(item["classification"] == "unresolved" for item in candidates),
        },
        "signal_accuracy_counts": counts,
        "unresolved_or_missing_data": [
            item for item in (*candidates, *signal_outcomes)
            if item.get("classification") == "unresolved"
        ],
        "api_physical_call_count": dict(after.get("deepseek", {})).get("physical_model_calls", 0),
        "estimated_api_cost_usd": dict(after.get("deepseek", {})).get("estimated_api_cost_usd", 0.0),
        "tdx_publication_status": after.get("tdx_publication"),
        "marker_adapter_status": _load_json(root / "intraday_report.json", default={}).get("marker_adapter"),
        "no_lookahead_audit": {
            "passed": all(item.get("strictly_later_close", True) for item in signal_outcomes),
            "rule": "each signal outcome uses only the final persisted bar whose end is later than the signal timestamp",
        },
        "broker_calls": 0,
        "order_submission_calls": 0,
    }
    json_path = write_json_atomic(report, root / "end_of_day_report.json")
    markdown_path = write_text_atomic(_end_of_day_markdown(report), root / "end_of_day_report.md")
    report["report_path"] = json_path
    report["human_report_path"] = markdown_path
    write_json_atomic(report, json_path)
    return report


def load_manual_production_input(path: str | Path) -> Mapping[str, Any]:
    """Minimal correctness validation without manifest/account/Paper gates."""

    payload = _require_mapping(_load_json(Path(path)), "production input")
    raw_symbols = payload.get("symbols")
    if not isinstance(raw_symbols, Sequence) or isinstance(raw_symbols, (str, bytes, bytearray)):
        raise ValueError("production input symbols must be a sequence")
    symbols = tuple(dict.fromkeys(canonicalize_tdx_level1_symbol(item) for item in raw_symbols))
    if not symbols or len(symbols) > 6 or any(not _SYMBOL_PATTERN.fullmatch(symbol) for symbol in symbols):
        raise ValueError("production input must contain one to six SH/SZ symbols")
    provenance = dict(payload.get("information_provenance", {}) or {})
    bridge = dict(provenance.get("daily_production_input_v1", {}) or {})
    context = dict(payload.get("quant_firm_context", {}) or {})
    daily = dict(context.get("daily_production_input_v1", {}) or {})
    decision = str(bridge.get("decision_session") or daily.get("decision_session") or "")
    execution = str(daily.get("execution_session") or "")
    if not decision or not execution:
        raise ValueError("production input is missing decision/execution sessions")
    datetime.fromisoformat(decision)
    datetime.fromisoformat(execution)
    bars = payload.get("bars")
    if not isinstance(bars, Sequence) or isinstance(bars, (str, bytes, bytearray)):
        raise ValueError("production input bars must be a sequence")
    normalized_bars = []
    for item in bars:
        if not isinstance(item, Mapping):
            raise ValueError("production input bar must be an object")
        symbol = canonicalize_tdx_level1_symbol(item.get("symbol", ""))
        bar_date = str(item.get("date", ""))
        if symbol not in symbols:
            continue
        if not bar_date or bar_date > decision:
            raise ValueError("production input contains future market rows")
        close = _optional_float(item.get("close"))
        if close is None or close <= 0:
            raise ValueError("production input contains invalid close")
        normalized_bars.append(dict(item, symbol=symbol))
    if any(not any(row["symbol"] == symbol for row in normalized_bars) for symbol in symbols):
        raise ValueError("each production symbol requires at least one bounded bar")
    information_signals = _bounded_information_signals(
        payload.get("information_signals", ()),
        decision_session=decision,
    )
    selected_scores = {
        str(key): float(value)
        for key, value in dict(bridge.get("selected_scores", {}) or {}).items()
        if _optional_float(value) is not None
    }
    return {
        "payload": payload,
        "symbols": symbols,
        "bars": tuple(normalized_bars),
        "information_signals": information_signals,
        "decision_session": decision,
        "execution_session": execution,
        "selected_scores": selected_scores,
        "validation": {
            "minimal_manual_contract": True,
            "future_market_rows": 0,
            "candidate_count": len(symbols),
            "account_capability_checked": False,
            "fee_profile_checked": False,
            "manifest_digest_equality_checked": False,
            "continuous_paper_checked": False,
            "database_checked": False,
        },
    }


def acceptance_summary(after: Mapping[str, Any], intraday: Mapping[str, Any]) -> Mapping[str, Any]:
    deepseek = dict(after.get("deepseek", {}) or {})
    publication = dict(after.get("tdx_publication", {}) or {})
    marker = dict(intraday.get("marker_adapter", {}) or {})
    checks = {
        "physical_model_calls_positive": int(deepseek.get("physical_model_calls", 0)) > 0,
        "successful_desk_count_positive": int(deepseek.get("successful_desk_count", 0)) > 0,
        "actual_model_present": bool(deepseek.get("actual_models")),
        "durable_ai_report_exists": Path(str(after.get("durable_report_path", ""))).is_file(),
        "final_watchlist_nonempty": bool(after.get("final_watchlist")),
        "qpty_publication_succeeded": publication.get("visibility_success") is True,
        "intraday_service_started": intraday.get("service_started") is True,
        "marker_adapter_initialized": marker.get("marker_adapter_initialized") is True,
        "broker_calls_zero": after.get("broker_calls") == intraday.get("broker_calls") == 0,
        "order_submission_calls_zero": after.get("order_submission_calls") == intraday.get("order_submission_calls") == 0,
    }
    automated_checks_passed = all(checks.values())
    return {
        "schema_version": "quantpilot_manual_windows_acceptance_v1",
        "accepted": False,
        "automated_checks_passed": automated_checks_passed,
        "acceptance_status": (
            "automated_runtime_passed_chart_observation_pending"
            if automated_checks_passed
            else "automated_runtime_failed"
        ),
        "checks": checks,
        "physical_model_calls": deepseek.get("physical_model_calls", 0),
        "successful_desk_count": deepseek.get("successful_desk_count", 0),
        "actual_deepseek_models": deepseek.get("actual_models", []),
        "durable_ai_report_path": after.get("durable_report_path"),
        "final_watchlist": after.get("final_watchlist", []),
        "qpty_publication": publication,
        "intraday_service_can_start": intraday.get("service_started", False),
        "marker_adapter_initialized": marker.get("marker_adapter_initialized", False),
        "ordinary_chart_overlay_status": marker.get("ordinary_chart_overlay_status"),
        "ordinary_chart_overlay_proven": False,
        "visible_marker_observation_required": True,
        "transport_success_is_visual_proof": False,
        "broker_calls": 0,
        "order_submission_calls": 0,
    }


def _advisory_evidence(value: Mapping[str, Any]) -> Mapping[str, Any]:
    latest = _latest_bars(value["bars"])
    return {
        "manual_workflow": True,
        "decision_session": value["decision_session"],
        "execution_session": value["execution_session"],
        "ordered_deterministic_watchlist": list(value["symbols"]),
        "selected_scores": value["selected_scores"],
        "latest_bars": latest,
        "information_signals": _jsonable(value["information_signals"]),
        "instruction": "annotate and rank risks, but never remove a deterministic candidate or emit an order",
    }


def _manual_candidate_decisions(
    value: Mapping[str, Any], desks: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    latest = _latest_bars(value["bars"])
    summaries = [
        {
            "role": item.get("role"),
            "status": item.get("status"),
            "summary": dict(item.get("output", {}) or {}).get("advisory_summary"),
        }
        for item in desks
    ]
    output = []
    for rank, symbol in enumerate(value["symbols"], start=1):
        score = value["selected_scores"].get(symbol)
        output.append({
            "symbol": symbol,
            "candidate_rank": rank,
            "quant_score": score,
            "reference_close": latest[symbol]["close"],
            "manual_decision": "WAIT",
            "deepseek_stance": _structured_stance(desks, symbol),
            "desk_summaries": summaries,
            "watchlist_retained_regardless_of_ai": True,
            "broker_action": None,
            "order": None,
        })
    return output


def _manual_experience_plan(
    value: Mapping[str, Any], decisions: Sequence[Mapping[str, Any]],
    desks: Sequence[Mapping[str, Any]], *, generated_at: str,
) -> Mapping[str, Any]:
    plan_id = "manual-plan-" + _digest({
        "decision_session": value["decision_session"],
        "execution_session": value["execution_session"],
        "symbols": value["symbols"],
    })[:24]
    candidates = []
    for item in decisions:
        score = _optional_float(item.get("quant_score"))
        confidence = 0.5 if score is None else 1.0 / (1.0 + math.exp(-max(-20.0, min(20.0, score))))
        candidates.append({
            "symbol": item["symbol"],
            "name": None,
            "candidate_rank": item["candidate_rank"],
            "quant_score": score,
            "reference_close": item.get("reference_close"),
            "candidate_confidence": round(confidence, 8),
            "direction": "long",
            "stance": item["deepseek_stance"],
            "stance_provenance": "manual_after_close_deepseek_advisory",
            "deepseek_stance": item["deepseek_stance"],
            "deepseek_stance_provenance": "manual_after_close_deepseek_advisory",
            "ai_conclusion": {"desks": item["desk_summaries"]},
            "key_reasons": ("authoritative_daily_production_input",),
            "risks": (),
            "provenance": {
                "experience_plan_id": plan_id,
                "source": "daily_production_input_existing_order",
                "evidence_refs": (f"production_input:{value['decision_session']}:{item['symbol']}",),
            },
            "timestamps": {
                "data_asof": f"{value['decision_session']}T15:00:00+08:00",
                "candidate_timestamp": f"{value['decision_session']}T15:00:00+08:00",
                "plan_generated_at": generated_at,
                "target_session": value["execution_session"],
            },
        })
    role_rows = []
    for item in desks:
        payload = dict(item.get("output", {}) or {})
        if not payload.get("advisory_summary"):
            continue
        role_rows.append({
            "role": item["role"],
            "summary": payload["advisory_summary"],
            "confidence": payload.get("confidence", 0.0),
            "risk_notes": payload.get("risk_notes", ()),
            "evidence_refs": payload.get("evidence_used", ()),
            "source": "quant_firm.DeepSeekAdvisoryAgent",
            "data_asof": generated_at,
            "stance": "neutral",
        })
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "plan_id": plan_id,
        "generated_at": generated_at,
        "decision_session": value["decision_session"],
        "target_session": value["execution_session"],
        "data_asof": f"{value['decision_session']}T15:00:00+08:00",
        "symbols": list(value["symbols"]),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "ai_analysis": {
            "roles": role_rows,
            "per_tick_deepseek_calls_permitted": False,
        },
        "broker_or_order_api_calls": False,
    }


def _fetch_history_by_symbol(
    provider: Any, symbols: Sequence[str], *, start_time: str, end_time: str,
    count: int, errors: list[Mapping[str, Any]],
) -> tuple[NormalizedIntradayBar, ...]:
    output = []
    method = getattr(provider, "get_historical_intraday_bars", None)
    if not callable(method):
        return ()
    for symbol in symbols:
        try:
            output.extend(method(
                (symbol,), period="1m",
                fields=("Open", "High", "Low", "Close", "Volume", "Amount"),
                start_time=start_time, end_time=end_time, count=int(count),
                dividend_type="none", fill_data=False,
            ))
        except Exception as exc:
            errors.append(_runtime_error("historical_bars", symbol, exc))
    return tuple(sorted(output, key=lambda bar: (bar.end, bar.symbol)))


def _manual_signal_outcome(signal: Mapping[str, Any], bars: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    timestamp = str(signal.get("timestamp") or signal.get("decision_timestamp") or "")
    later = [bar for bar in bars if str(bar.get("end", "")) > timestamp]
    final_close = _optional_float(later[-1].get("close")) if later else None
    decision_price = _optional_float(signal.get("decision_price"))
    state = str(signal.get("state", ""))
    expected_up = state in {"ENTRY", "HOLD"}
    value = final_close / decision_price - 1.0 if final_close is not None and decision_price and decision_price > 0 else None
    signed = value if expected_up else -value if value is not None else None
    return {
        "signal_id": signal.get("signal_id"),
        "symbol": signal.get("symbol"),
        "state": state,
        "timestamp": timestamp,
        "decision_price": decision_price,
        "target_close": final_close,
        "signal_relative_return": round(value, 8) if value is not None else None,
        "classification": "hit" if signed is not None and signed > 0 else "miss" if signed is not None else "unresolved",
        "strictly_later_close": all(str(bar.get("end", "")) > timestamp for bar in later),
        "reason": signal.get("reason_code"),
    }


def _latest_bars(bars: Sequence[Mapping[str, Any]]) -> Mapping[str, Mapping[str, Any]]:
    output: dict[str, Mapping[str, Any]] = {}
    for item in sorted(bars, key=lambda row: (str(row.get("date", "")), str(row.get("symbol", "")))):
        output[str(item["symbol"])] = dict(item)
    return output


def _bounded_information_signals(
    value: Any,
    *,
    decision_session: str,
) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError("production input information_signals must be a sequence")
    cutoff = datetime.fromisoformat(f"{decision_session}T15:00:00+08:00")
    output = []
    for item in value:
        if not isinstance(item, Mapping):
            raise ValueError("information signal must be a structured PIT object")
        if "signal" not in item or "available_at" not in item:
            raise ValueError("information signal requires signal and available_at")
        available = datetime.fromisoformat(str(item["available_at"]))
        if available.tzinfo is None or available.utcoffset() is None:
            raise ValueError("information signal available_at must be timezone-aware")
        if available.astimezone(SHANGHAI_TZ) > cutoff:
            raise ValueError("production input contains a future information signal")
        output.append(dict(item))
    return tuple(output)


def _structured_stance(desks: Sequence[Mapping[str, Any]], symbol: str) -> str:
    for desk in desks:
        raw = dict(desk.get("output", {}) or {}).get("raw_model_response")
        if not isinstance(raw, str):
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        candidates = payload.get("symbols") if isinstance(payload, Mapping) else None
        if isinstance(candidates, Sequence) and not isinstance(candidates, (str, bytes, bytearray)):
            for item in candidates:
                if isinstance(item, Mapping) and str(item.get("symbol")) == symbol:
                    stance = str(item.get("stance", item.get("direction", "neutral"))).lower()
                    return stance if stance in {"bullish", "bearish", "neutral"} else "neutral"
    return "neutral"


def _estimated_output_cost(payload: Mapping[str, Any], now: datetime) -> float:
    model = str(payload.get("used_model") or "")
    usage = payload.get("raw_response_usage")
    if model not in DEFAULT_MODEL_PRICES or not isinstance(usage, Mapping):
        return 0.0
    input_tokens = int(usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0)
    output_tokens = int(usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0)
    details = usage.get("prompt_tokens_details")
    cache_hits = int(usage.get("prompt_cache_hit_tokens", 0) or 0)
    if isinstance(details, Mapping):
        cache_hits = int(details.get("cached_tokens", cache_hits) or 0)
    return estimate_model_call_cost_usd(
        model,
        TokenEstimate(input_tokens=input_tokens, output_tokens=output_tokens,
                      cache_hit_input_tokens=cache_hits),
        is_peak=is_peak_bjt(now),
    )


def _physical_model_call_count(agent: Any) -> int:
    value = getattr(agent, "physical_model_calls", 0)
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _load_holdings(path: str | Path | None) -> Mapping[str, Mapping[str, Any]]:
    if path is None:
        return {}
    value = _require_mapping(_load_json(Path(path)), "holdings")
    rows = value.get("holdings", value)
    if not isinstance(rows, Mapping):
        raise ValueError("holdings must be a symbol-keyed object")
    return {
        canonicalize_tdx_level1_symbol(symbol): dict(item)
        for symbol, item in rows.items() if isinstance(item, Mapping)
    }


def _event_record(event: Any) -> Mapping[str, Any]:
    return {
        "symbol": str(event.symbol),
        "timestamp": event.timestamp.isoformat(),
        "received_at": event.received_at.isoformat(),
        "last_price": float(event.last_price),
        "cumulative_volume_shares": event.cumulative_volume_shares,
        "cumulative_amount_cny": event.cumulative_amount_cny,
        "buy1": event.buy1,
        "sell1": event.sell1,
        "timestamp_source": event.timestamp_source,
    }


def _bar_record(bar: NormalizedIntradayBar) -> Mapping[str, Any]:
    return {
        "symbol": bar.symbol,
        "start": bar.start.isoformat(),
        "end": bar.end.isoformat(),
        "interval_minutes": bar.interval_minutes,
        "open": bar.open, "high": bar.high, "low": bar.low, "close": bar.close,
        "volume": bar.volume, "amount": bar.amount,
        "average_price": bar.average_price,
        "event_count": bar.event_count,
        "missing_minutes_before": bar.missing_minutes_before,
        "partial": bar.partial,
    }


def _runtime_error(stage: str, symbol: str, exc: Exception) -> Mapping[str, Any]:
    return {
        "stage": stage,
        "symbol": symbol,
        "error_type": type(exc).__name__,
        "sanitized_error": _sanitize_error(exc, os.environ.get(DEEPSEEK_CREDENTIAL_ENV)),
    }


def _publication_failure(exc: Exception, secret: str | None, config: AfterCloseConfig) -> Mapping[str, Any]:
    return {
        "status": "failed_nonblocking",
        "error_type": type(exc).__name__,
        "sanitized_error": _sanitize_error(exc, secret),
        "block_code": config.tq_block_code,
        "block_name": config.tq_block_name,
        "published_symbols": [],
        "visibility_success": False,
    }


def _sanitize_error(exc: Exception, secret: str | None) -> str:
    text = " ".join(str(exc).split())
    if secret:
        text = text.replace(secret, "<redacted>")
    text = re.sub(r"(?i)(api[_-]?key|token|authorization)\s*[:=]\s*[^\s,;]+", r"\1=<redacted>", text)
    return text[:500]


def _after_close_markdown(report: Mapping[str, Any]) -> str:
    deepseek = dict(report.get("deepseek", {}) or {})
    lines = [
        "# QuantPilot Manual After-Close Report",
        "",
        f"Decision session: {report.get('decision_session')}",
        f"Next session: {report.get('execution_session')}",
        f"Watchlist: {', '.join(report.get('final_watchlist', ())) }",
        f"DeepSeek physical calls: {deepseek.get('physical_model_calls', 0)}",
        f"Successful desks: {deepseek.get('successful_desk_count', 0)} / {deepseek.get('desk_count', 0)}",
        f"Estimated API cost (USD): {deepseek.get('estimated_api_cost_usd', 0.0)}",
        f"QPTY publication: {dict(report.get('tdx_publication', {}) or {}).get('visibility_success', False)}",
        "",
        "## Candidate decisions",
    ]
    for item in report.get("candidate_decisions", ()):
        lines.append(
            f"- {item.get('candidate_rank')}. {item.get('symbol')}: "
            f"WAIT; AI={item.get('deepseek_stance')}"
        )
    lines.extend(("", "Broker calls: 0", "Order submission calls: 0"))
    return "\n".join(lines)


def _end_of_day_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# QuantPilot Manual End-of-Day Report", "",
        f"Target session: {report.get('target_session')}",
        f"Candidates: {', '.join(report.get('original_deterministic_candidates', ())) }",
        f"Candidate accuracy: {report.get('candidate_accuracy_counts')}",
        f"Signal accuracy: {report.get('signal_accuracy_counts')}",
        "", "## Candidate outcomes",
    ]
    for item in report.get("candidate_outcomes", ()):
        lines.append(f"- {item.get('symbol')}: {item.get('classification')} ({item.get('close_to_close_return')})")
    lines.extend(("", "Broker calls: 0", "Order submission calls: 0"))
    return "\n".join(lines)


def _load_json(path: Path, *, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        if default is not None:
            return default
        raise


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _optional_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(_jsonable(value), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value
