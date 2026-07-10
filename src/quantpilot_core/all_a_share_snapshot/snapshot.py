"""Builder, validator, and loader for the partitioned all-A-share artifact."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from quantpilot_core.all_a_share_snapshot.contracts import (
    AllAShareProvider, DEFAULT_BENCHMARK, OPTIONAL_DATASETS, REQUIRED_DATASETS,
    SnapshotConfig, ValidationResult,
)
from quantpilot_core.all_a_share_snapshot.pit import listed_universe
from quantpilot_core.all_a_share_snapshot.storage import (
    FORMAT_VERSION, SCHEMA_VERSION, atomic_json, atomic_write, digest, file_hash,
    read_table, schema_fingerprint, table_for,
)

NAMECHANGE_RESPONSE_CAP = 10_000
STRUCTURAL_KEYS = {
    "stock_basic": ("ts_code",), "calendar": ("exchange", "cal_date"),
    "daily": ("ts_code", "trade_date"), "daily_basic": ("ts_code", "trade_date"),
    "adj_factor": ("ts_code", "trade_date"), "suspend": ("ts_code", "trade_date", "suspend_type", "suspend_timing"),
    "limits": ("ts_code", "trade_date"), "benchmark": ("ts_code", "trade_date"),
    # end_date is deliberately nullable; this full business record key makes
    # exact repeats removable without treating an open-ended record as malformed.
    "namechange": ("ts_code", "name", "start_date", "end_date", "ann_date", "change_reason"),
    "namechange_shard": ("ts_code", "name", "start_date", "end_date", "ann_date", "change_reason"),
}
REQUIRED_KEY_FIELDS = {"namechange": ("ts_code", "name", "start_date"), "namechange_shard": ("ts_code", "name", "start_date")}


def _now() -> str: return datetime.now(timezone.utc).isoformat()
def _manifest_path(root: Path) -> Path: return root / "manifest.json"
def _load(root: Path) -> dict[str, Any] | None:
    path = _manifest_path(root)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
def _artifact_path(root: Path, value: object) -> Path:
    """Resolve a manifest path only inside the supplied artifact root."""
    relative = Path(str(value))
    if relative.is_absolute() or ".." in relative.parts: raise ValueError("unsafe manifest partition path")
    candidate = (root / relative).resolve()
    try: candidate.relative_to(root.resolve())
    except ValueError as exc: raise ValueError("unsafe manifest partition path") from exc
    return candidate
def _path(dataset: str, trade_date: str | None = None) -> str:
    if dataset in {"stock_basic", "calendar", "namechange"}: return f"{dataset}/part-00000.parquet"
    if dataset == "benchmark": return "benchmark/000300.SH/part-00000.parquet"
    assert trade_date
    return f"{dataset}/trade_year={trade_date[:4]}/trade_date={trade_date}/part-00000.parquet"
def _shard_path(shard: int) -> str: return f"namechange/shard={shard:05d}/part-00000.parquet"


def _base(config: SnapshotConfig, provider: AllAShareProvider) -> dict[str, Any]:
    return {"format_version": FORMAT_VERSION, "schema_version": SCHEMA_VERSION,
     "provider": str(provider.provider_name), "canonical": True, "status": "building",
     "requested_date_range": {"start": config.start_date, "end": config.end_date},
     "actual_date_range": {"start": None, "end": None}, "created_at": _now(), "completed_at": None,
     "exchanges": [], "boards": [], "list_statuses_requested": list(config.list_statuses),
     "capabilities": {d: "not_requested" for d in OPTIONAL_DATASETS}, "symbol_counts": {},
     "official_session_count": 0, "benchmark": {"symbol": DEFAULT_BENCHMARK, "row_count": 0},
     "dataset_row_counts": {}, "partition_counts": {}, "partitions": [], "failed_partitions": [],
     "retry_count": 0, "resume_count": 0, "fallback_used": False, "test_only": config.test_only,
     "comparison_only": False, "scope": "a_share_equity_pit",
     # This artifact is intentionally equity-only.  Existing mixed stock/ETF
     # execution consumes its own instrument master; non-equity provider rows
     # are classified and audited here rather than mistaken for corrupt stocks.
     "mixed_instrument_integration": "external_instrument_master_boundary",
     "outside_universe_rows": {}, "instrument_audit": {}, "unexplained_symbols": {},
     "historical_code_resolutions": {}, "historical_code_resolution_calls": 0,
     "namechange": {"strategy": "per_symbol_shards", "response_cap": NAMECHANGE_RESPONSE_CAP, "complete": False,
                    "shard_size": config.namechange_shard_size, "planned_symbol_count": 0,
                    "completed_symbol_count": 0, "planned_shard_count": 0, "completed_shard_count": 0,
                    "retry_delay_seconds": config.retry_delay_seconds},
     "digest": ""}


def _partition_valid(root: Path, entry: Mapping[str, Any], dataset: str, trade_date: str | None) -> bool:
    try: path = _artifact_path(root, entry.get("path", ""))
    except ValueError: return False
    if not path.exists() or entry.get("trade_date") != trade_date: return False
    try:
        table = read_table(path)
        return (file_hash(path) == entry.get("sha256") and table.num_rows == entry.get("row_count")
                and schema_fingerprint(table.schema) == entry.get("schema_fingerprint")
                and schema_fingerprint(table_for(dataset, []).schema) == entry.get("schema_fingerprint"))
    except Exception: return False


def _store(root: Path, manifest: dict[str, Any], dataset: str, rows: Sequence[Mapping[str, Any]],
           trade_date: str | None, old: Mapping[str, Any] | None = None,
           audit: Mapping[str, Any] | None = None, path: str | None = None) -> None:
    if old and _partition_valid(root, old, dataset, trade_date):
        manifest["partitions"].append(dict(old)); manifest["resume_count"] += 1; return
    issues = _row_issues(dataset, rows, trade_date)
    if issues: raise ValueError("; ".join(issues))
    relative_path = path or _path(dataset, trade_date)
    info = dict(atomic_write(dataset, _artifact_path(root, relative_path), rows)); info["path"] = relative_path
    if audit is not None: info["instrument_audit"] = dict(audit)
    info.update(dataset=dataset, trade_date=trade_date); manifest["partitions"].append(info)


def _aggregate_audits(manifest: dict[str, Any]) -> None:
    aggregate: dict[str, dict[str, int]] = {}; unexplained: dict[str, dict[str, Any]] = {}; outside: dict[str, int] = {}
    for entry in manifest["partitions"]:
        audit = entry.get("instrument_audit")
        if not isinstance(audit, Mapping): continue
        dataset = str(entry["dataset"]); counts = audit.get("counts", {})
        bucket = aggregate.setdefault(dataset, {})
        for kind, count in counts.items(): bucket[str(kind)] = bucket.get(str(kind), 0) + int(count)
        removed = int(audit.get("provider_row_count", 0)) - int(audit.get("persisted_row_count", 0))
        if removed: outside[dataset] = outside.get(dataset, 0) + removed
        for kind, values in audit.get("examples", {}).items():
            if kind not in {"absent_stock_basic", "unknown"}: continue
            record = unexplained.setdefault(dataset, {"count": 0, "examples": []})
            record["count"] += int(counts.get(kind, 0))
            for code in values:
                if code not in record["examples"] and len(record["examples"]) < 20: record["examples"].append(code)
    manifest["instrument_audit"] = aggregate; manifest["outside_universe_rows"] = outside; manifest["unexplained_symbols"] = unexplained


def _fetch(call, config: SnapshotConfig, manifest: dict[str, Any]):
    for attempt in range(config.max_retries + 1):
        try: return call()
        except (PermissionError, AttributeError, NotImplementedError): raise
        except Exception:
            if attempt >= config.max_retries: raise
            manifest["retry_count"] += 1
            time.sleep(max(0.0, min(config.retry_delay_seconds * (attempt + 1), 5.0)))


def _deduplicate(dataset: str, rows: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    seen: set[tuple[Any, ...]] = set(); output = []
    required = REQUIRED_KEY_FIELDS.get(dataset, STRUCTURAL_KEYS[dataset])
    for row in rows:
        item = dict(row)
        if any(not str(item.get(field) or "") for field in required): raise ValueError(f"null structural key: {dataset}")
        key = tuple(item.get(field) for field in STRUCTURAL_KEYS[dataset])
        if key in seen:
            if dataset not in {"namechange", "namechange_shard"}: raise ValueError(f"duplicate structural business key: {dataset}")
            continue
        seen.add(key); output.append(item)
    return output


def _row_issues(dataset: str, rows: Sequence[Mapping[str, Any]], trade_date: str | None) -> tuple[str, ...]:
    keys = STRUCTURAL_KEYS[dataset]; required = REQUIRED_KEY_FIELDS.get(dataset, keys); issues = []
    if any(not str(row.get(field) or "") for row in rows for field in required): issues.append(f"null structural key: {dataset}")
    values = [tuple(row.get(field) for field in keys) for row in rows]
    if dataset not in {"namechange", "namechange_shard"} and len(values) != len(set(values)): issues.append(f"duplicate structural business key: {dataset}")
    if dataset != "namechange_shard" and trade_date is not None and any(str(row.get("trade_date") or "") != str(trade_date) for row in rows): issues.append(f"partition date mismatch: {dataset}:{trade_date}")
    return tuple(issues)


def _instrument_type(row: Mapping[str, Any], equity_codes: set[str]) -> str:
    """Classify a provider row before applying this equity snapshot's scope."""
    code = str(row.get("ts_code") or "").upper()
    if code in equity_codes: return "a_share_equity"
    symbol, _, exchange = code.partition(".")
    if len(symbol) != 6 or exchange not in {"SH", "SZ", "BJ"} or not symbol.isdigit(): return "unknown"
    if (exchange == "SZ" and symbol.startswith("159")) or (exchange == "SH" and symbol.startswith(("51", "52", "56", "58"))): return "etf"
    if (exchange == "SZ" and symbol.startswith("16")) or (exchange == "SH" and symbol.startswith("50")): return "lof"
    if symbol.startswith(("110", "111", "113", "118", "123", "127", "128", "130")): return "convertible_bond"
    return "other_supported_exchange_instrument"


def _is_external_instrument_code(code: str) -> bool:
    symbol, _, exchange = code.upper().partition(".")
    return ((exchange == "SZ" and (symbol.startswith("159") or symbol.startswith("16")))
            or (exchange == "SH" and symbol.startswith(("50", "51", "52", "56", "58")))
            or symbol.startswith(("110", "111", "113", "118", "123", "127", "128", "130")))


def _resolve_historical_code(code: str, stocks: Sequence[Mapping[str, Any]], config: SnapshotConfig,
                             provider: AllAShareProvider, manifest: dict[str, Any]) -> Mapping[str, Any]:
    """Resolve a required historical equity code only from its own name history."""
    cached = manifest["historical_code_resolutions"].get(code)
    if cached is not None: return cached
    exchange = code.rpartition(".")[2]
    if _is_external_instrument_code(code):
        result = {"historical_ts_code": code, "current_ts_code": None, "resolution_status": "unresolved_external_instrument",
                  "exchange_match": False, "list_date_match": False, "name_history_match": False, "candidate_count": 0, "name_history": []}
        manifest["historical_code_resolutions"][code] = result; return result
    try:
        manifest["historical_code_resolution_calls"] += 1
        history = _fetch(lambda: provider.fetch_namechange_by_ts_code(code), config, manifest)
        if len(history) >= NAMECHANGE_RESPONSE_CAP: raise ValueError("response cap reached")
        names = sorted({str(row.get("name") or "") for row in history if str(row.get("name") or "")})
        starts = sorted(str(row.get("start_date") or "") for row in history if str(row.get("start_date") or ""))
        earliest = starts[0] if starts else None
        candidates = [row for row in stocks if str(row.get("ts_code") or "").rpartition(".")[2] == exchange
                      and str(row.get("name") or "") in names and str(row.get("list_date") or "") == earliest]
        result = {"historical_ts_code": code, "current_ts_code": str(candidates[0].get("ts_code")) if len(candidates) == 1 else None,
                  "resolution_status": "resolved" if len(candidates) == 1 else "unresolved_ambiguous_or_no_match",
                  "exchange_match": bool(candidates), "list_date_match": bool(candidates), "name_history_match": bool(candidates),
                  "candidate_count": len(candidates), "earliest_history_start_date": earliest, "name_history": names[:20]}
    except Exception as exc:
        result = {"historical_ts_code": code, "current_ts_code": None, "resolution_status": "unresolved_provider_error",
                  "exchange_match": False, "list_date_match": False, "name_history_match": False, "candidate_count": 0,
                  "name_history": [], "reason": str(exc)}
    manifest["historical_code_resolutions"][code] = result
    return result


def _filter_equity_universe(rows: Sequence[Mapping[str, Any]], pit_codes: set[str], equity_codes: set[str],
                            dataset: str, required_market: bool, resolutions: Mapping[str, Mapping[str, Any]] = {}) -> tuple[list[Mapping[str, Any]], Mapping[str, Any]]:
    kept: list[Mapping[str, Any]] = []; counts: dict[str, int] = {}; examples: dict[str, list[str]] = {}
    for row in rows:
        kind = _instrument_type(row, equity_codes); code = str(row.get("ts_code") or "")
        mapping = resolutions.get(code, {})
        if mapping.get("resolution_status") == "resolved" and str(mapping.get("current_ts_code")) in pit_codes:
            kind = "historical_equity_alias"
        # A required equity feed is not allowed to silently redefine an absent
        # stock-master code as a supported external instrument.
        if required_market and kind not in {"a_share_equity", "historical_equity_alias"}: kind = "absent_stock_basic"
        counts[kind] = counts.get(kind, 0) + 1
        if kind in {"absent_stock_basic", "unknown"} and len(examples.setdefault(kind, [])) < 20: examples[kind].append(code)
        if (kind == "a_share_equity" and code in pit_codes) or kind == "historical_equity_alias": kept.append(dict(row))
        elif kind == "a_share_equity": counts["equity_outside_pit"] = counts.get("equity_outside_pit", 0) + 1
    return kept, {"counts": counts, "examples": examples, "provider_row_count": len(rows), "persisted_row_count": len(kept)}


def build_snapshot(config: SnapshotConfig, provider: AllAShareProvider) -> Mapping[str, Any]:
    """Build or resume an offline-validatable, direct-Tushare snapshot."""
    root = Path(config.root); previous = _load(root) or {}
    old = {(p.get("dataset"), p.get("trade_date")): p for p in previous.get("partitions", [])}
    manifest = _base(config, provider)
    manifest["historical_code_resolutions"] = dict(previous.get("historical_code_resolutions", {}))
    try:
        stocks = _deduplicate("stock_basic", _fetch(lambda: provider.fetch_stock_basic(config.list_statuses), config, manifest))
        _store(root, manifest, "stock_basic", stocks, None, old.get(("stock_basic", None)))
        all_codes = {str(row.get("ts_code") or "") for row in stocks}
        manifest["exchanges"] = sorted({str(x.get("exchange")) for x in stocks if x.get("exchange")})
        manifest["boards"] = sorted({str(x.get("market")) for x in stocks if x.get("market")})
        statuses = {s: sum(1 for x in stocks if str(x.get("list_status")) == s) for s in config.list_statuses}
        manifest["symbol_counts"] = {"total": len(all_codes - {""}), "by_status": statuses, "listed": statuses.get("L", 0), "delisted": statuses.get("D", 0)}
        calendar = _deduplicate("calendar", _fetch(lambda: provider.fetch_trade_cal(config.start_date, config.end_date), config, manifest))
        _store(root, manifest, "calendar", calendar, None, old.get(("calendar", None)))
        sessions = sorted(str(x.get("cal_date")) for x in calendar if str(x.get("is_open")) in {"1", "True", "true"})
        if not sessions: raise ValueError("official trade calendar has no open sessions")
        manifest["official_session_count"] = len(sessions); manifest["actual_date_range"] = {"start": sessions[0], "end": sessions[-1]}
        pit_codes = {d: {str(r.get("ts_code")) for r in listed_universe(stocks, d)} for d in sessions}
        for d in sessions:
            for dataset, method in (("daily", provider.fetch_daily_by_trade_date), ("adj_factor", provider.fetch_adj_factor_by_trade_date)):
                entry = old.get((dataset, d))
                if entry and _partition_valid(root, entry, dataset, d): _store(root, manifest, dataset, (), d, entry); continue
                provider_rows = _fetch(lambda method=method, d=d: method(d), config, manifest)
                if dataset == "daily":
                    for code in sorted({str(row.get("ts_code") or "") for row in provider_rows} - all_codes - {""}):
                        _resolve_historical_code(code, stocks, config, provider, manifest)
                rows, audit = _filter_equity_universe(provider_rows, pit_codes[d], all_codes, dataset, dataset == "daily", manifest["historical_code_resolutions"])
                if audit["counts"].get("absent_stock_basic", 0):
                    manifest["failed_partitions"].append({"dataset": dataset, "trade_date": d, "reason": "provider symbols absent from stock_basic", "examples": audit["examples"].get("absent_stock_basic", [])})
                if dataset == "daily" and not rows: raise ValueError(f"required daily partition empty for official session {d}")
                if dataset == "adj_factor" and not rows: raise ValueError(f"required adj_factor partition empty for official session {d}")
                _store(root, manifest, dataset, _deduplicate(dataset, rows), d, audit=audit)
        benchmark = _deduplicate("benchmark", _fetch(lambda: provider.fetch_index_daily(DEFAULT_BENCHMARK, config.start_date, config.end_date), config, manifest))
        if not benchmark: raise ValueError("required benchmark partition is empty")
        _store(root, manifest, "benchmark", benchmark, None, old.get(("benchmark", None))); manifest["benchmark"]["row_count"] = len(benchmark)
        if config.include_optional:
            for dataset in ("daily_basic", "suspend", "limits"):
                try:
                    for d in sessions:
                        entry = old.get((dataset, d))
                        if entry and _partition_valid(root, entry, dataset, d):
                            _store(root, manifest, dataset, (), d, entry); continue
                        rows, audit = _filter_equity_universe(_fetch(lambda dataset=dataset, d=d: provider.fetch_optional(dataset, d), config, manifest), pit_codes[d], all_codes, dataset, False, manifest["historical_code_resolutions"])
                        _store(root, manifest, dataset, _deduplicate(dataset, rows), d, audit=audit)
                    manifest["capabilities"][dataset] = "available"
                except PermissionError: manifest["capabilities"][dataset] = "unavailable_permission"
                except (AttributeError, NotImplementedError): manifest["capabilities"][dataset] = "unavailable_endpoint"
                except Exception:
                    manifest["capabilities"][dataset] = "incomplete"; manifest["failed_partitions"].append({"dataset": dataset, "trade_date": d})
            try:
                symbols = sorted(str(row.get("ts_code")) for row in stocks if str(row.get("list_date") or "") <= config.end_date and str(row.get("list_date") or ""))
                size = max(1, config.namechange_shard_size); shards = [symbols[i:i + size] for i in range(0, len(symbols), size)]
                meta = manifest["namechange"]; meta.update(planned_symbol_count=len(symbols), planned_shard_count=len(shards))
                shard_entries = []
                for index, codes in enumerate(shards):
                    shard_id = f"shard-{index:05d}"; entry = old.get(("namechange_shard", shard_id))
                    if entry and _partition_valid(root, entry, "namechange_shard", shard_id):
                        _store(root, manifest, "namechange_shard", (), shard_id, entry); shard_entries.append(entry); meta["completed_symbol_count"] += len(codes); meta["completed_shard_count"] += 1; continue
                    records: list[Mapping[str, Any]] = []
                    for code in codes:
                        result = _fetch(lambda code=code: provider.fetch_namechange_by_ts_code(code), config, manifest)
                        if len(result) >= NAMECHANGE_RESPONSE_CAP: raise ValueError(f"namechange response cap reached for {code}; completeness is unknown")
                        records.extend(result)
                    _store(root, manifest, "namechange_shard", _deduplicate("namechange", records), shard_id, path=_shard_path(index))
                    meta["completed_symbol_count"] += len(codes); meta["completed_shard_count"] += 1
                records = []
                for entry in (p for p in manifest["partitions"] if p["dataset"] == "namechange_shard"):
                    records.extend(read_table(_artifact_path(root, entry["path"])).to_pylist())
                _store(root, manifest, "namechange", _deduplicate("namechange", records), None)
                meta["complete"] = True; manifest["capabilities"]["namechange"] = "available"
            except PermissionError: manifest["capabilities"]["namechange"] = "unavailable_permission"
            except (AttributeError, NotImplementedError): manifest["capabilities"]["namechange"] = "unavailable_endpoint"
            except Exception:
                manifest["capabilities"]["namechange"] = "incomplete"; manifest["failed_partitions"].append({"dataset": "namechange", "trade_date": None})
        _aggregate_audits(manifest)
        manifest["status"] = "completed" if not manifest["failed_partitions"] else "incomplete"
    except Exception as exc:
        manifest["status"] = "incomplete"; manifest["failed_partitions"].append({"dataset": "required", "reason": str(exc)})
    manifest["dataset_row_counts"] = {d: sum(int(p["row_count"]) for p in manifest["partitions"] if p["dataset"] == d) for d in REQUIRED_DATASETS + OPTIONAL_DATASETS}
    manifest["partition_counts"] = {d: sum(1 for p in manifest["partitions"] if p["dataset"] == d) for d in REQUIRED_DATASETS + OPTIONAL_DATASETS}
    # completed_at is the local build-end time, regardless of outcome.  It is
    # intentionally excluded from the semantic digest.
    manifest["completed_at"] = _now(); manifest["digest"] = digest(manifest); atomic_json(_manifest_path(root), manifest)
    local = validate_snapshot(root)
    if not local.ok and manifest["status"] == "completed":
        optional = {d for d in OPTIONAL_DATASETS if any(d in error for error in local.errors)}
        for dataset in optional:
            manifest["capabilities"][dataset] = "incomplete"
            manifest["failed_partitions"].append({"dataset": dataset, "reason": "local persisted validation failed"})
        if not optional: manifest["failed_partitions"].append({"dataset": "local_validation", "reason": "persisted artifact validation failed"})
        manifest["status"] = "incomplete"; manifest["digest"] = digest(manifest); atomic_json(_manifest_path(root), manifest)
    return manifest


def _sessions_from_manifest(root: Path, manifest: Mapping[str, Any]) -> tuple[str, ...]:
    entry = next((p for p in manifest.get("partitions", []) if p.get("dataset") == "calendar"), None)
    if not entry: return ()
    return tuple(sorted(str(r["cal_date"]) for r in read_table(_artifact_path(root, entry["path"])).to_pylist() if str(r.get("is_open")) in {"1", "True", "true"}))


def validate_snapshot(root: str | Path) -> ValidationResult:
    root = Path(root); errors: list[str] = []; warnings: list[str] = []; manifest = _load(root)
    if not manifest: return ValidationResult(False, ("manifest.json is missing",), (), 0, {})
    if manifest.get("format_version") != FORMAT_VERSION or manifest.get("schema_version") != SCHEMA_VERSION: errors.append("manifest format/schema version mismatch")
    if manifest.get("digest") != digest(manifest): errors.append("manifest digest mismatch")
    seen = set(); checked = 0; tables: dict[tuple[str, str | None], list[Mapping[str, Any]]] = {}; unsafe_calendar = False
    for p in manifest.get("partitions", []):
        dataset, trade_date = str(p.get("dataset", "")), p.get("trade_date"); identity = (dataset, trade_date); checked += 1
        if identity in seen: errors.append(f"duplicate partition identity: {identity}")
        seen.add(identity)
        try: path = _artifact_path(root, p.get("path", ""))
        except ValueError:
            errors.append(f"unsafe partition path: {p.get('path')}")
            if dataset == "calendar": unsafe_calendar = True
            continue
        if not path.exists(): errors.append(f"missing partition: {p.get('path')}"); continue
        try:
            table = read_table(path); rows = table.to_pylist(); tables[identity] = rows
            if file_hash(path) != p.get("sha256"): errors.append(f"hash mismatch: {p.get('path')}")
            if table.num_rows != p.get("row_count"): errors.append(f"row count mismatch: {p.get('path')}")
            if schema_fingerprint(table.schema) != p.get("schema_fingerprint") or schema_fingerprint(table_for(dataset, []).schema) != p.get("schema_fingerprint"): errors.append(f"schema mismatch: {p.get('path')}")
            key_fields = STRUCTURAL_KEYS.get(dataset, ())
            required = REQUIRED_KEY_FIELDS.get(dataset, key_fields)
            if any(not str(row.get(field) or "") for row in rows for field in required): errors.append(f"null structural key: {dataset}")
            keys = [tuple(row.get(field) for field in key_fields) for row in rows]
            if len(keys) != len(set(keys)): errors.append(f"duplicate structural business key: {dataset}")
            if dataset not in {"namechange_shard"} and trade_date is not None and any(str(row.get("trade_date") or "") != str(trade_date) for row in rows): errors.append(f"partition date mismatch: {dataset}:{trade_date}")
        except Exception as exc: errors.append(f"unreadable partition {p.get('path')}: {exc}")
    datasets = {p.get("dataset") for p in manifest.get("partitions", [])}
    for d in REQUIRED_DATASETS:
        if d not in datasets: errors.append(f"required dataset missing: {d}")
    if unsafe_calendar:
        errors.append("unsafe calendar partition path")
        sessions = ()
    else:
        try: sessions = _sessions_from_manifest(root, manifest)
        except ValueError:
            errors.append("unsafe calendar partition path"); sessions = ()
    for d in sessions:
        for dataset in ("daily", "adj_factor"):
            if (dataset, d) not in tables: errors.append(f"missing required official {dataset} session: {d}")
    stock_rows = tables.get(("stock_basic", None), []); stock_codes = {str(r.get("ts_code") or "") for r in stock_rows}
    resolutions = manifest.get("historical_code_resolutions", {})
    def resolved_current(code: str) -> str | None:
        item = resolutions.get(code, {})
        return str(item.get("current_ts_code")) if item.get("resolution_status") == "resolved" else None
    for (dataset, date), rows in tables.items():
        if dataset in {"benchmark", "calendar", "stock_basic"}: continue
        for row in rows:
            code = str(row.get("ts_code") or "")
            if code not in stock_codes and resolved_current(code) not in stock_codes: errors.append(f"symbol outside stock_basic universe: {dataset}"); break
    for d in sessions:
        daily = {str(r["ts_code"]) for r in tables.get(("daily", d), [])}
        pit = {str(r.get("ts_code")) for r in listed_universe(stock_rows, d)}
        if any(code not in pit and resolved_current(code) not in pit for code in daily): errors.append(f"daily symbols outside PIT universe: {d}")
        if not daily <= {str(r.get("ts_code")) for r in tables.get(("adj_factor", d), [])}: errors.append(f"daily coverage missing from adj_factor: {d}")
        for dataset in ("daily_basic", "limits"):
            if manifest.get("capabilities", {}).get(dataset) == "available":
                values = {str(r.get("ts_code")) for r in tables.get((dataset, d), [])}
                if not daily <= values: errors.append(f"daily coverage missing from {dataset}: {d}")
    benchmark_rows = tables.get(("benchmark", None), [])
    if benchmark_rows and not set(sessions) <= {str(r.get("trade_date")) for r in benchmark_rows}: errors.append("benchmark coverage missing official sessions")
    actual, requested = manifest.get("actual_date_range", {}), manifest.get("requested_date_range", {})
    if sessions and (actual.get("start") != sessions[0] or actual.get("end") != sessions[-1]): errors.append("actual date range inconsistent with official sessions")
    if sessions and (sessions[0] < str(requested.get("start", "")) or sessions[-1] > str(requested.get("end", ""))): errors.append("official sessions outside requested date range")
    capabilities = manifest.get("capabilities", {})
    for dataset in OPTIONAL_DATASETS:
        capability = capabilities.get(dataset)
        if capability == "available" and dataset not in datasets: errors.append(f"available capability missing dataset: {dataset}")
        if capability == "available" and dataset != "namechange":
            available_dates = {date for (name, date) in tables if name == dataset}
            if not set(sessions) <= available_dates: errors.append(f"available capability missing session partitions: {dataset}")
        if capability == "incomplete" and manifest.get("status") == "completed": errors.append(f"completed status inconsistent with incomplete capability: {dataset}")
    namechange = manifest.get("namechange", {})
    if capabilities.get("namechange") == "available":
        if not namechange.get("complete"): errors.append("namechange availability without completeness proof")
        planned_shards = int(namechange.get("planned_shard_count", -1)); completed_shards = int(namechange.get("completed_shard_count", -1))
        planned_symbols = int(namechange.get("planned_symbol_count", -1)); completed_symbols = int(namechange.get("completed_symbol_count", -1))
        shard_rows = [rows for (dataset, _), rows in tables.items() if dataset == "namechange_shard"]
        if planned_shards != completed_shards or planned_symbols != completed_symbols: errors.append("namechange checkpoint counts inconsistent")
        if len(shard_rows) != planned_shards: errors.append("namechange shard partition count inconsistent")
        combined = tables.get(("namechange", None), [])
        business = STRUCTURAL_KEYS["namechange"]
        shard_keys = {tuple(row.get(key) for key in business) for rows in shard_rows for row in rows}
        combined_keys = {tuple(row.get(key) for key in business) for row in combined}
        if len(combined) != len(shard_keys) or combined_keys != shard_keys:
            errors.append("namechange combined table inconsistent with shards")
    if manifest.get("unexplained_symbols", {}).get("daily", {}).get("count", 0): errors.append("required daily symbols absent from stock_basic")
    for code, item in resolutions.items():
        if item.get("resolution_status") == "resolved" and (not item.get("current_ts_code") or item.get("current_ts_code") not in stock_codes):
            errors.append(f"invalid historical code resolution: {code}")
    if manifest.get("status") == "completed" and (manifest.get("failed_partitions") or errors): errors.append("completed status inconsistent with failures")
    return ValidationResult(not errors, tuple(errors), tuple(warnings), checked, manifest)


class SnapshotLoader:
    def __init__(self, root: str | Path): self.root = Path(root); self.manifest = _load(self.root) or {}
    def _one(self, dataset: str, trade_date: str | None = None) -> tuple[Mapping[str, Any], ...]:
        entry = next((p for p in self.manifest.get("partitions", []) if p.get("dataset") == dataset and p.get("trade_date") == trade_date), None)
        return tuple(read_table(_artifact_path(self.root, entry["path"])).to_pylist()) if entry else ()
    def stock_master(self): return self._one("stock_basic")
    def sessions(self): return _sessions_from_manifest(self.root, self.manifest)
    def daily(self, trade_date: str): return self._one("daily", trade_date)
    def adj_factor(self, trade_date: str): return self._one("adj_factor", trade_date)
    def optional(self, dataset: str, trade_date: str | None = None): return self._one(dataset, trade_date)
    def benchmark(self): return self._one("benchmark")
    def listed_universe(self, trade_date: str): return listed_universe(self.stock_master(), trade_date)
