from __future__ import annotations

import json

import pytest

import scripts.run_tdx_level1_adapter_v1 as runner


class _Store:
    def __init__(self, backend: str, dsn: str | None = None) -> None:
        self.backend = backend
        self.dsn = dsn
        self.initialized = False

    def initialize(self) -> None:
        self.initialized = True


def test_shadow_with_postgresql_selection_keeps_postgresql_persistence(monkeypatch, capsys) -> None:
    stores = []
    collectors = []

    def postgresql_store(dsn):
        store = _Store("postgresql", dsn)
        stores.append(store)
        return store

    class Collector:
        def __init__(self, _provider, symbols, **kwargs) -> None:
            self.symbols = tuple(symbols)
            self.kwargs = kwargs
            collectors.append(self)

        def run(self, _duration):
            class Report:
                @staticmethod
                def as_dict():
                    return {
                        "connection_status": "subscribed",
                        "symbols": ("000001.SZ",),
                        "event_count": 1,
                        "snapshot_count": 1,
                        "bar_count": 1,
                        "storage_backend": "postgresql",
                        "shadow": True,
                    }
            return Report()

    monkeypatch.setenv("QUANTPILOT_POSTGRES_DSN", "postgresql://configured")
    monkeypatch.setattr(runner, "PostgreSQLReportingStore", postgresql_store)
    monkeypatch.setattr(runner, "TDXLevel1Provider", lambda _path: object())
    monkeypatch.setattr(runner, "LiveLevel1Collector", Collector)

    result = runner.main(
        [
            "--symbols", "000001.SZ",
            "--tdx-user-dir", r"D:\tongdaxin\PYPlugins\user",
            "--duration", "0",
            "--store-provider", "postgresql",
            "--shadow",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 0
    assert stores[0].initialized is True
    assert stores[0].dsn == "postgresql://configured"
    assert collectors[0].kwargs["sink"] is stores[0]
    assert collectors[0].kwargs["storage_backend"] == "postgresql"
    assert collectors[0].kwargs["shadow"] is True
    assert payload["storage_backend"] == "postgresql"


def test_memory_storage_remains_explicit_even_when_postgresql_is_configured(monkeypatch) -> None:
    memory_store = _Store("memory")
    monkeypatch.setenv("QUANTPILOT_POSTGRES_DSN", "postgresql://configured")
    monkeypatch.setattr(runner, "InMemoryReportingStore", lambda: memory_store)

    store, backend = runner._store("memory")

    assert store is memory_store
    assert store.initialized is True
    assert backend == "memory"


def test_auto_falls_back_to_memory_without_postgresql_configuration(monkeypatch) -> None:
    memory_store = _Store("memory")
    monkeypatch.delenv("QUANTPILOT_POSTGRES_DSN", raising=False)
    monkeypatch.setattr(runner, "InMemoryReportingStore", lambda: memory_store)

    store, backend = runner._store("auto")

    assert store is memory_store
    assert backend == "memory"


def test_explicit_postgresql_fails_clearly_without_configuration(monkeypatch) -> None:
    monkeypatch.delenv("QUANTPILOT_POSTGRES_DSN", raising=False)
    with pytest.raises(RuntimeError, match="QUANTPILOT_POSTGRES_DSN"):
        runner._store("postgresql")
