"""Atomic reporting persistence; it stores source facts and calculates nothing."""
from __future__ import annotations

import hashlib
import json
import os
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from typing import Any, Mapping, Protocol, Sequence


SCHEMA_VERSION = 3


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def payload_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class ReportingConflictError(ValueError):
    """A stable reporting identity was replayed with different immutable data."""


class ReportingStore(Protocol):
    def initialize(self) -> None: ...
    def persist_cycle(self, bundle: Any) -> None: ...
    def persist_market_data(self, events: Sequence[Any], bars: Sequence[Any]) -> None: ...
    def get_session(self, session_id: str) -> Mapping[str, Any] | None: ...


def initialize_reporting_store(
    provider: str,
    *,
    dsn: str | None = None,
) -> tuple[ReportingStore, str]:
    """Initialize the existing memory or PostgreSQL reporting store."""

    if provider not in {"auto", "memory", "postgresql"}:
        raise ValueError(f"unsupported reporting store provider: {provider}")
    configured_dsn = dsn if dsn is not None else os.environ.get("QUANTPILOT_POSTGRES_DSN")
    resolved = "postgresql" if provider == "auto" and configured_dsn else provider
    if resolved == "auto":
        resolved = "memory"
    if resolved == "postgresql" and not configured_dsn:
        raise RuntimeError(
            "--store-provider postgresql requires QUANTPILOT_POSTGRES_DSN to be configured"
        )
    store: ReportingStore = (
        PostgreSQLReportingStore(configured_dsn)
        if resolved == "postgresql"
        else InMemoryReportingStore()
    )
    store.initialize()
    return store, resolved


class InMemoryReportingStore:
    def __init__(self) -> None:
        self.sessions: dict[str, dict[str, Any]] = {}
        self.reports: dict[str, dict[str, Any]] = {}
        self.learning: dict[str, dict[str, Any]] = {}
        self.shadow: dict[str, dict[str, Any]] = {}
        self.facts: dict[str, dict[tuple[str, str, int], dict[str, Any]]] = {name: {} for name in ("paper_orders", "paper_fills", "paper_positions", "paper_equity_curve", "paper_reconciliation")}
        self.market_events: dict[str, dict[str, Any]] = {}
        self.intraday_bars: dict[str, dict[str, Any]] = {}

    def initialize(self) -> None:
        return None

    def persist_cycle(self, bundle: Any) -> None:
        # Validate against copies first: failure is all-or-nothing.
        tables = (dict(self.sessions), dict(self.reports), dict(self.learning), dict(self.shadow), {name: dict(rows) for name, rows in self.facts.items()})
        self._write_bundle(tables, bundle)
        self.sessions, self.reports, self.learning, self.shadow, self.facts = tables

    def persist_market_data(self, events: Sequence[Any], bars: Sequence[Any]) -> None:
        market_events = dict(self.market_events)
        intraday_bars = dict(self.intraday_bars)
        for event in events:
            payload = _market_payload(event)
            event_id = payload_digest(payload)
            row = {
                "event_id": event_id,
                "provider": str(payload.get("provider", "")),
                "symbol": str(payload["symbol"]),
                "event_timestamp": str(payload["timestamp"]),
                "received_at": str(payload["received_at"]),
                "payload": payload,
            }
            self._immutable(market_events, event_id, row, "payload_digest")
        for bar in bars:
            payload = _market_payload(bar)
            bar_id = payload_digest(payload)
            row = {
                "bar_id": bar_id,
                "provider": str(payload.get("provider", "")),
                "symbol": str(payload["symbol"]),
                "bar_start": str(payload["start"]),
                "interval_minutes": int(payload["interval_minutes"]),
                "payload": payload,
            }
            self._immutable(intraday_bars, bar_id, row, "payload_digest")
        self.market_events = market_events
        self.intraday_bars = intraday_bars

    def _write_bundle(self, tables: Any, bundle: Any) -> None:
        sessions, reports, learning, shadow, facts = tables
        session = dict(bundle.session); sid = str(session["session_id"])
        self._immutable(sessions, sid, session, "report_digest")
        self._immutable(reports, sid, {"payload": dict(bundle.report)}, "payload_digest")
        self._immutable(learning, sid, {"payload": dict(bundle.learning)}, "payload_digest")
        self._immutable(shadow, sid, {"payload": dict(bundle.shadow)}, "payload_digest")
        for table, rows in bundle.facts.items():
            if table not in facts:
                raise ValueError(f"unsupported fact table: {table}")
            for row in rows:
                item = dict(row)
                key = (sid, str(item["source_identity"]), int(item.get("source_index", 0)))
                self._immutable(facts[table], key, item, "payload_digest")

    @staticmethod
    def _immutable(table: dict[Any, dict[str, Any]], key: Any, value: Mapping[str, Any], digest_key: str) -> None:
        row = dict(value)
        row.setdefault(digest_key, payload_digest(row.get("payload", row)))
        prior = table.get(key)
        if prior is not None and prior[digest_key] != row[digest_key]:
            raise ReportingConflictError(f"conflicting digest for identity: {key}")
        table.setdefault(key, row)

    # Legacy helpers retained as small adapters for callers outside this PR.
    def upsert_session(self, session: Mapping[str, Any]) -> None: self._immutable(self.sessions, str(session["session_id"]), session, "report_digest")
    def upsert_report(self, sid: str, payload: Mapping[str, Any]) -> None: self._immutable(self.reports, sid, {"payload": dict(payload)}, "payload_digest")
    def upsert_learning(self, sid: str, payload: Mapping[str, Any]) -> None: self._immutable(self.learning, sid, {"payload": dict(payload)}, "payload_digest")
    def upsert_shadow(self, sid: str, payload: Mapping[str, Any]) -> None: self._immutable(self.shadow, sid, {"payload": dict(payload)}, "payload_digest")
    def get_session(self, session_id: str) -> Mapping[str, Any] | None: return self.sessions.get(session_id)


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS reporting_schema_version (version INTEGER PRIMARY KEY);
INSERT INTO reporting_schema_version(version) VALUES (3) ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS paper_sessions (session_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, decision_session TEXT NOT NULL, execution_session TEXT, status TEXT NOT NULL, strategy_id TEXT, production_manifest_digest TEXT, effective_parameter_digest TEXT, production_input_digest TEXT, state_hash_before TEXT, state_hash_after TEXT, prefect_flow_id TEXT, prefect_deployment_id TEXT, prefect_flow_run_id TEXT, replay_status TEXT NOT NULL, failure_class TEXT, failure_reason TEXT, started_at TIMESTAMPTZ NOT NULL, completed_at TIMESTAMPTZ NOT NULL, report_digest TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS paper_session_reports (session_id TEXT PRIMARY KEY REFERENCES paper_sessions(session_id), schema_version INTEGER NOT NULL, payload JSONB NOT NULL, payload_digest TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS learning_desk_reports (session_id TEXT PRIMARY KEY REFERENCES paper_sessions(session_id), payload JSONB NOT NULL, payload_digest TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ai_shadow_reports (session_id TEXT PRIMARY KEY REFERENCES paper_sessions(session_id), mode TEXT NOT NULL, payload JSONB NOT NULL, payload_digest TEXT NOT NULL, evidence_digest TEXT NOT NULL, physical_model_calls INTEGER NOT NULL, cache_hits INTEGER NOT NULL, estimated_api_cost DOUBLE PRECISION NOT NULL);
CREATE TABLE IF NOT EXISTS paper_orders (session_id TEXT REFERENCES paper_sessions(session_id), source_identity TEXT NOT NULL, source_index INTEGER NOT NULL, payload JSONB NOT NULL, payload_digest TEXT NOT NULL, PRIMARY KEY(session_id,source_identity,source_index));
CREATE TABLE IF NOT EXISTS paper_fills (session_id TEXT REFERENCES paper_sessions(session_id), source_identity TEXT NOT NULL, source_index INTEGER NOT NULL, payload JSONB NOT NULL, payload_digest TEXT NOT NULL, PRIMARY KEY(session_id,source_identity,source_index));
CREATE TABLE IF NOT EXISTS paper_positions (session_id TEXT REFERENCES paper_sessions(session_id), source_identity TEXT NOT NULL, source_index INTEGER NOT NULL, payload JSONB NOT NULL, payload_digest TEXT NOT NULL, PRIMARY KEY(session_id,source_identity,source_index));
CREATE TABLE IF NOT EXISTS paper_equity_curve (session_id TEXT REFERENCES paper_sessions(session_id), source_identity TEXT NOT NULL, source_index INTEGER NOT NULL, payload JSONB NOT NULL, payload_digest TEXT NOT NULL, PRIMARY KEY(session_id,source_identity,source_index));
CREATE TABLE IF NOT EXISTS paper_reconciliation (session_id TEXT REFERENCES paper_sessions(session_id), source_identity TEXT NOT NULL, source_index INTEGER NOT NULL, payload JSONB NOT NULL, payload_digest TEXT NOT NULL, PRIMARY KEY(session_id,source_identity,source_index));
CREATE TABLE IF NOT EXISTS market_level1_events (event_id TEXT PRIMARY KEY, provider TEXT NOT NULL, symbol TEXT NOT NULL, event_timestamp TIMESTAMPTZ NOT NULL, received_at TIMESTAMPTZ NOT NULL, payload JSONB NOT NULL, payload_digest TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS market_intraday_bars (bar_id TEXT PRIMARY KEY, provider TEXT NOT NULL, symbol TEXT NOT NULL, bar_start TIMESTAMPTZ NOT NULL, interval_minutes INTEGER NOT NULL, payload JSONB NOT NULL, payload_digest TEXT NOT NULL);
"""


class PostgreSQLReportingStore:
    def __init__(self, dsn: str | None = None, *, connection: Any | None = None) -> None:
        self.dsn, self.connection = dsn, connection

    def _conn(self) -> Any:
        if self.connection is None:
            try:
                import psycopg
            except ImportError as exc:
                raise RuntimeError("install quantpilot-ai-next[continuous-paper] for PostgreSQL") from exc
            self.connection = psycopg.connect(self.dsn)
        return self.connection

    def initialize(self) -> None:
        conn = self._conn()
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
        conn.commit()

    def persist_cycle(self, bundle: Any) -> None:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                self._check_and_insert(cur, "paper_sessions", "session_id", dict(bundle.session), "report_digest", session=True)
                self._check_and_insert(cur, "paper_session_reports", "session_id", {"session_id": bundle.session["session_id"], "schema_version": SCHEMA_VERSION, "payload": bundle.report}, "payload_digest")
                self._check_and_insert(cur, "learning_desk_reports", "session_id", {"session_id": bundle.session["session_id"], "payload": bundle.learning}, "payload_digest")
                shadow = dict(bundle.shadow)
                self._check_and_insert(cur, "ai_shadow_reports", "session_id", {"session_id": bundle.session["session_id"], "mode": shadow.get("mode", "disabled"), "payload": shadow, "evidence_digest": shadow.get("evidence_digest", ""), "physical_model_calls": shadow.get("physical_model_calls", 0), "cache_hits": shadow.get("cache_hits", 0), "estimated_api_cost": shadow.get("estimated_api_cost", 0.0)}, "payload_digest")
                for table, rows in bundle.facts.items():
                    for row in rows:
                        self._check_and_insert(cur, table, "session_id,source_identity,source_index", dict(row), "payload_digest")
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def persist_market_data(self, events: Sequence[Any], bars: Sequence[Any]) -> None:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                for event in events:
                    payload = _market_payload(event)
                    event_id = payload_digest(payload)
                    self._check_and_insert(
                        cur,
                        "market_level1_events",
                        "event_id",
                        {
                            "event_id": event_id,
                            "provider": str(payload.get("provider", "")),
                            "symbol": str(payload["symbol"]),
                            "event_timestamp": str(payload["timestamp"]),
                            "received_at": str(payload["received_at"]),
                            "payload": payload,
                        },
                        "payload_digest",
                    )
                for bar in bars:
                    payload = _market_payload(bar)
                    bar_id = payload_digest(payload)
                    self._check_and_insert(
                        cur,
                        "market_intraday_bars",
                        "bar_id",
                        {
                            "bar_id": bar_id,
                            "provider": str(payload.get("provider", "")),
                            "symbol": str(payload["symbol"]),
                            "bar_start": str(payload["start"]),
                            "interval_minutes": int(payload["interval_minutes"]),
                            "payload": payload,
                        },
                        "payload_digest",
                    )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _check_and_insert(self, cur: Any, table: str, keys: str, row: Mapping[str, Any], digest_key: str, *, session: bool = False) -> None:
        item = dict(row); item.setdefault(digest_key, payload_digest(item.get("payload", item)))
        key_names = keys.split(",")
        where = " AND ".join(f"{name}=%s" for name in key_names)
        args = tuple(item[name] for name in key_names)
        cur.execute(f"SELECT {digest_key} FROM {table} WHERE {where}", args)
        old = cur.fetchone()
        if old:
            if old[0] != item[digest_key]:
                raise ReportingConflictError(f"conflicting digest for {table}: {args}")
            return
        columns = list(item)
        values = []
        for name in columns:
            values.append(canonical_json(item[name]) if name == "payload" else item[name])
        placeholders = ",".join("%s::jsonb" if name == "payload" else "%s" for name in columns)
        cur.execute(f"INSERT INTO {table}({','.join(columns)}) VALUES({placeholders})", tuple(values))

    def get_session(self, session_id: str) -> Mapping[str, Any] | None:
        with self._conn().cursor() as cur:
            cur.execute("SELECT session_id, report_digest FROM paper_sessions WHERE session_id=%s", (session_id,))
            row = cur.fetchone()
        return {"session_id": row[0], "report_digest": row[1]} if row else None


def _market_payload(value: Any) -> Mapping[str, Any]:
    if is_dataclass(value) and not isinstance(value, type):
        payload = asdict(value)
    elif isinstance(value, Mapping):
        payload = dict(value)
    else:
        raise TypeError("market data rows must be dataclasses or mappings")
    return _json_ready(payload)


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_ready(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    enum_value = getattr(value, "value", None)
    if enum_value is not None and isinstance(enum_value, (str, int, float, bool)):
        return enum_value
    return value
