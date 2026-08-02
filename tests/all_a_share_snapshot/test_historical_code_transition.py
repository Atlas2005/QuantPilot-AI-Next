"""PIT and resume regressions for authoritative exchange-code transitions."""

from __future__ import annotations

from pathlib import Path

from quantpilot_core.all_a_share_snapshot.contracts import SnapshotConfig
from quantpilot_core.all_a_share_snapshot.snapshot import (
    SnapshotLoader,
    build_snapshot,
    validate_snapshot,
)


OLD_CODE = "300111.SZ"
NEW_CODE = "302222.SZ"
EFFECTIVE_DATE = "20250217"
SESSIONS = ("20250213", "20250214", EFFECTIVE_DATE, "20250218")


class TransitionProvider:
    provider_name = "tushare"

    def __init__(self, *, authoritative_transition: bool = True) -> None:
        self.authoritative_transition = authoritative_transition
        self.calls: list[tuple[object, ...]] = []

    def fetch_stock_basic(self, statuses):
        self.calls.append(("stock_basic", tuple(statuses)))
        return [
            {
                "ts_code": "600000.SH", "symbol": "600000", "name": "BASE",
                "market": "Main", "exchange": "SSE", "list_status": "L",
                "list_date": "20000101", "delist_date": "",
            },
            {
                "ts_code": NEW_CODE, "symbol": "302222", "name": "NEW NAME",
                "market": "Main", "exchange": "SZSE", "list_status": "L",
                "list_date": EFFECTIVE_DATE, "delist_date": "",
            },
        ]

    def fetch_trade_cal(self, start, end):
        self.calls.append(("trade_cal", start, end))
        return [
            {"exchange": "SSE", "cal_date": day, "is_open": 1}
            for day in SESSIONS
        ]

    def fetch_daily_by_trade_date(self, day):
        self.calls.append(("daily", day))
        transition_code = OLD_CODE if day < EFFECTIVE_DATE else NEW_CODE
        return [self._bar("600000.SH", day), self._bar(transition_code, day)]

    def fetch_adj_factor_by_trade_date(self, day):
        self.calls.append(("adj_factor", day))
        transition_code = OLD_CODE if day < EFFECTIVE_DATE else NEW_CODE
        return [
            {"ts_code": "600000.SH", "trade_date": day, "adj_factor": 1.0},
            {"ts_code": transition_code, "trade_date": day, "adj_factor": 1.0},
        ]

    def fetch_index_daily(self, symbol, start, end):
        self.calls.append(("index_daily", symbol, start, end))
        return [self._bar(symbol, day) for day in SESSIONS]

    def fetch_optional(self, dataset, trade_date=None):
        self.calls.append((dataset, trade_date))
        transition_code = OLD_CODE if trade_date < EFFECTIVE_DATE else NEW_CODE
        if dataset == "daily_basic":
            return [
                self._daily_basic("600000.SH", trade_date),
                self._daily_basic(transition_code, trade_date),
            ]
        if dataset == "limits":
            return [
                {"ts_code": code, "trade_date": trade_date, "up_limit": 11.0, "down_limit": 9.0}
                for code in ("600000.SH", transition_code)
            ]
        return []

    def fetch_namechange_by_ts_code(self, code):
        self.calls.append(("namechange", code))
        if code != OLD_CODE:
            return []
        if not self.authoritative_transition:
            return [self._namechange(code, "OLD NAME", "20100101", "20250214")]
        return [
            self._namechange(code, "OLD NAME", "20100101", "20250214"),
            self._namechange(code, "NEW NAME", EFFECTIVE_DATE, None),
        ]

    @staticmethod
    def _bar(code, day):
        return {
            "ts_code": code, "trade_date": day, "open": 10.0, "high": 11.0,
            "low": 9.0, "close": 10.0, "pre_close": 10.0, "change": 0.0,
            "pct_chg": 0.0, "vol": 100.0, "amount": 1_000.0,
        }

    @staticmethod
    def _daily_basic(code, day):
        return {
            "ts_code": code, "trade_date": day, "close": 10.0,
            "turnover_rate": 1.0, "pe": 2.0, "pb": 1.0, "total_mv": 3.0,
        }

    @staticmethod
    def _namechange(code, name, start, end):
        return {
            "ts_code": code, "name": name, "start_date": start,
            "end_date": end, "ann_date": start, "change_reason": "security code transition",
        }


def _config(root: Path) -> SnapshotConfig:
    return SnapshotConfig(
        root=str(root), start_date=SESSIONS[0], end_date=SESSIONS[-1],
        test_only=True, namechange_shard_size=1,
    )


def test_transition_preserves_exchange_codes_pit_identity_and_provenance(tmp_path: Path) -> None:
    manifest = build_snapshot(_config(tmp_path), TransitionProvider())
    loader = SnapshotLoader(tmp_path)
    resolution = manifest["historical_code_resolutions"][OLD_CODE]

    assert manifest["status"] == "completed" and validate_snapshot(tmp_path).ok
    assert {row["ts_code"] for row in loader.daily("20250214")} == {"600000.SH", OLD_CODE}
    assert {row["ts_code"] for row in loader.daily(EFFECTIVE_DATE)} == {"600000.SH", NEW_CODE}
    assert {row["ts_code"] for row in loader.listed_universe("20250214")} == {"600000.SH", OLD_CODE}
    assert {row["ts_code"] for row in loader.listed_universe(EFFECTIVE_DATE)} == {"600000.SH", NEW_CODE}
    historical_row = next(row for row in loader.listed_universe("20250214") if row["ts_code"] == OLD_CODE)
    assert historical_row["name"] == "OLD NAME" and NEW_CODE not in historical_row.values()
    assert loader.stable_instrument_identity(OLD_CODE) == loader.stable_instrument_identity(NEW_CODE)
    identities = {
        loader.stable_instrument_identity(row["ts_code"])
        for row in loader.listed_universe("20250214")
    }
    assert len(identities) == 2
    assert resolution["historical_code"] == OLD_CODE
    assert resolution["successor_code"] == NEW_CODE
    assert resolution["effective_date"] == EFFECTIVE_DATE
    assert resolution["evidence_source_type"] == "tushare_stock_basic_and_namechange"
    assert resolution["resolution_method"] == "unique_exchange_namechange_effective_date_stock_basic_match"
    assert resolution["affected_datasets"] == ["adj_factor", "daily", "daily_basic", "limits"]
    assert resolution["affected_date_range"] == {"start": "20250213", "end": "20250214"}


def test_unresolved_transition_still_fails_and_resume_refetches_only_affected_dates(tmp_path: Path) -> None:
    first = build_snapshot(
        _config(tmp_path), TransitionProvider(authoritative_transition=False),
    )

    assert first["status"] == "incomplete"
    assert first["historical_code_resolutions"][OLD_CODE]["resolution_status"] == "unresolved_ambiguous_or_no_match"
    assert {item["trade_date"] for item in first["failed_partitions"] if item["dataset"] == "daily"} == {"20250213", "20250214"}

    resumed_provider = TransitionProvider(authoritative_transition=True)
    resumed = build_snapshot(_config(tmp_path), resumed_provider)

    assert resumed["status"] == "completed" and not resumed["failed_partitions"]
    assert validate_snapshot(tmp_path).ok
    assert [call for call in resumed_provider.calls if call[0] == "daily"] == [
        ("daily", "20250213"), ("daily", "20250214"),
    ]
    assert [call for call in resumed_provider.calls if call[0] == "adj_factor"] == [
        ("adj_factor", "20250213"), ("adj_factor", "20250214"),
    ]
    assert not [
        call for call in resumed_provider.calls
        if call[0] in {"daily", "adj_factor"} and call[1] >= EFFECTIVE_DATE
    ]
    assert not [call for call in resumed_provider.calls if call[0] in {"stock_basic", "trade_cal", "index_daily"}]
    assert not [
        call for call in resumed_provider.calls
        if call[0] in {"daily_basic", "suspend", "limits"} and call[1] >= EFFECTIVE_DATE
    ]
    assert resumed["resume_count"] > 0
    assert {row["ts_code"] for row in SnapshotLoader(tmp_path).daily("20250214")} >= {OLD_CODE}
