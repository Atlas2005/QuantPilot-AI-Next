"""PIT, propagation, and resume regressions for duplicate code aliases."""

from __future__ import annotations

from pathlib import Path

from quantpilot_core.all_a_share_snapshot.contracts import SnapshotConfig
from quantpilot_core.all_a_share_snapshot.snapshot import (
    ECONOMIC_FIELDS,
    HISTORICAL_CODE_RESOLUTION_SOURCE,
    SnapshotLoader,
    build_snapshot,
    validate_snapshot,
)


OLD_CODE = "300111.SZ"
NEW_CODE = "302222.SZ"
SECOND_NEW_CODE = "302223.SZ"
UNKNOWN_CODE = "399999.SZ"
EFFECTIVE_DATE = "20250217"
SESSIONS = ("20250213", "20250214", EFFECTIVE_DATE, "20250218")


class TransitionProvider:
    provider_name = "tushare"

    def __init__(self, *, timeline_complete: bool = True, economic_mismatch: bool = False,
                 ambiguous: bool = False, unknown_only: bool = False) -> None:
        self.timeline_complete = timeline_complete
        self.economic_mismatch = economic_mismatch
        self.ambiguous = ambiguous
        self.unknown_only = unknown_only
        self.calls: list[tuple[object, ...]] = []

    def fetch_stock_basic(self, statuses):
        self.calls.append(("stock_basic", tuple(statuses)))
        rows = [
            self._stock("600000.SH", "600000", "BASE", "SSE", "20000101"),
            self._stock(NEW_CODE, "302222", "NEW NAME", "SZSE", "20100101"),
        ]
        if self.ambiguous:
            rows.append(self._stock(SECOND_NEW_CODE, "302223", "SECOND NEW NAME", "SZSE", "20100101"))
        return rows

    def fetch_trade_cal(self, start, end):
        self.calls.append(("trade_cal", start, end))
        return [{"exchange": "SSE", "cal_date": day, "is_open": 1} for day in SESSIONS]

    def fetch_daily_by_trade_date(self, day):
        self.calls.append(("daily", day))
        rows = [self._bar("600000.SH", day)]
        if self.unknown_only:
            return rows + [self._bar(UNKNOWN_CODE, day)]
        if day < EFFECTIVE_DATE:
            rows.extend((self._bar(OLD_CODE, day), self._bar(NEW_CODE, day)))
            if self.economic_mismatch:
                rows[-1]["close"] = 10.5
            if self.ambiguous:
                rows.append(self._bar(SECOND_NEW_CODE, day))
        else:
            rows.append(self._bar(NEW_CODE, day))
        return rows

    def fetch_adj_factor_by_trade_date(self, day):
        self.calls.append(("adj_factor", day))
        rows = [{"ts_code": "600000.SH", "trade_date": day, "adj_factor": 1.0}]
        if self.unknown_only:
            return rows
        codes = (OLD_CODE, NEW_CODE) if day < EFFECTIVE_DATE else (NEW_CODE,)
        rows.extend({"ts_code": code, "trade_date": day, "adj_factor": 1.0} for code in codes)
        return rows

    def fetch_index_daily(self, symbol, start, end):
        self.calls.append(("index_daily", symbol, start, end))
        return [self._bar(symbol, day) for day in SESSIONS]

    def fetch_optional(self, dataset, trade_date=None):
        self.calls.append((dataset, trade_date))
        if self.unknown_only:
            return self._base_optional(dataset, trade_date)
        # Suspend deliberately supplies only the successor alias.  This proves
        # a resolved identity propagates without requiring both rows in every
        # companion endpoint.
        if dataset == "suspend":
            return [
                {"ts_code": NEW_CODE, "trade_date": trade_date,
                 "suspend_timing": "09:30-10:00", "suspend_type": "S"},
            ]
        codes = (OLD_CODE, NEW_CODE) if trade_date < EFFECTIVE_DATE else (NEW_CODE,)
        rows = self._base_optional(dataset, trade_date)
        if dataset == "daily_basic":
            rows.extend(self._daily_basic(code, trade_date) for code in codes)
        elif dataset == "limits":
            rows.extend(
                {"ts_code": code, "trade_date": trade_date,
                 "up_limit": 11.0, "down_limit": 9.0}
                for code in codes
            )
        return rows

    def fetch_namechange_by_ts_code(self, code):
        self.calls.append(("namechange", code))
        if code == OLD_CODE:
            return []
        if code not in {NEW_CODE, SECOND_NEW_CODE}:
            return []
        current_name = "NEW NAME" if code == NEW_CODE else "SECOND NEW NAME"
        periods = [self._namechange(code, "OLD NAME", "20100101", "20250216")]
        if self.timeline_complete:
            periods.append(self._namechange(code, current_name, EFFECTIVE_DATE, None))
        return periods

    @staticmethod
    def _stock(code, symbol, name, exchange, list_date):
        return {
            "ts_code": code, "symbol": symbol, "name": name,
            "market": "Main", "exchange": exchange, "list_status": "L",
            "list_date": list_date, "delist_date": "",
        }

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
    def _base_optional(dataset, day):
        if dataset == "daily_basic":
            return [TransitionProvider._daily_basic("600000.SH", day)]
        if dataset == "limits":
            return [{"ts_code": "600000.SH", "trade_date": day,
                     "up_limit": 11.0, "down_limit": 9.0}]
        return []

    @staticmethod
    def _namechange(code, name, start, end):
        return {
            "ts_code": code, "name": name, "start_date": start,
            "end_date": end, "ann_date": start,
            "change_reason": "security code transition",
        }


def _config(root: Path) -> SnapshotConfig:
    return SnapshotConfig(
        root=str(root), start_date=SESSIONS[0], end_date=SESSIONS[-1],
        test_only=True, namechange_shard_size=1,
    )


def _codes(loader: SnapshotLoader, dataset: str, day: str) -> set[str]:
    rows = loader.optional(dataset, day) if dataset in {"daily_basic", "suspend", "limits"} else getattr(loader, dataset)(day)
    return {str(row["ts_code"]) for row in rows}


def test_duplicate_alias_resolution_preserves_pit_codes_and_provenance(tmp_path: Path) -> None:
    provider = TransitionProvider()
    manifest = build_snapshot(_config(tmp_path), provider)
    loader = SnapshotLoader(tmp_path)
    resolution = manifest["historical_code_resolutions"][OLD_CODE]

    assert manifest["status"] == "completed" and validate_snapshot(tmp_path).ok
    assert not [call for call in provider.calls if call == ("namechange", OLD_CODE)]
    assert [call for call in provider.calls if call == ("namechange", NEW_CODE)]
    for day in SESSIONS[:2]:
        assert _codes(loader, "daily", day) == {"600000.SH", OLD_CODE}
        assert _codes(loader, "adj_factor", day) == {"600000.SH", OLD_CODE}
        assert _codes(loader, "daily_basic", day) == {"600000.SH", OLD_CODE}
        assert _codes(loader, "limits", day) == {"600000.SH", OLD_CODE}
        assert _codes(loader, "suspend", day) == {OLD_CODE}
        assert {row["ts_code"] for row in loader.listed_universe(day)} == {"600000.SH", OLD_CODE}
    for day in SESSIONS[2:]:
        assert _codes(loader, "daily", day) == {"600000.SH", NEW_CODE}
        assert {row["ts_code"] for row in loader.listed_universe(day)} == {"600000.SH", NEW_CODE}

    historical_row = next(row for row in loader.listed_universe(SESSIONS[1]) if row["ts_code"] == OLD_CODE)
    assert historical_row["name"] == "OLD NAME"
    assert loader.stable_instrument_identity(OLD_CODE) == loader.stable_instrument_identity(NEW_CODE)
    assert len({loader.stable_instrument_identity(row["ts_code"]) for row in loader.listed_universe(SESSIONS[1])}) == 2
    assert resolution["historical_code"] == OLD_CODE
    assert resolution["successor_code"] == NEW_CODE
    assert resolution["effective_date"] == EFFECTIVE_DATE
    assert resolution["stable_instrument_identity"] == resolution["stable_instrument_id"]
    assert resolution["source"] == HISTORICAL_CODE_RESOLUTION_SOURCE
    assert resolution["evidence_source_type"] == HISTORICAL_CODE_RESOLUTION_SOURCE
    assert resolution["resolution_method"] == "unique_same_exchange_duplicate_economic_payload_and_successor_namechange_v1"
    assert resolution["compared_canonical_fields_by_dataset"]["daily"] == list(ECONOMIC_FIELDS["daily"])
    assert resolution["issuer_origin_evidence"]["stock_basic_list_date"] == "20100101"
    assert resolution["observed_duplicate_date_range"] == {"start": SESSIONS[0], "end": SESSIONS[1]}
    assert resolution["affected_datasets"] == ["adj_factor", "daily", "daily_basic", "limits", "suspend"]
    assert resolution["affected_date_range"] == {"start": SESSIONS[0], "end": SESSIONS[-1]}
    assert resolution["suppressed_duplicate_alias_row_count"] == 8
    assert resolution["normalized_alias_row_count"] == 2


def test_nonidentical_duplicate_does_not_resolve(tmp_path: Path) -> None:
    provider = TransitionProvider(economic_mismatch=True)
    manifest = build_snapshot(_config(tmp_path), provider)
    resolution = manifest["historical_code_resolutions"][OLD_CODE]

    assert manifest["status"] == "incomplete"
    assert resolution["resolution_status"] == "unresolved_ambiguous_or_no_match"
    assert resolution["candidate_count"] == 0
    assert not [call for call in provider.calls if call[0] == "namechange" and call[1] == OLD_CODE]


def test_multiple_identical_successors_remain_ambiguous(tmp_path: Path) -> None:
    manifest = build_snapshot(_config(tmp_path), TransitionProvider(ambiguous=True))
    resolution = manifest["historical_code_resolutions"][OLD_CODE]

    assert manifest["status"] == "incomplete"
    assert resolution["resolution_status"] == "unresolved_ambiguous_or_no_match"
    assert resolution["candidate_count"] == 2
    assert resolution["candidate_codes"] == [NEW_CODE, SECOND_NEW_CODE]


def test_unknown_without_duplicate_evidence_remains_required_failure(tmp_path: Path) -> None:
    provider = TransitionProvider(unknown_only=True)
    manifest = build_snapshot(_config(tmp_path), provider)
    resolution = manifest["historical_code_resolutions"][UNKNOWN_CODE]

    assert manifest["status"] == "incomplete"
    assert resolution["candidate_count"] == 0
    assert manifest["unexplained_symbols"]["daily"]["examples"] == [UNKNOWN_CODE]
    assert not [call for call in provider.calls if call[0] == "namechange" and call[1] == UNKNOWN_CODE]


def test_resume_rebuilds_only_failed_transition_dates_and_clears_stale_failure(tmp_path: Path) -> None:
    first = build_snapshot(_config(tmp_path), TransitionProvider(timeline_complete=False))
    first_loader = SnapshotLoader(tmp_path)

    assert first["status"] == "incomplete"
    assert {item["trade_date"] for item in first["failed_partitions"] if item["dataset"] == "daily"} == set(SESSIONS[:2])
    assert NEW_CODE in _codes(first_loader, "daily", SESSIONS[1])
    assert OLD_CODE not in _codes(first_loader, "daily", SESSIONS[1])

    provider = TransitionProvider()
    resumed = build_snapshot(_config(tmp_path), provider)
    loader = SnapshotLoader(tmp_path)

    assert resumed["status"] == "completed" and not resumed["failed_partitions"]
    assert validate_snapshot(tmp_path).ok
    assert [call for call in provider.calls if call[0] == "daily"] == [
        ("daily", SESSIONS[0]), ("daily", SESSIONS[1]),
    ]
    assert [call for call in provider.calls if call[0] == "adj_factor"] == [
        ("adj_factor", SESSIONS[0]), ("adj_factor", SESSIONS[1]),
    ]
    assert not [
        call for call in provider.calls
        if call[0] in {"daily", "adj_factor", "daily_basic", "suspend", "limits"}
        and call[1] >= EFFECTIVE_DATE
    ]
    assert not [call for call in provider.calls if call[0] in {"stock_basic", "trade_cal", "index_daily"}]
    assert resumed["resume_count"] > 0
    assert _codes(loader, "daily", SESSIONS[1]) == {"600000.SH", OLD_CODE}


def test_production_resolution_source_has_no_verified_security_literals() -> None:
    production = "\n".join(
        Path(path).read_text(encoding="utf-8")
        for path in (
            "src/quantpilot_core/all_a_share_snapshot/snapshot.py",
            "src/quantpilot_core/all_a_share_snapshot/pit.py",
            "src/quantpilot_core/all_a_share_snapshot/provider.py",
        )
    )
    for literal in ("300114", "302132", "中航电测", "中航成飞"):
        assert literal not in production
