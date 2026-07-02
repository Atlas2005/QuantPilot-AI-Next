from __future__ import annotations

from pathlib import Path

import pytest


LEGACY_ENGINE_TEST_DIRS = {
    "daily_paper_trading_loop_tradability_metrics",
    "executable_candidate_paper_bridge",
    "gate_pruning_tradability_fill_loop",
    "mixed_stock_etf_daily_paper_evaluation",
    "multi_day_paper_replay",
    "paper_ledger_dry_run",
    "qlib_offline_tradability_evaluation_fixture",
    "real_provider_mixed_etf_paper_replay",
}


@pytest.fixture(autouse=True)
def enable_legacy_engine_for_reference_tests(monkeypatch: pytest.MonkeyPatch, request) -> None:
    """Keep legacy reference tests explicit while runtime defaults remain off."""

    path_parts = Path(str(request.node.fspath)).parts
    if any(part in LEGACY_ENGINE_TEST_DIRS for part in path_parts):
        monkeypatch.setenv("USE_LEGACY_ENGINE", "true")
