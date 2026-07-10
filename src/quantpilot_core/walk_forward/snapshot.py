"""Fixed-snapshot manifest, loader, validator, and builder (PR #115)."""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from quantpilot_core.daily_paper_loop.state import payload_digest


CANONICAL_SNAPSHOT_SCHEMA_VERSION = 1
CANONICAL_SNAPSHOT_MANIFEST_VERSION = "canonical_baseline_v1"
DEFAULT_SNAPSHOT_PATH = "data/snapshots/canonical_baseline_v1.json"
DEFAULT_BENCHMARK_SYMBOL = "000300.SH"


@dataclass(frozen=True)
class SnapshotManifest:
    schema_version: int
    provider: str
    canonical: bool
    retrieval_timestamp: str
    decision_date_range_start: str
    decision_date_range_end: str
    data_date_range_start: str
    data_date_range_end: str
    symbols: tuple[str, ...]
    benchmark_index_symbol: str
    calendar_sessions: tuple[str, ...]
    bars: tuple[Mapping[str, Any], ...]
    benchmark_index_bars: tuple[Mapping[str, Any], ...]
    provenance: Mapping[str, Any]
    digest: str

    @property
    def decision_date_range(self) -> Mapping[str, str]:
        return {"start": self.decision_date_range_start, "end": self.decision_date_range_end}

    @property
    def data_date_range(self) -> Mapping[str, str]:
        return {"start": self.data_date_range_start, "end": self.data_date_range_end}


# ---------------------------------------------------------------------------
# Loader / validator
# ---------------------------------------------------------------------------


def load_and_validate_snapshot(snapshot_path: str) -> SnapshotManifest:
    path = Path(snapshot_path)
    if not path.exists():
        raise ValueError(f"canonical snapshot not found at {snapshot_path}.")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"snapshot is not valid JSON: {path}") from exc

    if raw.get("schema_version") != CANONICAL_SNAPSHOT_SCHEMA_VERSION:
        raise ValueError(f"schema_version mismatch: {raw.get('schema_version')}")

    stored_digest = str(raw.get("digest", ""))
    computed_digest = payload_digest({k: v for k, v in raw.items() if k != "digest"})
    if stored_digest != computed_digest:
        raise ValueError(f"digest mismatch: stored={stored_digest[:16]}... computed={computed_digest[:16]}...")

    provider = str(raw.get("provider", ""))
    is_canonical = bool(raw.get("canonical", False))
    provenance = raw.get("provenance", {})

    if is_canonical:
        if provider != "tushare":
            raise ValueError(f"canonical snapshot requires provider 'tushare', got '{provider}'")
        _validate_no_fallback_deep(provenance, raw)

    benchmark_bars = tuple(raw.get("benchmark_index_bars", ()) or ())
    if is_canonical and not benchmark_bars:
        raise ValueError("canonical baseline requires benchmark_index_bars")

    symbols = tuple(sorted(raw.get("symbols", ()) or ()))
    calendar_sessions = tuple(raw.get("calendar_sessions", ()) or ())
    _validate_calendar_sessions(calendar_sessions)

    return SnapshotManifest(
        schema_version=int(raw["schema_version"]),
        provider=provider, canonical=is_canonical,
        retrieval_timestamp=str(raw.get("retrieval_timestamp", "")),
        decision_date_range_start=str(raw.get("decision_date_range", {}).get("start", "")),
        decision_date_range_end=str(raw.get("decision_date_range", {}).get("end", "")),
        data_date_range_start=str(raw.get("data_date_range", {}).get("start", "")),
        data_date_range_end=str(raw.get("data_date_range", {}).get("end", "")),
        symbols=symbols,
        benchmark_index_symbol=str(raw.get("benchmark_index_symbol", DEFAULT_BENCHMARK_SYMBOL)),
        calendar_sessions=calendar_sessions,
        bars=tuple(raw.get("bars", ()) or ()),
        benchmark_index_bars=benchmark_bars,
        provenance=dict(provenance),
        digest=computed_digest,
    )


def _validate_no_fallback_deep(provenance: Mapping[str, Any], raw: Mapping[str, Any]) -> None:
    """Deep validation: every provider at every level must be tushare, no fallback."""
    # Calendar
    requested = tuple(sorted(str(symbol) for symbol in raw.get("symbols", ()) or ()))
    if not requested:
        raise ValueError("canonical: requested symbols are required")
    bars = tuple(raw.get("bars", ()) or ())
    present = tuple(sorted({str(row.get("symbol", "")) for row in bars if isinstance(row, Mapping)}))
    if present != requested:
        raise ValueError("canonical: requested symbols must exactly match equity-bar symbols")

    cal = provenance.get("calendar")
    if not isinstance(cal, Mapping):
        raise ValueError("canonical: missing calendar provenance")
    if str(cal.get("selected_provider", "")) != "tushare":
        raise ValueError(f"canonical: calendar provider is {cal.get('selected_provider')}, not tushare")
    if cal.get("fallback_used"):
        raise ValueError("canonical: calendar fallback used")

    # Per-symbol bars
    bars_prov = provenance.get("bars")
    if not isinstance(bars_prov, Mapping) or tuple(sorted(str(k) for k in bars_prov)) != requested:
        raise ValueError("canonical: per-symbol provenance keys must exactly match requested symbols")
    for sym in requested:
        sym_prov = bars_prov[sym]
        if not isinstance(sym_prov, Mapping) or str(sym_prov.get("selected_provider", "")) != "tushare":
            raise ValueError(f"canonical: symbol {sym} provider is not tushare")
        if sym_prov.get("fallback_used"):
            raise ValueError(f"canonical: symbol {sym} used fallback")

    # Benchmark
    bench = provenance.get("benchmark")
    if not isinstance(bench, Mapping) or str(bench.get("selected_provider", "")) != "tushare":
        raise ValueError("canonical: benchmark provider is not tushare")
    if bench.get("fallback_used"):
        raise ValueError("canonical: benchmark used fallback")

    # Equity bars: every bar's provider field must be "tushare"
    for i, bar in enumerate(bars):
        if isinstance(bar, Mapping) and str(bar.get("provider", "")) != "tushare":
            raise ValueError(f"canonical: equity bar {i} provider is {bar.get('provider')}, not tushare")
    for i, bar in enumerate(raw.get("benchmark_index_bars", ()) or ()):
        if not isinstance(bar, Mapping) or str(bar.get("provider", "")) != "tushare":
            raise ValueError(f"canonical: benchmark bar {i} provider is not tushare")


def _validate_calendar_sessions(sessions: tuple[str, ...]) -> None:
    if not sessions:
        return
    prev: date | None = None
    for s in sessions:
        d = date.fromisoformat(s)
        if prev is not None and d <= prev:
            raise ValueError(f"calendar sessions not strictly increasing: {s}")
        prev = d


# ---------------------------------------------------------------------------
# Fixture manifest (deterministic, non-canonical, test-only)
# ---------------------------------------------------------------------------


def build_fixture_manifest(
    *, symbols: tuple[str, ...] = ("600000.SH",),
    num_sessions: int = 200,
    benchmark_symbol: str = DEFAULT_BENCHMARK_SYMBOL,
) -> SnapshotManifest:
    bars = tuple(_synthetic_fixture_bars(symbols, num_sessions))
    calendar = tuple(dict.fromkeys(str(r["date"]) for r in sorted(bars, key=lambda r: str(r["date"]))))
    benchmark = tuple(_synthetic_benchmark_bars(calendar, benchmark_symbol))

    payload: dict[str, Any] = {
        "schema_version": CANONICAL_SNAPSHOT_SCHEMA_VERSION,
        "manifest_version": CANONICAL_SNAPSHOT_MANIFEST_VERSION,
        "provider": "synthetic_engineering_fixture",
        "canonical": False,
        "comparison_only": True,
        "test_only": True,
        "retrieval_timestamp": "2026-01-05T00:00:00+00:00",
        # Reserve deterministic history and D+1 coverage; only the middle
        # official-calendar sessions are eligible for OOS decisions.
        "decision_date_range": {"start": calendar[60], "end": calendar[-2]} if len(calendar) > 61 else {},
        "data_date_range": {"start": calendar[0], "end": calendar[-1]} if calendar else {},
        "symbols": list(symbols),
        "benchmark_index_symbol": benchmark_symbol,
        "calendar_sessions": list(calendar),
        "bars": list(bars),
        "benchmark_index_bars": list(benchmark),
        "provenance": {
            "calendar": {"selected_provider": "synthetic_engineering_fixture", "fallback_used": False, "attempts": []},
            "bars": {},
            "benchmark": {"selected_provider": "synthetic_engineering_fixture", "fallback_used": False},
            "data_mode": "fixture",
            "note": "synthetic deterministic fixture — not real market data",
        },
    }
    payload["digest"] = payload_digest({k: v for k, v in payload.items() if k != "digest"})
    return SnapshotManifest(
        schema_version=payload["schema_version"], provider=payload["provider"],
        canonical=payload["canonical"],
        retrieval_timestamp=payload["retrieval_timestamp"],
        decision_date_range_start=payload["decision_date_range"]["start"],
        decision_date_range_end=payload["decision_date_range"]["end"],
        data_date_range_start=payload["data_date_range"]["start"],
        data_date_range_end=payload["data_date_range"]["end"],
        symbols=tuple(payload["symbols"]),
        benchmark_index_symbol=payload["benchmark_index_symbol"],
        calendar_sessions=tuple(payload["calendar_sessions"]),
        bars=tuple(payload["bars"]),
        benchmark_index_bars=tuple(payload["benchmark_index_bars"]),
        provenance=payload["provenance"], digest=payload["digest"],
    )


def _synthetic_fixture_bars(symbols: tuple[str, ...], num_sessions: int) -> list[dict[str, Any]]:
    from datetime import timedelta
    start = date(2026, 1, 5)
    rows: list[dict[str, Any]] = []
    for si, sym in enumerate(symbols):
        base = 9.0 + si * 3.0
        prev = base
        for i in range(num_sessions):
            sess = start + timedelta(days=i)
            if sess.weekday() >= 5:
                continue
            drift = (len(symbols) - si) * 0.006
            wave = math.sin(i / 5.0 + si) * 0.03
            close = round(base * (1.0 + drift * i + wave), 4)
            rows.append({"symbol": sym, "date": sess.isoformat(),
                         "open": round(close * 0.995, 4), "high": round(close * 1.015, 4),
                         "low": round(close * 0.985, 4), "close": close,
                         "previous_close": prev, "volume": float(120_000 + si * 25_000 + i * 100),
                         "amount": round(close * (120_000 + si * 25_000 + i * 100), 6),
                         "is_suspended": False, "provider": "synthetic_engineering_fixture"})
            prev = close
    return rows


def _synthetic_benchmark_bars(calendar_sessions: tuple[str, ...],
                               benchmark_symbol: str = DEFAULT_BENCHMARK_SYMBOL) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    base = 3500.0
    for i, sess in enumerate(calendar_sessions):
        close = round(base * (1.0 + 0.0002 * i + math.sin(i / 10.0) * 0.005), 4)
        rows.append({"symbol": benchmark_symbol, "date": sess, "close": close,
                     "provider": "synthetic_engineering_fixture"})
    return rows


# ---------------------------------------------------------------------------
# Live snapshot builder
# ---------------------------------------------------------------------------


def build_and_persist_snapshot(
    symbols: tuple[str, ...],
    start_decision_session: str,
    end_decision_session: str,
    output_path: str,
    *,
    benchmark_index_symbol: str = DEFAULT_BENCHMARK_SYMBOL,
    calendar_provider: Any = None,
    bar_provider: Any = None,
    index_provider: Any = None,
    allow_comparison_fallback: bool = False,
) -> str:
    if calendar_provider is None or bar_provider is None:
        raise ValueError("snapshot builder requires explicit calendar_provider and bar_provider")

    start = date.fromisoformat(start_decision_session)
    end = date.fromisoformat(end_decision_session)
    from datetime import timedelta

    cal_result = calendar_provider.fetch_calendar_with_provenance(
        start - timedelta(days=160), end + timedelta(days=10))
    cal_prov = str(cal_result.selected_provider.value)
    cal_fb = bool(cal_result.fallback_used)

    bar_start = cal_result.calendar.shift_session(start, -60)
    bar_end = cal_result.calendar.next_session(end)
    all_bars: list[dict[str, Any]] = []
    bar_provenance: dict[str, Any] = {}
    any_fb = cal_fb
    any_non_tushare = cal_prov != "tushare"

    for sym in symbols:
        from quantpilot_core.real_data_provider import DailyBarRequest
        req = DailyBarRequest(symbol=sym, start_date=bar_start, end_date=bar_end)
        result = bar_provider.fetch_daily_bars_with_provenance(req)
        sp = str(result.selected_provider.value)
        sf = bool(result.fallback_used)
        bar_provenance[sym] = {"selected_provider": sp, "fallback_used": sf,
            "attempts": [{"provider": str(a.provider.value), "status": a.status, "reason": a.reason}
                         for a in (result.attempts or ())]}
        if sf: any_fb = True
        if sp != "tushare": any_non_tushare = True
        if not result.bars:
            raise ValueError(f"no bar data for symbol {sym}")
        for nb in result.bars:
            all_bars.append({"symbol": nb.symbol, "date": nb.trade_date.isoformat(),
                "open": nb.open, "high": nb.high, "low": nb.low, "close": nb.close,
                "volume": nb.volume, "amount": nb.amount, "previous_close": nb.previous_close,
                "is_suspended": getattr(nb, "is_suspended", False),
                "provider": str(nb.provider.value) if hasattr(nb.provider, "value") else str(nb.provider)})

    benchmark_bars: list[dict[str, Any]] = []
    benchmark_prov: dict[str, Any] = {}
    if index_provider is not None:
        from quantpilot_core.real_data_provider import DailyBarRequest
        ireq = DailyBarRequest(symbol=benchmark_index_symbol, start_date=bar_start, end_date=bar_end)
        try:
            ires = index_provider.fetch_index_daily_bars_with_provenance(ireq)
            ip = str(ires.selected_provider.value)
            iff = bool(ires.fallback_used)
            benchmark_prov = {"selected_provider": ip, "fallback_used": iff}
            if iff: any_fb = True
            if ip != "tushare": any_non_tushare = True
            for nb in ires.bars:
                benchmark_bars.append({"symbol": benchmark_index_symbol, "date": nb.trade_date.isoformat(),
                                       "close": nb.close, "provider": str(nb.provider.value) if hasattr(nb.provider, "value") else str(nb.provider)})
        except Exception:
            benchmark_prov = {"error": "index_provider_unavailable"}
    else:
        benchmark_prov = {"error": "no_index_provider_supplied"}

    is_canonical = not any_non_tushare and not any_fb and bool(benchmark_bars)
    if not allow_comparison_fallback:
        if any_non_tushare:
            raise ValueError("non-Tushare provider selected; set allow_comparison_fallback=True")
        if any_fb:
            raise ValueError("provider fallback used; set allow_comparison_fallback=True")
        if not benchmark_bars:
            raise ValueError("benchmark index unavailable; set allow_comparison_fallback=True")

    canonical_bars = sorted(all_bars, key=lambda r: (r["date"], r["symbol"]))
    cal_sessions = cal_result.calendar.to_iso_strings()
    data_start = str(cal_result.calendar.shift_session(start, -60))
    data_end = str(cal_result.calendar.next_session(end))

    payload: dict[str, Any] = {
        "schema_version": CANONICAL_SNAPSHOT_SCHEMA_VERSION,
        "manifest_version": CANONICAL_SNAPSHOT_MANIFEST_VERSION,
        "provider": "tushare" if is_canonical else cal_prov,
        "canonical": is_canonical,
        "retrieval_timestamp": datetime.now(timezone.utc).isoformat(),
        "decision_date_range": {"start": start_decision_session, "end": end_decision_session},
        "data_date_range": {"start": data_start, "end": data_end},
        "symbols": sorted(symbols),
        "benchmark_index_symbol": benchmark_index_symbol,
        "calendar_sessions": list(cal_sessions),
        "bars": canonical_bars,
        "benchmark_index_bars": benchmark_bars,
        "provenance": {
            "calendar": {"selected_provider": cal_prov, "fallback_used": cal_fb,
                "attempts": [{"provider": str(a.provider.value), "status": a.status, "reason": a.reason}
                             for a in (cal_result.attempts or ())]},
            "bars": bar_provenance,
            "benchmark": benchmark_prov,
        },
    }
    if not is_canonical:
        payload["comparison_only"] = True
    payload["digest"] = payload_digest({k: v for k, v in payload.items() if k != "digest"})

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    serialized = json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True)
    tmp.write_text(serialized + "\n", encoding="utf-8")
    os.fsync(tmp.open("w", encoding="utf-8").fileno()) if False else None
    with tmp.open("w", encoding="utf-8") as fh:
        fh.write(serialized); fh.write("\n"); fh.flush(); os.fsync(fh.fileno())
    os.replace(tmp, path)
    return str(path)
