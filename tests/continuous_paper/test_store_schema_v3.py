from __future__ import annotations

from quantpilot_core.continuous_paper.store import PostgreSQLReportingStore, SCHEMA_SQL, SCHEMA_VERSION


class _Cursor:
    def __init__(self, connection) -> None:
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def execute(self, sql: str) -> None:
        normalized = sql.upper()
        assert "DROP TABLE" not in normalized
        assert "TRUNCATE" not in normalized
        assert "DELETE FROM" not in normalized
        self.connection.statements.append(sql)
        if "VALUES (3) ON CONFLICT DO NOTHING" in sql:
            self.connection.schema_versions.add(3)
        for table in ("market_level1_events", "market_intraday_bars"):
            if f"CREATE TABLE IF NOT EXISTS {table}" in sql:
                self.connection.tables.add(table)


class _ExistingV2Connection:
    def __init__(self) -> None:
        self.schema_versions = {2}
        self.tables = {"paper_sessions", "paper_session_reports"}
        self.existing_session = {"session_id": "preserved-v2-session"}
        self.statements = []
        self.commits = 0

    def cursor(self) -> _Cursor:
        return _Cursor(self)

    def commit(self) -> None:
        self.commits += 1


def test_schema_v2_store_upgrades_additively_and_idempotently_to_v3() -> None:
    connection = _ExistingV2Connection()
    store = PostgreSQLReportingStore(connection=connection)

    store.initialize()
    store.initialize()

    assert SCHEMA_VERSION == 3
    assert connection.schema_versions == {2, 3}
    assert connection.existing_session == {"session_id": "preserved-v2-session"}
    assert {"paper_sessions", "paper_session_reports"} <= connection.tables
    assert {"market_level1_events", "market_intraday_bars"} <= connection.tables
    assert connection.commits == 2
    assert all("CREATE TABLE IF NOT EXISTS" in statement for statement in connection.statements)
    assert "ALTER TABLE" not in SCHEMA_SQL.upper()
