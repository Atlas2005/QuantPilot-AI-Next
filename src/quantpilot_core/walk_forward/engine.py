"""Rolling out-of-sample walk-forward paper evaluation engine."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Mapping

import pandas as pd

from quantpilot_core.execution_candidate import build_execution_candidate_report
from quantpilot_core.execution_optimizer import OptimizationAssumption, build_portfolio_allocation_plan
from quantpilot_core.order_intent import OrderIntentController
from quantpilot_core.paper_trading import PaperAccount, run_paper_trading_loop
from quantpilot_core.quant_firm import DeepSeekAdvisoryRole, run_deepseek_advisory_fallback
from quantpilot_core.walk_forward.contracts import (
    WalkForwardInput,
    WalkForwardResult,
    WalkForwardWindow,
    WalkForwardWindowContext,
    WalkForwardWindowExecutionResult,
    WalkForwardWindowResult,
    WindowRunnerFactory,
)
from quantpilot_core.walk_forward.leakage import LeakageGuard, _as_timestamp


class WalkForwardEngine:
    """Run deterministic train-before-test paper evaluation windows.

    When *window_runner_factory* is provided the engine delegates
    test-phase execution to a typed ``WindowRunner`` (PR #115).  When
    *window_runner_factory* is ``None`` the legacy ``exec1→exec2→
    proposal→run_paper_trading_loop`` path is used — fully backward
    compatible.

    The engine never touches temp directories, state files, or account
    types — those belong to the runner factory and the caller.
    """

    def __init__(
        self,
        leakage_guard: LeakageGuard | None = None,
        window_runner_factory: WindowRunnerFactory | None = None,
    ) -> None:
        self.leakage_guard = leakage_guard or LeakageGuard()
        self._runner_factory = window_runner_factory  # None → legacy default

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self, walk_input: WalkForwardInput) -> WalkForwardResult:
        if walk_input.advisory_mode not in {"disabled", "fallback_only", "evidence_only"}:
            raise ValueError("advisory_mode must be disabled, fallback_only, or evidence_only")
        if not walk_input.windows:
            raise ValueError("at least one walk-forward window is required")

        window_results: list[WalkForwardWindowResult] = []
        accepted_updates: list[Mapping[str, Any]] = []
        rejected_updates: list[Mapping[str, Any]] = []
        leakage_checks: list[str] = []
        parameters = dict(walk_input.current_parameters)

        # --- runner path (PR #115) ---
        if self._runner_factory is not None:
            runner = self._runner_factory.create_runner(
                initial_capital=float(walk_input.initial_cash),
            )
            for window in walk_input.windows:
                self.leakage_guard.check_window_order(window)
                train_prices = _slice_train(walk_input.historical_price_frame, window)
                test_prices = _slice_test(walk_input.historical_price_frame, window)
                train_signals = _slice_train(walk_input.historical_signal_frame, window)
                train_events = _slice_train(walk_input.information_events, window)
                self.leakage_guard.assert_train_phase_data(train_prices, window, label="train_price_frame")
                self.leakage_guard.assert_train_phase_data(train_signals, window, label="train_signal_frame")
                self.leakage_guard.assert_train_phase_data(train_events, window, label="information_events")
                self.leakage_guard.assert_paper_trading_data(test_prices, window, label="test_price_frame")
                leakage_checks.append(f"{window.run_label}:train_and_test_slices_validated")

                train_summary = _train_summary(train_prices, train_signals, train_events, window, walk_input.metadata)
                advisory_summary = self._advisory_summary(walk_input, window, train_summary)

                ctx = WalkForwardWindowContext(
                    window=window,
                    test_prices=test_prices,
                    train_summary=train_summary,
                    parameters=dict(parameters),
                    metadata=dict(walk_input.metadata),
                    initial_capital=float(walk_input.initial_cash),
                )
                exec_result = runner.run_window(ctx)

                # Convert typed result to legacy-compatible dicts
                perf = _runner_performance_metrics(exec_result)
                param_update = _frozen_baseline_parameter_update(window.run_label)
                rejected_updates.append(param_update)

                window_results.append(
                    WalkForwardWindowResult(
                        window=window,
                        train_summary=train_summary,
                        order_intent_proposal=None,
                        paper_trading_result={
                            "runner": "production_window_runner",
                            "daily_session_count": len(exec_result.daily_sessions),
                            "daily_sessions": tuple(
                                _daily_session_to_dict(s) for s in exec_result.daily_sessions
                            ),
                            "ending_equity": exec_result.ending_equity,
                        },
                        performance_metrics=perf,
                        learning_desk_output=None,
                        deepseek_advisory_summary=advisory_summary,
                        leakage_warnings=(),
                        parameter_update_recommendation=param_update,
                    )
                )

            aggregate = _aggregate_metrics(window_results)
            return WalkForwardResult(
                window_results=tuple(window_results),
                aggregate_metrics=aggregate,
                accepted_parameter_updates=tuple(accepted_updates),
                rejected_parameter_updates=tuple(rejected_updates),
                leakage_checks=tuple(leakage_checks),
                improvement_summary=_improvement_summary(window_results),
            )

        # --- legacy default path (fully backward compatible) ---
        account = PaperAccount(cash=float(walk_input.initial_cash))
        for window in walk_input.windows:
            self.leakage_guard.check_window_order(window)
            train_prices = _slice_train(walk_input.historical_price_frame, window)
            test_prices = _slice_test(walk_input.historical_price_frame, window)
            train_signals = _slice_train(walk_input.historical_signal_frame, window)
            train_events = _slice_train(walk_input.information_events, window)
            self.leakage_guard.assert_train_phase_data(train_prices, window, label="train_price_frame")
            self.leakage_guard.assert_train_phase_data(train_signals, window, label="train_signal_frame")
            self.leakage_guard.assert_train_phase_data(train_events, window, label="information_events")
            self.leakage_guard.assert_paper_trading_data(test_prices, window, label="test_price_frame")
            leakage_checks.append(f"{window.run_label}:train_and_test_slices_validated")

            train_summary = _train_summary(train_prices, train_signals, train_events, window, walk_input.metadata)
            advisory_summary = self._advisory_summary(walk_input, window, train_summary)
            proposal, paper_result, updated_account = _legacy_default_window_execution(
                train_prices=train_prices,
                test_prices=test_prices,
                train_signals=train_signals if _has_rows(train_signals) else _signal_rows_from_prices(train_prices),
                train_events=train_events,
                train_summary=train_summary,
                window=window,
                account=account,
                parameters=parameters,
                walk_input=walk_input,
            )
            account = updated_account
            metrics = _metrics_mapping(paper_result.metrics)
            parameter_update = _parameter_update(metrics, parameters, window.run_label)
            if bool(parameter_update.get("accepted")):
                accepted_updates.append(parameter_update)
                parameters.update(parameter_update.get("recommended_parameters", {}))
            else:
                rejected_updates.append(parameter_update)

            window_results.append(
                WalkForwardWindowResult(
                    window=window,
                    train_summary=train_summary,
                    order_intent_proposal=proposal,
                    paper_trading_result=paper_result,
                    performance_metrics=metrics,
                    learning_desk_output=paper_result.learning_desk_output,
                    deepseek_advisory_summary=advisory_summary,
                    leakage_warnings=(),
                    parameter_update_recommendation=parameter_update,
                )
            )

        aggregate = _aggregate_metrics(window_results)
        return WalkForwardResult(
            window_results=tuple(window_results),
            aggregate_metrics=aggregate,
            accepted_parameter_updates=tuple(accepted_updates),
            rejected_parameter_updates=tuple(rejected_updates),
            leakage_checks=tuple(leakage_checks),
            improvement_summary=_improvement_summary(window_results),
        )

    # ------------------------------------------------------------------
    # Advisory
    # ------------------------------------------------------------------

    def _advisory_summary(
        self,
        walk_input: WalkForwardInput,
        window: WalkForwardWindow,
        train_summary: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        if walk_input.advisory_mode == "disabled":
            return None
        payload = _evidence_packet(walk_input, window, train_summary)
        self.leakage_guard.assert_deepseek_advisory_input(
            payload,
            window,
            evidence_only=walk_input.advisory_mode == "evidence_only",
        )
        output = run_deepseek_advisory_fallback(
            DeepSeekAdvisoryRole.BACKTEST_DESK,
            vectorbt_stats=payload.get("vectorbt_stats"),
            qlib_report=payload.get("qlib_report"),
            rqalpha_artifact_summary=payload.get("rqalpha_artifact_summary"),
            current_parameters=payload.get("current_parameters"),
            research_committee_summary=payload,
            run_label=window.run_label,
        )
        return {
            "mode": walk_input.advisory_mode,
            "summary": output.advisory_summary,
            "evidence_used": output.evidence_used,
            "is_fallback": output.is_fallback,
            "used_model": output.used_model,
            "as_of": str(window.train_end),
        }


# ------------------------------------------------------------------
# Registry wrapper
# ------------------------------------------------------------------


def run_walk_forward_paper_evaluation(
    walk_forward_input: WalkForwardInput | None = None,
    **kwargs: Any,
) -> WalkForwardResult:
    """Registry-safe wrapper for deterministic walk-forward paper evaluation."""
    payload = walk_forward_input or WalkForwardInput(**kwargs)
    return WalkForwardEngine().run(payload)


# ------------------------------------------------------------------
# Legacy default window execution (extracted, unchanged behavior)
# ------------------------------------------------------------------


def _legacy_default_window_execution(
    *,
    train_prices: Any,
    test_prices: Any,
    train_signals: Any,
    train_events: Any,
    train_summary: Mapping[str, Any],
    window: WalkForwardWindow,
    account: PaperAccount,
    parameters: dict[str, Any],
    walk_input: WalkForwardInput,
) -> tuple[Any, Any, PaperAccount]:
    """Legacy exec1→exec2→proposal→run_paper_trading_loop path.

    Extracted from ``WalkForwardEngine.run()`` so the engine can
    delegate to either this path or a typed ``WindowRunner``.
    """
    exec1_report = build_execution_candidate_report(
        qlib_signals=train_signals if _has_rows(train_signals) else _signal_rows_from_prices(train_prices),
        info_signals=_info_rows_from_events(train_events),
        research_committee_output=_research_rows_from_train_summary(train_summary),
        strategy_id=str(parameters.get("strategy_id", "walk_forward")),
        top_n=int(parameters.get("top_n", 3)),
        timestamp=_as_timestamp(window.train_end).to_pydatetime(),
    )
    last_train_prices = _latest_prices(train_prices)
    assumptions = OptimizationAssumption(capital=float(parameters.get("capital", walk_input.initial_cash)))
    exec2_plan = build_portfolio_allocation_plan(
        exec1_report,
        last_prices=last_train_prices,
        assumptions=assumptions,
    )
    proposal = OrderIntentController(lot_size=int(parameters.get("lot_size", 100))).from_exec2_plan(
        exec2_plan,
        run_label=window.run_label,
    )
    paper_result = run_paper_trading_loop(proposal, test_prices, account)
    return proposal, paper_result, paper_result.account


# ------------------------------------------------------------------
# Runner-path helpers (PR #115)
# ------------------------------------------------------------------


def _runner_performance_metrics(result: WalkForwardWindowExecutionResult) -> Mapping[str, Any]:
    """Build a legacy-compatible ``performance_metrics`` dict from a typed result."""
    return {
        "net_pnl": result.net_pnl,
        "gross_pnl": result.gross_pnl,
        "ending_equity": result.ending_equity,
        "fill_rate": result.fill_rate,
        "trade_count": result.trade_count,
        "rejected_count": result.rejected_count,
        "turnover": result.turnover,
        "commission": result.commission,
        "transaction_tax": result.transaction_tax,
        "transfer_or_exchange_fee": result.transfer_or_exchange_fee,
        "slippage_cost": result.slippage_cost,
        "total_cost": result.total_cost,
        "daily_session_count": len(result.daily_sessions),
        "window_label": result.window_label,
        "intent_count": result.intent_count,
        "filled_count": result.filled_count,
        "partial_fill_count": result.partial_fill_count,
        "requested_quantity": result.requested_quantity,
        "filled_quantity": result.filled_quantity,
    }


def _daily_session_to_dict(session: Any) -> dict[str, Any]:
    """Convert an OOSDailySessionResult to a plain dict for storage."""
    from dataclasses import asdict
    return asdict(session)


def _frozen_baseline_parameter_update(run_label: str) -> Mapping[str, Any]:
    """Parameter update record for frozen-baseline mode.

    Parameters are never mutated across OOS windows — this is a
    pure evidence record, not a control signal.
    """
    return {
        "run_label": run_label,
        "accepted": False,
        "reason": "parameter_update_mode_frozen_baseline",
        "recommended_parameters": {},
    }


# ------------------------------------------------------------------
# Slice helpers
# ------------------------------------------------------------------


def _slice_train(payload: Any, window: WalkForwardWindow) -> Any:
    return _slice_between(payload, window.train_start, window.train_end)


def _slice_test(payload: Any, window: WalkForwardWindow) -> Any:
    return _slice_between(payload, window.test_start, window.test_end)


def _slice_between(payload: Any, start: Any, end: Any) -> Any:
    if payload is None:
        return None
    start_ts = _as_timestamp(start)
    end_ts = _as_timestamp(end, end_of_day=True)
    if isinstance(payload, pd.DataFrame):
        column = _date_column(payload)
        if column is None and isinstance(payload.index, pd.DatetimeIndex):
            mask = (payload.index >= start_ts) & (payload.index <= end_ts)
            return payload.loc[mask].copy()
        if column is None:
            return payload.copy()
        dates = pd.to_datetime(payload[column]).dt.tz_localize(None)
        return payload.loc[(dates >= start_ts) & (dates <= end_ts)].copy()
    if isinstance(payload, (list, tuple)):
        return tuple(item for item in payload if _row_in_range(item, start_ts, end_ts))
    if isinstance(payload, Mapping):
        if _row_has_date(payload):
            return payload if _row_in_range(payload, start_ts, end_ts) else {}
        return {key: _slice_between(value, start, end) for key, value in payload.items()}
    return payload


def _train_summary(prices: Any, signals: Any, events: Any, window: WalkForwardWindow, metadata: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "run_label": window.run_label,
        "as_of": str(window.train_end),
        "price_rows": _row_count(prices),
        "signal_rows": _row_count(signals),
        "information_event_rows": _row_count(events),
        "symbols": tuple(sorted(_symbols(prices) | _symbols(signals))),
        "vectorbt_stats": _adapter_summary(metadata.get("vectorbt_stats")),
        "qlib_report": _adapter_summary(metadata.get("qlib_report")),
        "rqalpha_artifact_summary": _adapter_summary(metadata.get("rqalpha_artifact")),
    }


def _evidence_packet(
    walk_input: WalkForwardInput,
    window: WalkForwardWindow,
    train_summary: Mapping[str, Any],
) -> Mapping[str, Any]:
    metadata = dict(walk_input.metadata)
    return {
        "as_of": str(window.train_end),
        "train_summary": train_summary,
        "current_parameters": dict(walk_input.current_parameters),
        "vectorbt_stats": _slice_or_summary(metadata.get("vectorbt_stats"), window),
        "qlib_report": _slice_or_summary(metadata.get("qlib_report"), window),
        "rqalpha_artifact_summary": _slice_or_summary(metadata.get("rqalpha_artifact"), window),
    }


def _slice_or_summary(payload: Any, window: WalkForwardWindow) -> Any:
    if payload is None:
        return None
    try:
        return _slice_train(payload, window)
    except Exception:
        return _adapter_summary(payload)


def _signal_rows_from_prices(prices: Any) -> tuple[Mapping[str, Any], ...]:
    frame = prices if isinstance(prices, pd.DataFrame) else pd.DataFrame(prices or ())
    if frame.empty:
        raise ValueError("train price slice must contain at least one row")
    rows = []
    for symbol, group in frame.groupby("symbol") if "symbol" in frame.columns else (("UNKNOWN", frame),):
        date_column = _date_column(group)
        ordered = group.sort_values(date_column) if date_column else group
        first = _number(ordered["close"].iloc[0]) if "close" in ordered else 1.0
        last = _number(ordered["close"].iloc[-1]) if "close" in ordered else first
        momentum = 0.0 if not first else max(-1.0, min(1.0, (last - first) / first))
        rows.append({"symbol": symbol, "signal_score": round(momentum, 6), "liquidity_score": 1.0})
    return tuple(rows)


def _info_rows_from_events(events: Any) -> tuple[Mapping[str, Any], ...]:
    if not _has_rows(events):
        return ()
    frame = events if isinstance(events, pd.DataFrame) else pd.DataFrame(events)
    if "symbol" not in frame.columns:
        return ()
    rows = []
    for symbol, group in frame.groupby("symbol"):
        score = group["info_score"].mean() if "info_score" in group.columns else 0.0
        rows.append({"symbol": symbol, "info_score": round(float(score), 6)})
    return tuple(rows)


def _research_rows_from_train_summary(summary: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    symbols = summary.get("symbols") or ()
    return tuple({"symbol": symbol, "research_score": 0.5} for symbol in symbols)


def _latest_prices(prices: Any) -> Mapping[str, float]:
    frame = prices if isinstance(prices, pd.DataFrame) else pd.DataFrame(prices or ())
    if frame.empty or "close" not in frame.columns:
        return {}
    if "symbol" not in frame.columns:
        return {"UNKNOWN": float(frame["close"].iloc[-1])}
    column = _date_column(frame)
    ordered = frame.sort_values(column) if column else frame
    return {str(symbol): float(group["close"].iloc[-1]) for symbol, group in ordered.groupby("symbol")}


def _metrics_mapping(metrics: Any) -> Mapping[str, Any]:
    return asdict(metrics) if is_dataclass(metrics) else dict(metrics)


def _parameter_update(metrics: Mapping[str, Any], parameters: Mapping[str, Any], run_label: str) -> Mapping[str, Any]:
    top_n = int(parameters.get("top_n", 3))
    net_pnl = float(metrics.get("net_pnl", 0.0))
    rejected = int(metrics.get("rejected_count", 0))
    if net_pnl < 0 or rejected:
        return {
            "run_label": run_label,
            "accepted": True,
            "reason": "paper_window_failure_or_rejection",
            "recommended_parameters": {"top_n": min(top_n + 1, 10)},
        }
    return {
        "run_label": run_label,
        "accepted": False,
        "reason": "no_failure_threshold_breached",
        "recommended_parameters": {"top_n": top_n},
    }


def _aggregate_metrics(results: list[WalkForwardWindowResult]) -> Mapping[str, Any]:
    metrics = [result.performance_metrics for result in results]
    count = len(metrics)
    total_net_pnl = round(sum(float(item.get("net_pnl", 0.0)) for item in metrics), 6)
    return {
        "window_count": count,
        "total_net_pnl": total_net_pnl,
        "average_net_pnl": round(total_net_pnl / count, 6) if count else 0.0,
        "total_trades": sum(int(item.get("trade_count", 0)) for item in metrics),
        "total_rejections": sum(int(item.get("rejected_count", 0)) for item in metrics),
        "average_fill_rate": round(sum(float(item.get("fill_rate", 0.0)) for item in metrics) / count, 6) if count else 0.0,
        "ending_equity": metrics[-1].get("ending_equity") if metrics else None,
    }


def _improvement_summary(results: list[WalkForwardWindowResult]) -> Mapping[str, Any]:
    if len(results) < 2:
        return {"window_count": len(results), "net_pnl_delta": 0.0, "direction": "insufficient_windows"}
    first = float(results[0].performance_metrics.get("net_pnl", 0.0))
    last = float(results[-1].performance_metrics.get("net_pnl", 0.0))
    delta = round(last - first, 6)
    return {"window_count": len(results), "net_pnl_delta": delta, "direction": "improved" if delta > 0 else "not_improved"}


def _adapter_summary(payload: Any) -> Mapping[str, Any] | None:
    if payload is None:
        return None
    if is_dataclass(payload):
        payload = asdict(payload)
    if isinstance(payload, Mapping):
        return {str(key): payload[key] for key in sorted(payload)[:8]}
    if isinstance(payload, pd.DataFrame):
        return {"rows": len(payload), "columns": tuple(str(column) for column in payload.columns)}
    return {"type": type(payload).__name__, "repr": repr(payload)[:200]}


def _row_count(payload: Any) -> int:
    if payload is None:
        return 0
    if isinstance(payload, pd.DataFrame):
        return len(payload)
    if isinstance(payload, (list, tuple)):
        return len(payload)
    if isinstance(payload, Mapping):
        return 1 if _row_has_date(payload) else sum(_row_count(value) for value in payload.values())
    return 0


def _has_rows(payload: Any) -> bool:
    return _row_count(payload) > 0


def _symbols(payload: Any) -> set[str]:
    if payload is None:
        return set()
    if isinstance(payload, pd.DataFrame) and "symbol" in payload.columns:
        return {str(value) for value in payload["symbol"].dropna().unique()}
    if isinstance(payload, Mapping) and "symbol" in payload:
        return {str(payload["symbol"])}
    if isinstance(payload, (list, tuple)):
        return {symbol for item in payload for symbol in _symbols(item)}
    return set()


def _row_has_date(row: Mapping[str, Any]) -> bool:
    return any(key in row for key in ("date", "datetime", "timestamp", "trade_date", "event_time", "as_of"))


def _row_in_range(row: Any, start: pd.Timestamp, end: pd.Timestamp) -> bool:
    if not isinstance(row, Mapping):
        return True
    for key in ("date", "datetime", "timestamp", "trade_date", "event_time", "as_of"):
        if key in row:
            ts = _as_timestamp(row[key])
            return start <= ts <= end
    return True


def _date_column(frame: pd.DataFrame) -> str | None:
    for column in ("date", "datetime", "timestamp", "trade_date", "event_time"):
        if column in frame.columns:
            return column
    return None


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
