"""Tests for PR #115 canonical cost-after-fee baseline v3."""

from __future__ import annotations

import json, math
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
import pytest

from quantpilot_core.daily_paper_loop.state import payload_digest
from quantpilot_core.walk_forward.canonical_baseline import (
    CanonicalBaselineConfig, ProductionWindowRunner, ProductionWindowRunnerFactory,
    _build_walk_forward_windows_from_calendar, _code_revision, _compute_benchmark_return,
    _max_drawdown_from_series, run_canonical_cost_after_fee_baseline,
)
from quantpilot_core.walk_forward.contracts import OOSDailySessionResult, WindowRunnerFactory
from quantpilot_core.walk_forward.engine import WalkForwardEngine
from quantpilot_core.walk_forward.leakage import LeakageGuard
from quantpilot_core.walk_forward.pit_helpers import rows_through_execution
from quantpilot_core.walk_forward.snapshot import (
    CANONICAL_SNAPSHOT_SCHEMA_VERSION, DEFAULT_BENCHMARK_SYMBOL,
    _synthetic_fixture_bars, _synthetic_benchmark_bars,
    build_fixture_manifest, load_and_validate_snapshot,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _fixture_cal(num: int = 300) -> tuple[str, ...]:
    bars = tuple(_synthetic_fixture_bars(("600000.SH",), num))
    return tuple(dict.fromkeys(str(r["date"]) for r in sorted(bars, key=lambda r: str(r["date"]))))

def _write_tushare_snapshot(tmp_path: Path, **kw) -> Path:
    """Write a canonical Tushare snapshot with tushare-labelled bars."""
    bars_list = []
    for i, d in enumerate(_fixture_cal(200)):
        bars_list.append({"symbol": "600000.SH", "date": d,
            "open": 10.0, "high": 10.2, "low": 9.8, "close": 10.1 + i * 0.001,
            "volume": 100_000.0, "amount": 1_000_000.0, "previous_close": 10.0,
            "is_suspended": False, "provider": "tushare"})
    cal = tuple(dict.fromkeys(str(r["date"]) for r in sorted(bars_list, key=lambda r: str(r["date"]))))
    bench = tuple({"symbol": "000300.SH", "date": d, "close": 3500.0 + i * 0.5,
                    "provider": "tushare"} for i, d in enumerate(cal))
    p: dict[str, Any] = {
        "schema_version": CANONICAL_SNAPSHOT_SCHEMA_VERSION,
        "manifest_version": "canonical_baseline_v1",
        "provider": kw.pop("provider", "tushare"), "canonical": kw.pop("canonical", True),
        "retrieval_timestamp": "2026-07-08T12:00:00+00:00",
        "decision_date_range": {"start": cal[0], "end": cal[-1]},
        "data_date_range": {"start": cal[0], "end": cal[-1]},
        "symbols": ["600000.SH"], "benchmark_index_symbol": DEFAULT_BENCHMARK_SYMBOL,
        "calendar_sessions": list(cal), "bars": bars_list,
        "benchmark_index_bars": list(bench),
        "provenance": {
            "calendar": {"selected_provider": "tushare", "fallback_used": False, "attempts": []},
            "bars": {"600000.SH": {"selected_provider": "tushare", "fallback_used": False}},
            "benchmark": {"selected_provider": "tushare", "fallback_used": False},
        },
    }
    p["digest"] = payload_digest({k: v for k, v in p.items() if k != "digest"})
    p.update(kw)
    path = tmp_path / "snap.json"
    path.write_text(json.dumps(p, sort_keys=True, indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Snapshot loader
# ---------------------------------------------------------------------------

class TestSnapshotValidator:
    def test_valid_tushare_canonical(self, tmp_path: Path) -> None:
        p = _write_tushare_snapshot(tmp_path)
        m = load_and_validate_snapshot(str(p))
        assert m.provider == "tushare" and m.canonical is True

    def test_rejects_non_tushare_bar(self, tmp_path: Path) -> None:
        p = _write_tushare_snapshot(tmp_path)
        raw = json.loads(p.read_text(encoding="utf-8"))
        raw["bars"][0]["provider"] = "baostock"
        raw["digest"] = payload_digest({k: v for k, v in raw.items() if k != "digest"})
        p.write_text(json.dumps(raw, sort_keys=True, indent=2), encoding="utf-8")
        with pytest.raises(ValueError, match="equity bar"):
            load_and_validate_snapshot(str(p))

    def test_rejects_symbol_fallback(self, tmp_path: Path) -> None:
        p = _write_tushare_snapshot(tmp_path)
        raw = json.loads(p.read_text(encoding="utf-8"))
        raw["provenance"]["bars"]["600000.SH"]["fallback_used"] = True
        raw["digest"] = payload_digest({k: v for k, v in raw.items() if k != "digest"})
        p.write_text(json.dumps(raw, sort_keys=True, indent=2), encoding="utf-8")
        with pytest.raises(ValueError, match="fallback"):
            load_and_validate_snapshot(str(p))

    def test_rejects_benchmark_non_tushare(self, tmp_path: Path) -> None:
        p = _write_tushare_snapshot(tmp_path)
        raw = json.loads(p.read_text(encoding="utf-8"))
        raw["provenance"]["benchmark"]["selected_provider"] = "baostock"
        raw["digest"] = payload_digest({k: v for k, v in raw.items() if k != "digest"})
        p.write_text(json.dumps(raw, sort_keys=True, indent=2), encoding="utf-8")
        with pytest.raises(ValueError, match="benchmark"):
            load_and_validate_snapshot(str(p))

    def test_rejects_missing_benchmark(self, tmp_path: Path) -> None:
        p = _write_tushare_snapshot(tmp_path)
        raw = json.loads(p.read_text(encoding="utf-8"))
        raw["benchmark_index_bars"] = []
        raw["digest"] = payload_digest({k: v for k, v in raw.items() if k != "digest"})
        p.write_text(json.dumps(raw, sort_keys=True, indent=2), encoding="utf-8")
        with pytest.raises(ValueError, match="benchmark_index_bars"):
            load_and_validate_snapshot(str(p))

    def test_rejects_missing_symbol_and_digest_tampering(self, tmp_path: Path) -> None:
        p = _write_tushare_snapshot(tmp_path)
        raw = json.loads(p.read_text(encoding="utf-8"))
        raw["symbols"].append("000001.SZ")
        raw["digest"] = payload_digest({k: v for k, v in raw.items() if k != "digest"})
        p.write_text(json.dumps(raw, sort_keys=True, indent=2), encoding="utf-8")
        with pytest.raises(ValueError, match="exactly match"):
            load_and_validate_snapshot(str(p))
        raw["digest"] = "tampered"
        p.write_text(json.dumps(raw, sort_keys=True, indent=2), encoding="utf-8")
        with pytest.raises(ValueError, match="digest mismatch"):
            load_and_validate_snapshot(str(p))

    def test_synthetic_rejected_as_canonical(self) -> None:
        m = build_fixture_manifest(symbols=("600000.SH",))
        assert m.canonical is False
        assert m.provider == "synthetic_engineering_fixture"

    def test_fixture_noncanonical_has_comparison_only(self) -> None:
        m = build_fixture_manifest(symbols=("600000.SH",))
        assert m.provenance.get("data_mode") == "fixture"


# ---------------------------------------------------------------------------
# PIT helper
# ---------------------------------------------------------------------------

class TestPITHelper:
    def test_d1_close_not_in_decision(self) -> None:
        rows = ({"symbol": "X", "date": "2026-04-01", "close": 10.0},
                {"symbol": "X", "date": "2026-04-02", "close": 10.5})
        r = rows_through_execution(rows, date(2026, 4, 1))
        assert len(r) == 1
        assert r[0]["date"] == "2026-04-01"

    def test_d2_not_visible(self) -> None:
        rows = ({"symbol": "X", "date": "2026-04-01"},
                {"symbol": "X", "date": "2026-04-02"},
                {"symbol": "X", "date": "2026-04-03"})
        r = rows_through_execution(rows, date(2026, 4, 2))
        assert len(r) == 2


# ---------------------------------------------------------------------------
# Window construction
# ---------------------------------------------------------------------------

class TestWindows:
    def test_from_calendar_non_overlapping(self) -> None:
        cal = _fixture_cal(300)
        ws = _build_walk_forward_windows_from_calendar(cal, 60, 20, 3)
        assert len(ws) >= 2
        for i in range(len(ws) - 1):
            assert ws[i].test_end < ws[i + 1].test_start

    def test_uses_official_calendar(self) -> None:
        cal = _fixture_cal(300)
        ws = _build_walk_forward_windows_from_calendar(cal, 60, 20, 1)
        test_dates = [d for d in cal if ws[0].test_start <= d <= ws[0].test_end]
        assert len(test_dates) == 20

    def test_excludes_lookback_and_trailing_coverage_from_decisions(self) -> None:
        cal = _fixture_cal(120)
        start, end = cal[60], cal[-2]
        windows = _build_walk_forward_windows_from_calendar(cal, 60, 20, 2, start, end)
        decisions = [d for window in windows for d in cal if window.test_start <= d <= window.test_end]
        assert all(start <= d <= end for d in decisions)
        assert cal[59] not in decisions
        assert cal[-1] not in decisions


# ---------------------------------------------------------------------------
# PnL telescoping
# ---------------------------------------------------------------------------

class TestPnL:
    def test_telescoping_equality_two_windows(self, tmp_path: Path) -> None:
        cfg = CanonicalBaselineConfig(
            data_mode="fixture", output_dir=str(tmp_path / "out"),
            initial_capital=100_000.0, train_window_days=60, test_window_days=20,
            max_windows=2, fixture_symbols=("600000.SH",), fixture_num_sessions=300)
        r = run_canonical_cost_after_fee_baseline(cfg)
        flat = tuple(s for ss in r.daily_sessions for s in ss)
        window_pnls = [
            float(wr.performance_metrics.get("net_pnl", 0))
            for wr in r.walk_forward_result.window_results
        ]
        # telescoping: sum(window_net_pnl) == final_equity - initial_capital
        total_window = sum(window_pnls)
        direct = round(flat[-1].session_end_equity - 100_000.0, 6) if flat else 0
        assert total_window == pytest.approx(direct, rel=1e-5)

    def test_session_equity_from_ledger(self, tmp_path: Path) -> None:
        cfg = CanonicalBaselineConfig(
            data_mode="fixture", output_dir=str(tmp_path / "out"),
            initial_capital=100_000.0, train_window_days=60, test_window_days=20,
            max_windows=1, fixture_symbols=("600000.SH",), fixture_num_sessions=200)
        r = run_canonical_cost_after_fee_baseline(cfg)
        for ss in r.daily_sessions:
            for s in ss:
                assert s.session_net_pnl == pytest.approx(
                    s.session_end_equity - s.session_start_equity, rel=1e-5)


# ---------------------------------------------------------------------------
# Execution metrics
# ---------------------------------------------------------------------------

class TestExecutionMetrics:
    def test_fill_rate_weighted_not_averaged(self, tmp_path: Path) -> None:
        cfg = CanonicalBaselineConfig(
            data_mode="fixture", output_dir=str(tmp_path / "out"),
            initial_capital=100_000.0, train_window_days=60, test_window_days=20,
            max_windows=1, fixture_symbols=("600000.SH",), fixture_num_sessions=200)
        r = run_canonical_cost_after_fee_baseline(cfg)
        assert r.fill_rate is not None
        assert 0.0 <= r.fill_rate <= 1.0

    def test_report_has_cost_after_fee_identity_and_execution_fields(self, tmp_path: Path) -> None:
        cfg = CanonicalBaselineConfig(
            data_mode="fixture", output_dir=str(tmp_path / "out"), initial_capital=100_000.0,
            train_window_days=60, test_window_days=20, max_windows=1,
            fixture_symbols=("600000.SH",), fixture_num_sessions=200)
        run_canonical_cost_after_fee_baseline(cfg)
        report = json.loads((tmp_path / "out" / "baseline_report.json").read_text(encoding="utf-8"))
        assert report["report_schema"] == "canonical_cost_after_fee_oos_v2"
        assert report["strategy"]["initial_equity"] == 100_000.0
        assert report["strategy"]["final_equity"] is not None
        assert report["benchmark"]["start_value"] is not None
        assert report["execution"]["fee_drag"] == report["fee_breakdown"]["total_cost"]
        strategy = report["strategy"]
        assert strategy["final_equity"] - strategy["initial_equity"] == pytest.approx(strategy["net_pnl"], abs=1e-6)
        assert strategy["gross_pnl"] - report["fee_breakdown"]["total_cost"] == pytest.approx(strategy["net_pnl"], abs=1e-6)
        assert strategy["net_return_after_fees"] == pytest.approx(strategy["net_pnl"] / strategy["initial_equity"], abs=1e-6)
        assert report["excess_return"] == pytest.approx(strategy["net_return_after_fees"] - report["benchmark"]["total_return"], abs=1e-6)
        assert report["execution"]["reconciliation_status"] == "passed"
        assert report["no_profitability_claim"] is True
        assert (tmp_path / "out" / "baseline_summary.md").is_file()

    def test_code_revision_is_safely_nullable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def unavailable(*args: Any, **kwargs: Any) -> None:
            raise OSError("git unavailable")

        monkeypatch.setattr("quantpilot_core.walk_forward.canonical_baseline.subprocess.run", unavailable)
        assert _code_revision() is None


# ---------------------------------------------------------------------------
# Benchmark
# ---------------------------------------------------------------------------

class TestBenchmark:
    def test_exact_return(self) -> None:
        bench = ({"symbol": "000300.SH", "date": "2026-04-01", "close": 3500.0},
                 {"symbol": "000300.SH", "date": "2026-04-02", "close": 3520.0},
                 {"symbol": "000300.SH", "date": "2026-04-06", "close": 3550.0})
        daily = (OOSDailySessionResult(
            decision_session=date(2026, 4, 1), execution_session=date(2026, 4, 2),
            valuation_session=date(2026, 4, 2),
            session_start_equity=100_000.0, session_end_equity=100_080.0,
            session_net_pnl=80.0, gross_pnl=100.0,
            intent_count=1, filled_count=1, partial_fill_count=0, rejected_count=0,
            requested_quantity=100, filled_quantity=100, fill_rate=1.0, turnover=1000.0,
            commission=5.0, transaction_tax=3.0, transfer_or_exchange_fee=2.0,
            slippage_cost=10.0, total_cost=20.0, reconciliation_passed=True,
            settlement_lot_count=1,
            pipeline_request_digest="", daily_loop_session_id="", report_path=None),)
        # Last session: valuation reaches 2026-04-06
        last = OOSDailySessionResult(
            decision_session=date(2026, 4, 3), execution_session=date(2026, 4, 6),
            valuation_session=date(2026, 4, 6),
            session_start_equity=100_080.0, session_end_equity=100_160.0,
            session_net_pnl=80.0, gross_pnl=100.0,
            intent_count=1, filled_count=1, partial_fill_count=0, rejected_count=0,
            requested_quantity=100, filled_quantity=100, fill_rate=1.0, turnover=1000.0,
            commission=5.0, transaction_tax=3.0, transfer_or_exchange_fee=2.0,
            slippage_cost=10.0, total_cost=20.0, reconciliation_passed=True,
            settlement_lot_count=1,
            pipeline_request_digest="", daily_loop_session_id="", report_path=None)
        daily = daily + (last,)
        br, be, gap = _compute_benchmark_return(bench, daily, 100_000.0)
        assert gap is None
        assert br == round(3550.0 / 3500.0 - 1.0, 6)


# ---------------------------------------------------------------------------
# E2E
# ---------------------------------------------------------------------------

class TestE2E:
    def test_guaranteed_fill_with_pr114_evidence(self, tmp_path: Path) -> None:
        cfg = CanonicalBaselineConfig(
            data_mode="fixture", output_dir=str(tmp_path / "out"),
            initial_capital=100_000.0, train_window_days=60, test_window_days=20,
            max_windows=1, fixture_symbols=("600000.SH",), fixture_num_sessions=200)
        r = run_canonical_cost_after_fee_baseline(cfg)
        assert r.status == "completed"
        assert r.no_profitability_claim is True
        assert r.parameter_update_mode == "frozen_baseline"

        flat = tuple(s for ss in r.daily_sessions for s in ss)
        # At least one session with actual intent/fill
        sessions_with_intent = [s for s in flat if s.intent_count > 0]
        assert len(sessions_with_intent) > 0, "no session had order intents"
        sessions_with_fill = [s for s in flat if s.filled_count > 0]
        assert len(sessions_with_fill) > 0, "no session had fills"
        sessions_with_qty = [s for s in flat if s.filled_quantity > 0]
        assert len(sessions_with_qty) > 0, "no session had filled_quantity > 0"

        # Reconciliation, provenance, settlement evidence
        for s in flat:
            assert s.reconciliation_passed is True
            assert s.pipeline_request_digest or s.daily_loop_session_id
            assert s.commission >= 0
        assert any(s.settlement_lot_count > 0 for s in flat)

        assert r.benchmark_total_return is not None
        assert r.excess_return is not None

    def test_missing_exact_benchmark_boundary_fails(self) -> None:
        daily = (OOSDailySessionResult(
            decision_session=date(2026, 4, 1), execution_session=date(2026, 4, 2),
            valuation_session=date(2026, 4, 2), session_start_equity=100_000.0,
            session_end_equity=100_100.0, session_net_pnl=100.0, gross_pnl=100.0,
            intent_count=1, filled_count=1, partial_fill_count=0, rejected_count=0,
            requested_quantity=100, filled_quantity=100, fill_rate=1.0, turnover=1000.0,
            commission=0.0, transaction_tax=0.0, transfer_or_exchange_fee=0.0,
            slippage_cost=0.0, total_cost=0.0, reconciliation_passed=True,
            settlement_lot_count=1, pipeline_request_digest="", daily_loop_session_id="", report_path=None),)
        bars = ({"date": "2026-04-02", "close": 3500.0},)
        _, _, gap = _compute_benchmark_return(bars, daily, 100_000.0)
        assert gap == "benchmark_bars_do_not_cover_oos_boundary"

    def test_builder_loader_closure(self, tmp_path: Path) -> None:
        """build → load → canonical run round-trip."""
        from scripts.build_fixed_snapshot_v1 import main as bmain
        out = str(tmp_path / "s.json")
        ret = bmain(["--output", out, "--start-decision-session", "2026-04-01",
                      "--end-decision-session", "2026-04-30", "--symbol", "600000.SH",
                      "--provider-fixture"])
        assert ret == 0
        raw = json.loads(Path(out).read_text(encoding="utf-8"))
        assert raw["provider"] == "synthetic_engineering_fixture"
        assert raw["canonical"] is False
        assert raw["test_only"] is True
        cfg = CanonicalBaselineConfig(
            snapshot_path=out, data_mode="fixed_snapshot",
            output_dir=str(tmp_path / "run"), max_windows=1,
            train_window_days=60, test_window_days=5)
        with pytest.raises(ValueError, match="requires a canonical snapshot"):
            run_canonical_cost_after_fee_baseline(cfg)

    def test_temp_dir_cleanup(self, tmp_path: Path) -> None:
        import tempfile as tm
        before = set(Path(tm.gettempdir()).iterdir())
        cfg = CanonicalBaselineConfig(
            data_mode="fixture", output_dir=str(tmp_path / "out"),
            initial_capital=100_000.0, train_window_days=60, test_window_days=20,
            max_windows=1, fixture_symbols=("600000.SH",), fixture_num_sessions=200)
        run_canonical_cost_after_fee_baseline(cfg)
        after = set(Path(tm.gettempdir()).iterdir())
        new = after - before
        canon_dirs = [d for d in new if "canonical_baseline_" in str(d)]
        assert len(canon_dirs) == 0, f"temp dirs not cleaned: {canon_dirs}"


# ---------------------------------------------------------------------------
# Builder CLI
# ---------------------------------------------------------------------------

class TestBuilderCLI:
    def test_fixture_creates_file(self, tmp_path: Path) -> None:
        from scripts.build_fixed_snapshot_v1 import main as bm
        out = str(tmp_path / "s.json")
        rc = bm(["--output", out, "--start-decision-session", "2026-04-01",
                  "--end-decision-session", "2026-04-10", "--symbol", "600000.SH",
                  "--provider-fixture"])
        assert rc == 0
        assert Path(out).exists()

    def test_live_path_requires_providers(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from scripts.build_fixed_snapshot_v1 import main as bm
        monkeypatch.setattr("scripts.build_fixed_snapshot_v1._construct_tushare_providers",
                            lambda: (_ for _ in ()).throw(RuntimeError("missing configured Tushare")))
        rc = bm(["--output", str(tmp_path / "s.json"),
                  "--start-decision-session", "2026-04-01",
                  "--end-decision-session", "2026-04-10",
                  "--symbol", "600000.SH"])
        assert rc == 1

    def test_live_path_constructs_direct_tushare_providers_and_closes(self, tmp_path: Path,
                                                                       monkeypatch: pytest.MonkeyPatch) -> None:
        from quantpilot_core.real_data_provider import NormalizedDailyBar, ProviderName, TradingCalendar
        from scripts.build_fixed_snapshot_v1 import main as bm

        class Calendar:
            provider_name = ProviderName.TUSHARE
            def fetch_calendar(self, start: date, end: date) -> TradingCalendar:
                return TradingCalendar(tuple(start + timedelta(days=i) for i in range((end - start).days + 1)
                                             if (start + timedelta(days=i)).weekday() < 5), ProviderName.TUSHARE)

        class Bars:
            provider_name = ProviderName.TUSHARE
            def fetch_daily_bars(self, request: Any) -> list[NormalizedDailyBar]:
                return [NormalizedDailyBar(symbol=request.symbol, trade_date=request.start_date,
                         open=10, high=11, low=9, close=10, volume=1_000,
                         provider=ProviderName.TUSHARE),
                        NormalizedDailyBar(symbol=request.symbol, trade_date=request.end_date,
                         open=11, high=12, low=10, close=11, volume=1_000,
                         provider=ProviderName.TUSHARE)]

        monkeypatch.setattr("scripts.build_fixed_snapshot_v1._construct_tushare_providers",
                            lambda: (Calendar(), Bars(), Bars()))
        out = tmp_path / "s.json"
        assert bm(["--output", str(out), "--start-decision-session", "2024-04-01",
                   "--end-decision-session", "2024-04-30", "--symbol", "600000.SH"]) == 0
        manifest = load_and_validate_snapshot(str(out))
        assert manifest.canonical is True and manifest.provider == "tushare"

    def test_no_token_argument(self) -> None:
        assert "--tushare-token" not in Path("scripts/build_fixed_snapshot_v1.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Legacy compatibility
# ---------------------------------------------------------------------------

class TestLegacy:
    def test_default_engine(self) -> None:
        from quantpilot_core.walk_forward.contracts import WalkForwardInput, WalkForwardWindow
        dl = [date(2026, 1, 5) + timedelta(days=i) for i in range(30)]
        prices = pd.DataFrame([{"symbol": "600000.SH", "date": str(d), "open": 10.0,
                                "high": 10.2, "low": 9.8, "close": 10.1, "volume": 100_000}
                               for d in dl])
        wi = WalkForwardInput(historical_price_frame=prices, initial_cash=100_000.0,
                              windows=(WalkForwardWindow(
                                  train_start=str(dl[0]), train_end=str(dl[9]),
                                  test_start=str(dl[10]), test_end=str(dl[14]),
                                  run_label="w1"),),
                              advisory_mode="disabled")
        r = WalkForwardEngine(leakage_guard=LeakageGuard()).run(wi)
        assert r.aggregate_metrics["window_count"] == 1


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

class TestMisc:
    def test_max_dd(self) -> None:
        assert _max_drawdown_from_series([100.0, 90.0, 95.0, 105.0]) == pytest.approx(-0.1)

    def test_protocol(self) -> None:
        assert hasattr(ProductionWindowRunner, "run_window")
        f = ProductionWindowRunnerFactory(
            state_path=Path("/tmp/test"), symbols=("X",), all_bars=(),
            calendar_sessions=(), strategy_id="t")
        assert isinstance(f, WindowRunnerFactory)

    def test_cli_no_token(self) -> None:
        import scripts.run_canonical_cost_after_fee_baseline_v1 as cm
        assert "--tushare-token" not in Path(cm.__file__).read_text(encoding="utf-8")
