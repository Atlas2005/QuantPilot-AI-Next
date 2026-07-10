"""Canonical cost-after-fee OOS baseline — runner, benchmark, aggregation (PR #115)."""

from __future__ import annotations

import hashlib
import math
import os
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from quantpilot_core.daily_paper_loop.state import load_daily_state, payload_digest
from quantpilot_core.daily_paper_loop.report import write_report_atomic
from quantpilot_core.real_candidate_pipeline import (
    RealCandidatePipelineConfig,
    run_real_candidate_daily_paper,
)
from quantpilot_core.walk_forward.contracts import (
    OOSDailySessionResult,
    WalkForwardInput,
    WalkForwardWindow,
    WalkForwardWindowContext,
    WalkForwardWindowExecutionResult,
    WindowRunner,
)
from quantpilot_core.walk_forward.engine import WalkForwardEngine
from quantpilot_core.walk_forward.leakage import LeakageGuard
from quantpilot_core.walk_forward.pit_helpers import rows_through_execution
from quantpilot_core.walk_forward.snapshot import (
    DEFAULT_BENCHMARK_SYMBOL,
    DEFAULT_SNAPSHOT_PATH,
    SnapshotManifest,
    build_fixture_manifest,
    load_and_validate_snapshot,
)


REAL_TUSHARE_SNAPSHOT_SHA256 = "4f76dc8a83901d295c8f8688341649b5994d58ded110844e72a83be5398492c0"
REAL_TUSHARE_MANIFEST_DIGEST = "34e8a34a053bfc958c3bc898565b972417e1d5df436bd2349297b17135c95ab4"


@dataclass(frozen=True)
class CanonicalBaselineConfig:
    snapshot_path: str = DEFAULT_SNAPSHOT_PATH
    data_mode: str = "fixed_snapshot"
    output_dir: str = ".cache/canonical_baseline"
    strategy_id: str = "canonical-cost-after-fee-baseline-v1"
    initial_capital: float = 100_000.0
    train_window_days: int = 60
    test_window_days: int = 20
    max_windows: int = 12
    benchmark_index_symbol: str = DEFAULT_BENCHMARK_SYMBOL
    fixture_symbols: tuple[str, ...] = ()
    fixture_num_sessions: int = 200


@dataclass(frozen=True)
class CanonicalBaselineResult:
    status: str
    snapshot_digest: str | None
    windows: tuple[WalkForwardWindow, ...]
    walk_forward_result: Any
    daily_sessions: tuple[tuple[OOSDailySessionResult, ...], ...]
    benchmark_total_return: float | None
    benchmark_final_equity: float | None
    excess_return: float | None
    strategy_total_return: float | None
    strategy_net_pnl: float | None
    max_drawdown: float | None
    turnover: float | None
    fill_rate: float | None
    fee_breakdown: Mapping[str, float]
    snapshot_provenance: Mapping[str, Any]
    report_path: str | None
    limitations: tuple[str, ...]
    parameter_update_mode: str
    no_profitability_claim: bool


# ---------------------------------------------------------------------------
# Windows from calendar
# ---------------------------------------------------------------------------


def _build_walk_forward_windows_from_calendar(
    calendar_sessions: tuple[str, ...],
    train_window_days: int, test_window_days: int, max_windows: int,
    decision_date_range_start: str | None = None, decision_date_range_end: str | None = None,
) -> tuple[WalkForwardWindow, ...]:
    train_size, test_size, max_win = int(train_window_days), int(test_window_days), int(max_windows)
    dates = list(calendar_sessions)
    windows: list[WalkForwardWindow] = []
    decision_start = decision_date_range_start or dates[train_size]
    decision_end = decision_date_range_end or dates[-1]
    eligible_indices = [i for i, d in enumerate(dates) if decision_start <= d <= decision_end]
    if not eligible_indices:
        return ()
    next_decision = 0
    while len(windows) < max_win and next_decision < len(eligible_indices):
        first_test_idx = eligible_indices[next_decision]
        if first_test_idx < train_size:
            raise ValueError("insufficient calendar lookback before first decision session")
        test_indices = eligible_indices[next_decision : next_decision + test_size]
        if len(test_indices) < test_size:
            break
        td = [dates[i] for i in test_indices]
        for d in td:
            try:
                dates[dates.index(d) + 1]
            except (ValueError, IndexError):
                raise ValueError(f"test date {d} has no D+1 execution session")
        windows.append(WalkForwardWindow(
            train_start=dates[first_test_idx - train_size], train_end=dates[first_test_idx - 1],
            test_start=td[0], test_end=td[-1],
            run_label=f"canonical-baseline-{len(windows) + 1}"))
        next_decision += test_size
    return tuple(windows)


# ---------------------------------------------------------------------------
# ProductionWindowRunner
# ---------------------------------------------------------------------------


class ProductionWindowRunner:
    def __init__(self, state_path: Path, symbols: tuple[str, ...],
                 all_bars: tuple[Mapping[str, Any], ...],
                 calendar_sessions: tuple[str, ...], strategy_id: str):
        self._state_path = state_path
        self._symbols = symbols
        self._all_bars = all_bars
        self._calendar_sessions = calendar_sessions
        self._strategy_id = strategy_id

    def run_window(self, context: WalkForwardWindowContext) -> WalkForwardWindowExecutionResult:
        # Official decision days from calendar + window boundaries
        test_dates = _official_test_dates(
            self._calendar_sessions, context.window.test_start, context.window.test_end)
        if not test_dates:
            raise ValueError("test window contains no trading dates")

        daily_sessions: list[OOSDailySessionResult] = []
        totals = _zero_fee_totals()

        for session_index, decision_date_str in enumerate(test_dates, start=1):
            if os.environ.get("QUANTPILOT_CANONICAL_PROGRESS") == "1" and (session_index == 1 or session_index % 5 == 0):
                print(f"canonical baseline {context.window.run_label}: {session_index}/{len(test_dates)} {decision_date_str}", flush=True)
            decision_date = date.fromisoformat(decision_date_str)
            try:
                exec_idx = self._calendar_sessions.index(decision_date_str) + 1
                execution_date_str = self._calendar_sessions[exec_idx]
                execution_date = date.fromisoformat(execution_date_str)
            except (ValueError, IndexError):
                raise ValueError(f"cannot resolve execution session for {decision_date_str}")

            bars_through_exec = rows_through_execution(self._all_bars, execution_date)
            pipeline_config = RealCandidatePipelineConfig(
                decision_session=decision_date_str, symbols=self._symbols,
                initial_capital=context.initial_capital, state_path=self._state_path,
                report_path=None, strategy_id=self._strategy_id,
                live_market_data=False, input_bars=bars_through_exec,
                input_calendar_sessions=self._calendar_sessions,
                input_calendar_provider="tushare",
            )
            pipeline_result = run_real_candidate_daily_paper(pipeline_config)
            daily = _extract_daily_session(pipeline_result, decision_date, execution_date)
            daily_sessions.append(daily)
            _accumulate_fees(totals, daily)

        if not daily_sessions:
            raise ValueError("no daily sessions")

        # Window equity from first/last session (production ledger)
        w_start_eq = daily_sessions[0].session_start_equity
        w_end_eq = daily_sessions[-1].session_end_equity
        w_net_pnl = round(w_end_eq - w_start_eq, 6)
        w_gross_pnl = round(w_net_pnl + totals["total_cost"], 6)

        # Aggregate execution metrics
        agg = _aggregate_execution_metrics(daily_sessions)

        return WalkForwardWindowExecutionResult(
            window_label=context.window.run_label,
            daily_sessions=tuple(daily_sessions),
            net_pnl=w_net_pnl, gross_pnl=w_gross_pnl,
            ending_equity=w_end_eq,
            fill_rate=agg["fill_rate"], trade_count=agg["trade_count"],
            rejected_count=agg["rejected_count"], turnover=agg["turnover"],
            commission=totals["commission"], transaction_tax=totals["transaction_tax"],
            transfer_or_exchange_fee=totals["transfer_or_exchange_fee"],
            slippage_cost=totals["slippage_cost"], total_cost=totals["total_cost"],
            intent_count=agg["intent_count"], filled_count=agg["filled_count"],
            partial_fill_count=agg["partial_fill_count"],
            requested_quantity=agg["requested_quantity"],
            filled_quantity=agg["filled_quantity"],
            reconciliation_all_passed=agg["reconciliation_all_passed"],
        )


class ProductionWindowRunnerFactory:
    def __init__(self, state_path: Path, symbols: tuple[str, ...],
                 all_bars: tuple[Mapping[str, Any], ...],
                 calendar_sessions: tuple[str, ...], strategy_id: str):
        self._state_path = state_path
        self._symbols = symbols
        self._all_bars = all_bars
        self._calendar_sessions = calendar_sessions
        self._strategy_id = strategy_id

    def create_runner(self, *, initial_capital: float) -> WindowRunner:
        return ProductionWindowRunner(
            state_path=self._state_path, symbols=self._symbols,
            all_bars=self._all_bars, calendar_sessions=self._calendar_sessions,
            strategy_id=self._strategy_id)


# ---------------------------------------------------------------------------
# Daily session extraction (from production structured reports)
# ---------------------------------------------------------------------------


def _extract_daily_session(pipeline_result: Any, decision_date: date,
                            execution_date: date) -> OOSDailySessionResult:
    combined = dict(pipeline_result.combined_report or {})
    daily = dict(combined.get("daily_paper_loop", {}) or {})
    lb = dict(daily.get("ledger_before", {}) or {})
    la = dict(daily.get("ledger_after", {}) or {})
    fees = dict(daily.get("fee_breakdown", {}) or {})

    # Valuation session from production report
    vs_str = str(daily.get("execution_session") or "")
    try:
        valuation_date = date.fromisoformat(vs_str) if vs_str else execution_date
    except ValueError:
        valuation_date = execution_date

    # Equity from ledger
    s_start_eq = float(lb.get("total_equity", 0.0))
    s_end_eq = float(la.get("total_equity", 0.0))
    s_net = round(s_end_eq - s_start_eq, 6)

    # Fees
    comm = float(fees.get("commission", 0.0))
    tax = float(fees.get("transaction_tax", 0.0))
    tfe = float(fees.get("transfer_or_exchange_fee", 0.0))
    slip = float(fees.get("slippage_cost", 0.0))
    tcost = float(fees.get("total_cost", 0.0))
    gross = round(s_net + tcost, 6)

    # Execution metrics from production outcomes
    fills = tuple(daily.get("fills", ()) or ())
    partials = tuple(daily.get("partial_fills", ()) or ())
    intents_t = tuple(dict(daily.get("order_intents", {}) or {}).get("intents", ()) or ())
    sizing_t = tuple(daily.get("sizing_decisions", ()) or ())
    rej_t = tuple(daily.get("rejections", ()) or ())

    intent_count = len(intents_t)
    filled_count = len(fills)
    partial_fill_count = len(partials)
    rejected_count = len(rej_t)

    # Quantities from sizing decisions (final_order_quantity) and fills
    req_qty = sum(int(dict(s).get("final_order_quantity", 0) or 0) for s in sizing_t)
    fill_qty = sum(int(dict(f).get("filled_quantity", 0) or 0) for f in fills + partials)
    fr = round(fill_qty / req_qty, 6) if req_qty > 0 else (1.0 if intent_count == 0 else 0.0)

    # Turnover
    to = sum(float(r.get("gross_value", 0.0)) for r in fills + partials)

    # Reconciliation
    rec = dict(daily.get("reconciliation_audit", {}) or {})
    rec_ok = str(rec.get("status", "")) == "passed"
    settlement_lot_count = len(tuple(la.get("settlement_lots", ()) or ()))

    # Provenance
    pipe_dig = str(combined.get("candidate_pipeline", {}).get("pipeline_request_digest", ""))
    sid = str(daily.get("session_id", ""))

    return OOSDailySessionResult(
        decision_session=decision_date, execution_session=execution_date,
        valuation_session=valuation_date,
        session_start_equity=s_start_eq, session_end_equity=s_end_eq,
        session_net_pnl=s_net, gross_pnl=gross,
        intent_count=intent_count, filled_count=filled_count,
        partial_fill_count=partial_fill_count, rejected_count=rejected_count,
        requested_quantity=req_qty, filled_quantity=fill_qty, fill_rate=fr,
        turnover=to, commission=comm, transaction_tax=tax,
        transfer_or_exchange_fee=tfe, slippage_cost=slip, total_cost=tcost,
        reconciliation_passed=rec_ok, settlement_lot_count=settlement_lot_count,
        pipeline_request_digest=pipe_dig, daily_loop_session_id=sid,
        report_path=None)


def _aggregate_execution_metrics(sessions: list[OOSDailySessionResult]) -> dict[str, Any]:
    ic = sum(s.intent_count for s in sessions)
    fc = sum(s.filled_count for s in sessions)
    pc = sum(s.partial_fill_count for s in sessions)
    rc = sum(s.rejected_count for s in sessions)
    rq = sum(s.requested_quantity for s in sessions)
    fq = sum(s.filled_quantity for s in sessions)
    fr = round(fq / rq, 6) if rq > 0 else (1.0 if ic == 0 else 0.0)
    return {"intent_count": ic, "filled_count": fc, "partial_fill_count": pc,
            "rejected_count": rc, "requested_quantity": rq, "filled_quantity": fq,
            "fill_rate": fr, "trade_count": fc + pc,
            "turnover": round(sum(s.turnover for s in sessions), 6),
            "reconciliation_all_passed": all(s.reconciliation_passed for s in sessions)}


# ---------------------------------------------------------------------------
# Benchmark
# ---------------------------------------------------------------------------


def _compute_benchmark_return(benchmark_bars: tuple[Mapping[str, Any], ...],
                               daily_sessions: tuple[OOSDailySessionResult, ...],
                               initial_capital: float) -> tuple[float | None, float | None, str | None]:
    if not benchmark_bars or not daily_sessions:
        return None, None, "missing_benchmark_bars_or_sessions"
    first = daily_sessions[0].decision_session
    last = daily_sessions[-1].valuation_session
    cbd: dict[date, float] = {}
    for row in benchmark_bars:
        try:
            cbd[date.fromisoformat(str(row["date"]))] = float(row["close"])
        except (KeyError, ValueError):
            continue
    sc = cbd.get(first)
    ec = cbd.get(last)
    if sc is None or ec is None or sc <= 0:
        return None, None, "benchmark_bars_do_not_cover_oos_boundary"
    br = round((ec / sc) - 1.0, 6)
    return br, round(float(initial_capital) * (1.0 + br), 6), None


def _nearest(cbd: dict[date, float], target: date, direction: str) -> float | None:
    dates = sorted(cbd)
    if not dates: return None
    if direction == "forward":
        for d in dates:
            if d >= target: return cbd[d]
        return None
    for d in reversed(dates):
        if d <= target: return cbd[d]
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _zero_fee_totals() -> dict[str, float]:
    return {"commission": 0.0, "transaction_tax": 0.0,
            "transfer_or_exchange_fee": 0.0, "slippage_cost": 0.0, "total_cost": 0.0}


def _accumulate_fees(t: dict[str, float], s: OOSDailySessionResult) -> None:
    for k in t: t[k] = round(t[k] + getattr(s, k, 0.0), 6)


def _official_test_dates(calendar: tuple[str, ...], test_start: str, test_end: str) -> tuple[str, ...]:
    return tuple(d for d in calendar if test_start <= d <= test_end)


def _max_drawdown_from_series(equities: list[float]) -> float | None:
    if not equities: return None
    peak = equities[0]; md = 0.0
    for e in equities:
        peak = max(peak, e)
        if peak > 0: md = min(md, (e - peak) / peak)
    return round(md, 6)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _code_revision() -> str | None:
    """Return the current revision when this source is running from a Git checkout."""
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[3],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    revision = completed.stdout.strip()
    return revision if completed.returncode == 0 and len(revision) == 40 else None


def _validate_real_tushare_snapshot(manifest: SnapshotManifest, path: Path) -> None:
    """Pin the PR #116 immutable snapshot before entering the production loop."""
    checks = {
        "SHA256": _file_sha256(path) == REAL_TUSHARE_SNAPSHOT_SHA256,
        "manifest digest": manifest.digest == REAL_TUSHARE_MANIFEST_DIGEST,
        "provider": manifest.provider == "tushare",
        "canonical": manifest.canonical is True,
        "symbol count": len(manifest.symbols) == 12,
        "calendar sessions": len(manifest.calendar_sessions) == 303,
        "equity bars": len(manifest.bars) == 3636,
        "benchmark": manifest.benchmark_index_symbol == "000300.SH" and len(manifest.benchmark_index_bars) == 303,
        "decision range": (manifest.decision_date_range_start, manifest.decision_date_range_end) == ("2024-01-02", "2024-12-31"),
        "data range": (manifest.data_date_range_start, manifest.data_date_range_end) == ("2023-10-09", "2025-01-02"),
    }
    failures = tuple(name for name, passed in checks.items() if not passed)
    if failures:
        raise ValueError("real Tushare snapshot integrity mismatch: " + ", ".join(failures))


def _annualized_return(total_return: float | None, session_count: int) -> float | None:
    if total_return is None or session_count <= 0 or 1.0 + total_return <= 0:
        return None
    return round((1.0 + total_return) ** (252.0 / session_count) - 1.0, 6)


def _annualized_volatility(session_returns: tuple[float, ...]) -> float | None:
    if len(session_returns) < 2:
        return None
    mean = sum(session_returns) / len(session_returns)
    variance = sum((value - mean) ** 2 for value in session_returns) / (len(session_returns) - 1)
    return round(math.sqrt(variance) * math.sqrt(252.0), 6)


def _benchmark_boundary_values(
    benchmark_bars: tuple[Mapping[str, Any], ...], daily_sessions: tuple[OOSDailySessionResult, ...]
) -> tuple[float | None, float | None]:
    if not daily_sessions:
        return None, None
    values = {str(row.get("date")): float(row["close"]) for row in benchmark_bars if "date" in row and "close" in row}
    return values.get(daily_sessions[0].decision_session.isoformat()), values.get(daily_sessions[-1].valuation_session.isoformat())


def _execution_summary(sessions: tuple[OOSDailySessionResult, ...]) -> Mapping[str, Any]:
    intents = sum(s.intent_count for s in sessions)
    fills = sum(s.filled_count for s in sessions)
    partials = sum(s.partial_fill_count for s in sessions)
    rejected = sum(s.rejected_count for s in sessions)
    requested = sum(s.requested_quantity for s in sessions)
    filled_quantity = sum(s.filled_quantity for s in sessions)
    turnover = round(sum(s.turnover for s in sessions), 6)
    return {
        "intent_count": intents, "submitted_order_count": intents,
        "filled_count": fills, "partial_fill_count": partials, "rejected_count": rejected,
        "unfilled_count": max(0, intents - fills - partials - rejected),
        "fill_rate": round(filled_quantity / requested, 6) if requested else None,
        "total_filled_quantity": filled_quantity, "trade_count": fills + partials,
        "total_turnover": turnover, "buy_turnover": None, "sell_turnover": None,
        "turnover_directional_breakdown_available": False,
        "slippage_estimate": round(sum(s.slippage_cost for s in sessions), 6),
        "fee_drag": round(sum(s.total_cost for s in sessions), 6),
        "holding_count": sessions[-1].settlement_lot_count if sessions else 0,
        "settlement_lot_evidence": sum(s.settlement_lot_count for s in sessions),
        "reconciliation_status": "passed" if all(s.reconciliation_passed for s in sessions) else "failed",
        "no_trade_reasons": (), "rejection_reasons": (), "execution_blockers": (),
        "warnings": ("directional turnover and reason codes are not emitted by the existing production report",),
    }


def _write_markdown_summary(report: Mapping[str, Any], path: Path) -> None:
    """Write a small human-readable companion without duplicating market rows."""
    data = report["data_provenance"]
    strategy = report["strategy"]
    benchmark = report["benchmark"]
    execution = report["execution"]
    lines = (
        "# Canonical Cost-After-Fee OOS Baseline\n\n"
        f"- Snapshot SHA-256: `{report['snapshot_sha256']}`\n"
        f"- Manifest digest: `{report['snapshot_digest']}`\n"
        f"- Provider/canonical: `{data['provider']}` / `{data['canonical']}`\n"
        f"- Decision range: `{data['decision_date_range']['start']}` to `{data['decision_date_range']['end']}`\n\n"
        "## Results\n\n"
        f"- Initial/final equity: {strategy['initial_equity']:.2f} / {strategy['final_equity']:.2f}\n"
        f"- Net return after fees: {strategy['net_return_after_fees']:.4%}\n"
        f"- CSI 300 return: {benchmark['total_return']:.4%}; excess: {report['excess_return']:.4%}\n"
        f"- Total explicit fees: {report['fee_breakdown']['total_cost']:.2f}\n"
        f"- Filled orders: {execution['filled_count']}; fill rate: {execution['fill_rate']:.2%}\n\n"
        "This is first historical paper-trading evidence only and makes no profitability claim.\n"
    )
    path.write_text(lines, encoding="utf-8")


def _dict_to_daily_session(raw: dict[str, Any]) -> OOSDailySessionResult:
    return OOSDailySessionResult(
        decision_session=date.fromisoformat(str(raw["decision_session"])),
        execution_session=date.fromisoformat(str(raw["execution_session"])),
        valuation_session=date.fromisoformat(str(raw["valuation_session"])),
        session_start_equity=float(raw.get("session_start_equity", 0)),
        session_end_equity=float(raw.get("session_end_equity", 0)),
        session_net_pnl=float(raw.get("session_net_pnl", raw.get("net_pnl", 0))),
        gross_pnl=float(raw["gross_pnl"]),
        intent_count=int(raw.get("intent_count", 0)),
        filled_count=int(raw.get("filled_count", 0)),
        partial_fill_count=int(raw.get("partial_fill_count", 0)),
        rejected_count=int(raw.get("rejected_count", 0)),
        requested_quantity=int(raw.get("requested_quantity", 0)),
        filled_quantity=int(raw.get("filled_quantity", 0)),
        fill_rate=float(raw["fill_rate"]),
        turnover=float(raw["turnover"]),
        commission=float(raw["commission"]), transaction_tax=float(raw["transaction_tax"]),
        transfer_or_exchange_fee=float(raw["transfer_or_exchange_fee"]),
        slippage_cost=float(raw["slippage_cost"]), total_cost=float(raw["total_cost"]),
        reconciliation_passed=bool(raw.get("reconciliation_passed", True)),
        settlement_lot_count=int(raw.get("settlement_lot_count", 0)),
        pipeline_request_digest=str(raw.get("pipeline_request_digest", "")),
        daily_loop_session_id=str(raw.get("daily_loop_session_id", "")),
        report_path=None)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run_canonical_cost_after_fee_baseline(
    config: CanonicalBaselineConfig | None = None,
) -> CanonicalBaselineResult:
    cfg = config or CanonicalBaselineConfig()

    if cfg.data_mode == "fixture":
        manifest = build_fixture_manifest(
            symbols=cfg.fixture_symbols or ("600000.SH",),
            num_sessions=cfg.fixture_num_sessions,
            benchmark_symbol=cfg.benchmark_index_symbol)
    elif cfg.data_mode == "fixed_snapshot":
        manifest = load_and_validate_snapshot(cfg.snapshot_path)
        if not manifest.canonical:
            raise ValueError(
                f"canonical baseline requires a canonical snapshot. "
                f"Got canonical={manifest.canonical}, provider={manifest.provider}.")
        _validate_real_tushare_snapshot(manifest, Path(cfg.snapshot_path))
    else:
        raise ValueError(f"data_mode '{cfg.data_mode}' not supported.")

    windows = _build_walk_forward_windows_from_calendar(
        manifest.calendar_sessions, cfg.train_window_days,
        cfg.test_window_days, cfg.max_windows,
        manifest.decision_date_range_start, manifest.decision_date_range_end)
    if not windows:
        raise ValueError("no walk-forward windows could be built")

    import pandas as pd
    price_frame = pd.DataFrame(manifest.bars)
    walk_input = WalkForwardInput(
        historical_price_frame=price_frame, initial_cash=cfg.initial_capital,
        current_parameters={"strategy_id": cfg.strategy_id, "top_n": 3,
                            "lot_size": 100, "capital": cfg.initial_capital},
        windows=windows, advisory_mode="disabled",
        metadata={"snapshot_digest": manifest.digest,
                  "snapshot_provider": manifest.provider,
                  "benchmark_index_symbol": manifest.benchmark_index_symbol,
                  "parameter_update_mode": "frozen_baseline"})

    # Temp dir owned here, cleaned up after run
    run_dir = Path(tempfile.mkdtemp(prefix="canonical_baseline_"))
    state_path = run_dir / "state.json"
    try:
        load_daily_state(state_path, initial_capital=float(cfg.initial_capital))

        runner_factory = ProductionWindowRunnerFactory(
            state_path=state_path, symbols=manifest.symbols,
            all_bars=tuple(manifest.bars),
            calendar_sessions=manifest.calendar_sessions,
            strategy_id=cfg.strategy_id)
        engine = WalkForwardEngine(
            leakage_guard=LeakageGuard(), window_runner_factory=runner_factory)
        wf_result = engine.run(walk_input)

        # Collect daily sessions
        all_daily: list[tuple[OOSDailySessionResult, ...]] = []
        for wr in wf_result.window_results:
            paper = wr.paper_trading_result
            if isinstance(paper, dict) and "daily_sessions" in paper:
                raw = paper["daily_sessions"]
                if isinstance(raw, tuple):
                    all_daily.append(tuple(
                        _dict_to_daily_session(d) if isinstance(d, dict) else d
                        for d in raw))

        flat = tuple(s for sessions in all_daily for s in sessions)

        # Benchmark
        br, be, bg = _compute_benchmark_return(
            manifest.benchmark_index_bars, flat, cfg.initial_capital)
        if cfg.data_mode == "fixed_snapshot" and br is None:
            raise ValueError(f"canonical baseline: benchmark coverage missing. Gap: {bg}")

        # Strategy PnL: telescoping sum from first/last session
        if flat:
            strategy_net_pnl = round(flat[-1].session_end_equity - cfg.initial_capital, 6)
            strategy_return = round(strategy_net_pnl / cfg.initial_capital, 6)
        else:
            strategy_net_pnl = None
            strategy_return = None

        excess = None
        if strategy_return is not None and br is not None:
            excess = round(strategy_return - br, 6)

        agg_fees = _zero_fee_totals()
        for sessions in all_daily:
            for s in sessions:
                _accumulate_fees(agg_fees, s)

        equities = [cfg.initial_capital]
        for sessions in all_daily:
            for s in sessions:
                equities.append(s.session_end_equity)
        max_dd = _max_drawdown_from_series(equities)

        total_to = round(sum(sum(s.turnover for s in ss) for ss in all_daily), 6)
        all_rq = sum(s.requested_quantity for s in flat)
        all_fq = sum(s.filled_quantity for s in flat)
        overall_fr = round(all_fq / all_rq, 6) if all_rq > 0 else None

        output_dir = Path(cfg.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        final_equity = flat[-1].session_end_equity if flat else None
        benchmark_start, benchmark_end = _benchmark_boundary_values(manifest.benchmark_index_bars, flat)
        session_returns = tuple(
            s.session_net_pnl / s.session_start_equity
            for s in flat if s.session_start_equity > 0
        )
        annualized_return = _annualized_return(strategy_return, len(flat))
        volatility = _annualized_volatility(session_returns)
        window_metrics = tuple({
            "label": wr.window.run_label,
            "net_pnl": wr.performance_metrics.get("net_pnl"),
            "gross_pnl": wr.performance_metrics.get("gross_pnl"),
            "ending_equity": wr.performance_metrics.get("ending_equity"),
            "turnover": wr.performance_metrics.get("turnover"),
            "fill_rate": wr.performance_metrics.get("fill_rate"),
            "trade_count": wr.performance_metrics.get("trade_count"),
        } for wr in wf_result.window_results)
        execution = _execution_summary(flat)
        report_payload = {
            "schema_version": 2, "baseline_version": "canonical_baseline_v1",
            "report_schema": "canonical_cost_after_fee_oos_v2",
            "run_timestamp": datetime.now(timezone.utc).isoformat(),
            "code_revision": _code_revision(),
            "parameter_update_mode": "frozen_baseline", "no_profitability_claim": True,
            "snapshot_digest": manifest.digest,
            "snapshot_sha256": _file_sha256(Path(cfg.snapshot_path)) if cfg.data_mode == "fixed_snapshot" else None,
            "data_provenance": {"mode": cfg.data_mode, "provider": manifest.provider,
                "canonical": manifest.canonical, "snapshot_path": cfg.snapshot_path,
                "symbols": manifest.symbols,
                "decision_date_range": manifest.decision_date_range,
                "data_date_range": manifest.data_date_range,
                "benchmark_index_symbol": manifest.benchmark_index_symbol},
            "snapshot_provenance": dict(manifest.provenance),
            "windows": tuple(w.run_label for w in windows), "window_count": len(windows),
            "frozen_runner_config": {"initial_capital": cfg.initial_capital,
                "train_window_days": cfg.train_window_days, "test_window_days": cfg.test_window_days,
                "max_windows": cfg.max_windows, "strategy_id": cfg.strategy_id,
                "benchmark_index": cfg.benchmark_index_symbol},
            "strategy": {"initial_equity": cfg.initial_capital, "final_equity": final_equity,
                "net_pnl": strategy_net_pnl,
                "gross_pnl": round(float(strategy_net_pnl or 0) + agg_fees["total_cost"], 6)
                if strategy_net_pnl is not None else None,
                "total_return": strategy_return, "net_return_after_fees": strategy_return,
                "gross_return": round((float(strategy_net_pnl or 0) + agg_fees["total_cost"]) / cfg.initial_capital, 6)
                if strategy_net_pnl is not None else None,
                "annualized_return": annualized_return, "volatility": volatility,
                "max_drawdown": max_dd, "turnover": total_to, "fill_rate": overall_fr,
                "positive_session_count": sum(s.session_net_pnl > 0 for s in flat),
                "negative_session_count": sum(s.session_net_pnl < 0 for s in flat),
                "flat_session_count": sum(s.session_net_pnl == 0 for s in flat)},
            "benchmark": {"symbol": manifest.benchmark_index_symbol,
                "start_value": benchmark_start, "end_value": benchmark_end,
                "total_return": br, "final_equity": be, "data_gap_reason": bg},
            "excess_return": excess, "fee_breakdown": dict(agg_fees),
            "execution": execution,
            "per_window_metrics": window_metrics,
            "limitations": ("paper_trading_only_no_broker_execution",
                "no_profitability_claim", "parameter_update_mode_frozen_baseline",
                f"data_mode:{cfg.data_mode}"),
            "production_provenance": tuple(_daily_provenance(s) for s in flat),
        }
        rp = write_report_atomic(report_payload, output_dir / "baseline_report.json")
        _write_markdown_summary(report_payload, output_dir / "baseline_summary.md")

        return CanonicalBaselineResult(
            status="completed", snapshot_digest=manifest.digest,
            windows=windows, walk_forward_result=wf_result,
            daily_sessions=tuple(all_daily),
            benchmark_total_return=br, benchmark_final_equity=be,
            excess_return=excess, strategy_total_return=strategy_return,
            strategy_net_pnl=strategy_net_pnl, max_drawdown=max_dd,
            turnover=total_to, fill_rate=overall_fr,
            fee_breakdown=agg_fees, snapshot_provenance=manifest.provenance,
            report_path=rp,
            limitations=("paper_trading_only_no_broker_execution",
                "no_profitability_claim", "parameter_update_mode_frozen_baseline",
                f"data_mode:{cfg.data_mode}"),
            parameter_update_mode="frozen_baseline", no_profitability_claim=True)
    finally:
        # Clean up temp directory
        import shutil
        if run_dir.exists():
            shutil.rmtree(run_dir, ignore_errors=True)


def _daily_provenance(s: OOSDailySessionResult) -> Mapping[str, Any]:
    return {
        "decision_session": s.decision_session.isoformat(),
        "execution_session": s.execution_session.isoformat(),
        "valuation_session": s.valuation_session.isoformat(),
        "intent_count": s.intent_count, "filled_count": s.filled_count,
        "partial_fill_count": s.partial_fill_count, "rejected_count": s.rejected_count,
        "requested_quantity": s.requested_quantity, "filled_quantity": s.filled_quantity,
        "fill_rate": s.fill_rate, "reconciliation_passed": s.reconciliation_passed,
        "settlement_lot_count": s.settlement_lot_count,
        "pipeline_request_digest": s.pipeline_request_digest,
        "daily_loop_session_id": s.daily_loop_session_id,
    }
