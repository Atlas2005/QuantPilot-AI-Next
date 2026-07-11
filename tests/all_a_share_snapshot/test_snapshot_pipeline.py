from __future__ import annotations
import importlib.util
from pathlib import Path
import json
import shutil
import pytest

from quantpilot_core.all_a_share_snapshot.contracts import SnapshotConfig
from quantpilot_core.all_a_share_snapshot.snapshot import (
    ProviderCallError, SnapshotLoader, _CallPacer, _failure, _fetch,
    build_snapshot, validate_snapshot,
)

class FakeProvider:
    provider_name="tushare"
    def __init__(self, *, fail_daily=False, optional_permission=False, namechange_rows=None): self.calls=[]; self.fail_daily=fail_daily; self.optional_permission=optional_permission; self.namechange_rows=namechange_rows or {}
    def fetch_stock_basic(self,statuses):
        self.calls.append(("stock_basic",tuple(statuses))); return [
          {"ts_code":"600000.SH","symbol":"600000","name":"SSE","market":"Main","exchange":"SSE","list_status":"L","list_date":"20200101","delist_date":""},
          {"ts_code":"000001.SZ","symbol":"000001","name":"SZSE","market":"Main","exchange":"SZSE","list_status":"L","list_date":"20231010","delist_date":""},
          {"ts_code":"430001.BJ","symbol":"430001","name":"BSE","market":"BSE","exchange":"BSE","list_status":"D","list_date":"20200101","delist_date":"20231010"},]
    def fetch_trade_cal(self,start,end): self.calls.append(("trade_cal",start,end)); return [{"exchange":"SSE","cal_date":"20231009","is_open":1},{"exchange":"SSE","cal_date":"20231010","is_open":1},{"exchange":"SSE","cal_date":"20231011","is_open":0}]
    def fetch_daily_by_trade_date(self,d):
        self.calls.append(("daily",d))
        if self.fail_daily: raise RuntimeError("transient exhausted")
        return [self._bar("600000.SH",d)]
    def fetch_adj_factor_by_trade_date(self,d): self.calls.append(("adj_factor",d)); return [{"ts_code":"600000.SH","trade_date":d,"adj_factor":1.0}]
    def fetch_index_daily(self,s,start,end): self.calls.append(("index_daily",s,start,end)); return [self._bar(s,"20231009"),self._bar(s,"20231010")]
    def fetch_optional(self,dataset,trade_date=None):
        self.calls.append((dataset,trade_date))
        if self.optional_permission and dataset == "limits": raise PermissionError("no permission")
        if dataset == "daily_basic": return [{"ts_code":"600000.SH","trade_date":trade_date,"close":10,"turnover_rate":1,"pe":2,"pb":1,"total_mv":3}]
        if dataset == "suspend": return [{"ts_code":"600000.SH","trade_date":trade_date,"suspend_timing":"09:30-10:00","suspend_type":"S"}]
        return [{"ts_code":"600000.SH","trade_date":trade_date,"up_limit":11,"down_limit":9}]
    def fetch_namechange_by_ts_code(self, ts_code):
        self.calls.append(("namechange",ts_code)); return self.namechange_rows.get(ts_code, [])
    @staticmethod
    def _bar(code,d): return {"ts_code":code,"trade_date":d,"open":10,"high":11,"low":9,"close":10,"pre_close":10,"change":0,"pct_chg":0,"vol":100,"amount":1000}

def build(tmp_path: Path, provider: FakeProvider | None=None):
    p=provider or FakeProvider(); return build_snapshot(SnapshotConfig(root=str(tmp_path),start_date="20231009",end_date="20231010",test_only=True),p),p

def test_full_universe_pit_and_daily_trade_date_partitions(tmp_path: Path):
    manifest,p=build(tmp_path); loader=SnapshotLoader(tmp_path)
    assert set(x["ts_code"] for x in loader.stock_master()) == {"600000.SH","000001.SZ","430001.BJ"}
    assert {x["ts_code"] for x in loader.listed_universe("20231009")} == {"600000.SH","430001.BJ"}
    assert {x["ts_code"] for x in loader.listed_universe("20231010")} == {"600000.SH","000001.SZ","430001.BJ"}
    assert "430001.BJ" not in {x["ts_code"] for x in loader.listed_universe("20231011")}
    assert [x for x in p.calls if x[0]=="daily"] == [("daily","20231009"),("daily","20231010")]
    assert manifest["status"]=="completed" and manifest["fallback_used"] is False

def test_digest_is_timestamp_independent_and_resume_skips_valid_partitions(tmp_path: Path):
    first,p=build(tmp_path); second,p2=build(tmp_path)
    assert first["digest"] == second["digest"]
    assert all(not Path(partition["path"]).is_absolute() and str(tmp_path) not in partition["path"] for partition in first["partitions"])
    assert not [x for x in p2.calls if x[0] in {"daily","adj_factor"}]
    assert second["resume_count"] > 0

def test_relative_partition_paths_are_portable_and_unsafe_paths_are_rejected(tmp_path: Path):
    source=tmp_path / "source"; manifest,_=build(source)
    assert all(not Path(entry["path"]).is_absolute() and ".." not in Path(entry["path"]).parts for entry in manifest["partitions"])
    copied=tmp_path / "copied"; shutil.copytree(source,copied)
    (source / manifest["partitions"][0]["path"]).write_bytes(b"corrupt original")
    assert validate_snapshot(copied).ok
    from quantpilot_core.all_a_share_snapshot.storage import digest
    for value in (str(source / "stock_basic/part-00000.parquet"), "../outside.parquet"):
        raw=json.loads((copied/"manifest.json").read_text()); raw["partitions"][0]["path"]=value; raw["digest"]=digest(raw)
        (copied/"manifest.json").write_text(json.dumps(raw))
        assert any("unsafe partition path" in error for error in validate_snapshot(copied).errors)

def test_unsafe_calendar_paths_return_failed_validation_without_raising(tmp_path: Path):
    manifest,_=build(tmp_path); calendar=next(index for index, entry in enumerate(manifest["partitions"]) if entry["dataset"] == "calendar")
    from quantpilot_core.all_a_share_snapshot.storage import digest
    for value in (str(tmp_path / "calendar/part-00000.parquet"), "../calendar/part-00000.parquet"):
        raw=json.loads((tmp_path/"manifest.json").read_text()); raw["partitions"][calendar]["path"] = value; raw["digest"] = digest(raw)
        (tmp_path/"manifest.json").write_text(json.dumps(raw))
        result=validate_snapshot(tmp_path)
        assert not result.ok and any("unsafe calendar partition path" in error for error in result.errors)

def test_corrupt_partition_rewrites_and_validator_detects_hash_and_schema(tmp_path: Path):
    manifest,p=build(tmp_path); entry=next(x for x in manifest["partitions"] if x["dataset"]=="daily" and x["trade_date"]=="20231009")
    path=tmp_path/entry["path"]; path.write_bytes(b"broken")
    bad=validate_snapshot(tmp_path); assert not bad.ok and any("hash mismatch" in x or "unreadable" in x for x in bad.errors)
    _,p2=build(tmp_path); assert ("daily","20231009") in p2.calls; assert validate_snapshot(tmp_path).ok

def test_required_failure_is_explicit_incomplete(tmp_path: Path):
    manifest,_=build(tmp_path,FakeProvider(fail_daily=True)); assert manifest["status"]=="incomplete"; assert manifest["failed_partitions"]

def test_optional_permission_failure_is_manifest_capability(tmp_path: Path):
    manifest,_=build(tmp_path,FakeProvider(optional_permission=True)); assert manifest["status"]=="completed"; assert manifest["capabilities"]["limits"]=="unavailable"

def test_missing_official_session_and_manifest_tamper_are_detected(tmp_path: Path):
    manifest,_=build(tmp_path); raw=json.loads((tmp_path/"manifest.json").read_text()); raw["partitions"]=[x for x in raw["partitions"] if not (x["dataset"]=="daily" and x["trade_date"]=="20231010")]
    (tmp_path/"manifest.json").write_text(json.dumps(raw)); result=validate_snapshot(tmp_path)
    assert any("manifest digest mismatch" in x for x in result.errors) and any("missing required official daily session" in x for x in result.errors)

def test_loader_reads_one_partition_without_directory_scan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    build(tmp_path); loader=SnapshotLoader(tmp_path)
    import quantpilot_core.all_a_share_snapshot.snapshot as module
    calls=[]; original=module.read_table
    def tracked(path): calls.append(Path(path)); return original(path)
    monkeypatch.setattr(module,"read_table",tracked); assert loader.daily("20231009")[0]["trade_date"]=="20231009"
    assert len(calls)==1 and "trade_date=20231009" in str(calls[0])

def test_artifact_policy_and_no_token_or_fallback_source(tmp_path: Path):
    build(tmp_path); assert ".cache/" in Path(".gitignore").read_text()
    source=Path("src/quantpilot_core/all_a_share_snapshot/snapshot.py").read_text()
    assert "baostock" not in source.lower() and "akshare" not in source.lower() and "TUSHARE_TOKEN" not in source

def test_suspend_daily_events_keep_actual_fields_and_are_not_repeated(tmp_path: Path):
    manifest,_=build(tmp_path); loader=SnapshotLoader(tmp_path)
    rows=loader.optional("suspend","20231009")
    assert rows == ({"ts_code":"600000.SH","trade_date":"20231009","suspend_timing":"09:30-10:00","suspend_type":"S"},)
    assert all(row["trade_date"] == day for day in ("20231009","20231010") for row in loader.optional("suspend",day))
    assert manifest["capabilities"]["suspend"] == "available"

def test_namechange_is_per_symbol_deduplicated_and_open_end_is_valid(tmp_path: Path):
    row={"ts_code":"600000.SH","name":"SSE","start_date":"20200101","end_date":None,"ann_date":"20200101","change_reason":"rename"}
    manifest,p=build(tmp_path,FakeProvider(namechange_rows={"600000.SH":[row,row]}))
    assert manifest["namechange"]["complete"] and len(SnapshotLoader(tmp_path).optional("namechange")) == 1
    assert {call[1] for call in p.calls if call[0] == "namechange"} == {"600000.SH","000001.SZ","430001.BJ"}
    assert validate_snapshot(tmp_path).ok

def test_namechange_cap_is_incomplete_not_canonical(tmp_path: Path):
    cap_rows=[{"ts_code":"600000.SH","name":"N","start_date":"20200101","end_date":None,"ann_date":"20200101","change_reason":"x"}] * 10000
    manifest,_=build(tmp_path,FakeProvider(namechange_rows={"600000.SH":cap_rows}))
    assert manifest["status"] == "completed" and manifest["capabilities"]["namechange"] == "unavailable"

def test_optional_etf_and_unknown_rows_are_audited_without_contaminating_equity(tmp_path: Path):
    class Mixed(FakeProvider):
        def fetch_optional(self,dataset,trade_date=None):
            rows=super().fetch_optional(dataset,trade_date)
            return rows + ([{"ts_code":"510300.SH","trade_date":trade_date,"up_limit":4,"down_limit":3}] if dataset == "limits" else []) + ([{"ts_code":"not-a-code","trade_date":trade_date,"up_limit":4,"down_limit":3}] if dataset == "limits" else [])
    manifest,_=build(tmp_path,Mixed())
    assert manifest["instrument_audit"]["limits"]["etf"] == 2 and manifest["instrument_audit"]["limits"]["unknown"] == 2
    assert {row["ts_code"] for row in SnapshotLoader(tmp_path).optional("limits","20231009")} == {"600000.SH"}
    assert validate_snapshot(tmp_path).ok

def test_daily_absent_stock_master_is_blocking_and_records_code(tmp_path: Path):
    class Missing(FakeProvider):
        def fetch_daily_by_trade_date(self,d): return [self._bar("600000.SH",d), self._bar("999999.SZ",d)]
    manifest,_=build(tmp_path,Missing())
    assert manifest["status"] == "incomplete"
    assert manifest["unexplained_symbols"]["daily"] == {"count":2,"examples":["999999.SZ"]}
    assert "required daily symbols absent from stock_basic" in validate_snapshot(tmp_path).errors

def test_unique_historical_alias_preserves_raw_daily_and_adj_factor_codes(tmp_path: Path):
    class Alias(FakeProvider):
        def fetch_stock_basic(self,statuses):
            return super().fetch_stock_basic(statuses) + [{"ts_code":"302132.SZ","symbol":"302132","name":"中航成飞","market":"Main","exchange":"SZSE","list_status":"L","list_date":"20100827","delist_date":""}]
        def fetch_daily_by_trade_date(self,d): return [self._bar("600000.SH",d), self._bar("300114.SZ",d)]
        def fetch_adj_factor_by_trade_date(self,d): return [{"ts_code":"600000.SH","trade_date":d,"adj_factor":1.0},{"ts_code":"300114.SZ","trade_date":d,"adj_factor":1.0}]
        def fetch_optional(self,dataset,trade_date=None):
            rows=super().fetch_optional(dataset,trade_date)
            if dataset == "daily_basic": rows.append({"ts_code":"300114.SZ","trade_date":trade_date,"close":10,"turnover_rate":1,"pe":2,"pb":1,"total_mv":3})
            if dataset == "limits": rows.append({"ts_code":"300114.SZ","trade_date":trade_date,"up_limit":11,"down_limit":9})
            return rows
        def fetch_namechange_by_ts_code(self,code):
            if code == "300114.SZ":
                self.calls.append(("namechange",code)); return [{"ts_code":code,"name":"中航电测","start_date":"20100827","end_date":"20230201","ann_date":"20100827","change_reason":"x"},{"ts_code":code,"name":"中航成飞","start_date":"20230202","end_date":None,"ann_date":"20230202","change_reason":"x"}]
            return super().fetch_namechange_by_ts_code(code)
    manifest,p=build(tmp_path,Alias()); loader=SnapshotLoader(tmp_path)
    resolution=manifest["historical_code_resolutions"]["300114.SZ"]
    assert manifest["status"] == "completed" and resolution["current_ts_code"] == "302132.SZ" and resolution["resolution_status"] == "resolved"
    assert "300114.SZ" in {row["ts_code"] for row in loader.daily("20231009")} and "300114.SZ" in {row["ts_code"] for row in loader.adj_factor("20231009")}
    assert len([call for call in p.calls if call == ("namechange","300114.SZ")]) == 1 and validate_snapshot(tmp_path).ok
    assert manifest["historical_code_resolution_calls"] == 1
    resumed=Alias(); rebuilt=build_snapshot(SnapshotConfig(root=str(tmp_path),start_date="20231009",end_date="20231010",test_only=True),resumed)
    assert rebuilt["historical_code_resolution_calls"] == 0
    assert not [call for call in resumed.calls if call == ("namechange","300114.SZ")]
    assert rebuilt["historical_code_resolutions"] == manifest["historical_code_resolutions"]
    assert rebuilt["digest"] == manifest["digest"] and validate_snapshot(tmp_path).ok

def test_ambiguous_or_name_only_historical_alias_is_blocking(tmp_path: Path):
    class Ambiguous(FakeProvider):
        def fetch_stock_basic(self,statuses):
            return super().fetch_stock_basic(statuses) + [
                {"ts_code":"302132.SZ","symbol":"302132","name":"OLD","market":"Main","exchange":"SZSE","list_status":"L","list_date":"20100827","delist_date":""},
                {"ts_code":"302133.SZ","symbol":"302133","name":"OLD","market":"Main","exchange":"SZSE","list_status":"L","list_date":"20100827","delist_date":""}]
        def fetch_daily_by_trade_date(self,d): return [self._bar("600000.SH",d), self._bar("300114.SZ",d)]
        def fetch_namechange_by_ts_code(self,code):
            if code == "300114.SZ": return [{"ts_code":code,"name":"OLD","start_date":"20100827","end_date":None,"ann_date":"20100827","change_reason":"x"}]
            return super().fetch_namechange_by_ts_code(code)
    manifest,_=build(tmp_path,Ambiguous())
    assert manifest["status"] == "incomplete" and manifest["historical_code_resolutions"]["300114.SZ"]["candidate_count"] == 2

def test_etf_daily_code_is_never_resolved_as_historical_alias(tmp_path: Path):
    class EtfDaily(FakeProvider):
        def fetch_daily_by_trade_date(self,d): return [self._bar("600000.SH",d), self._bar("510300.SH",d)]
    manifest,p=build(tmp_path,EtfDaily())
    assert manifest["status"] == "incomplete" and manifest["historical_code_resolutions"]["510300.SH"]["resolution_status"] == "unresolved_external_instrument"
    assert not [call for call in p.calls if call == ("namechange","510300.SH")]

def test_daily_pit_filter_excludes_future_listing_and_delists_after_last_day(tmp_path: Path):
    class PitRows(FakeProvider):
        def fetch_daily_by_trade_date(self,d):
            return [self._bar("600000.SH",d), self._bar("000001.SZ",d), self._bar("430001.BJ",d)]
        def fetch_adj_factor_by_trade_date(self,d):
            return [{"ts_code":code,"trade_date":d,"adj_factor":1.0} for code in ("600000.SH","000001.SZ","430001.BJ")]
    _,_=build(tmp_path,PitRows()); loader=SnapshotLoader(tmp_path)
    assert {row["ts_code"] for row in loader.daily("20231009")} == {"600000.SH","430001.BJ"}
    assert {row["ts_code"] for row in loader.daily("20231010")} == {"600000.SH","000001.SZ","430001.BJ"}

def test_suspend_null_structural_key_fails_validation(tmp_path: Path):
    class BadSuspend(FakeProvider):
        def fetch_optional(self,dataset,trade_date=None):
            rows=super().fetch_optional(dataset,trade_date)
            if dataset == "suspend": rows[0]["suspend_type"] = None
            return rows
    manifest,_=build(tmp_path,BadSuspend())
    assert manifest["status"] == "completed" and manifest["capabilities"]["suspend"] == "unavailable"
    assert manifest["completed_at"] and validate_snapshot(tmp_path).ok

def test_provider_duplicate_and_partition_date_mismatch_are_not_completed(tmp_path: Path):
    class Duplicate(FakeProvider):
        def fetch_daily_by_trade_date(self,d): return [self._bar("600000.SH",d), self._bar("600000.SH",d)]
    duplicate,_=build(tmp_path / "duplicate",Duplicate())
    assert duplicate["status"] == "incomplete"
    class WrongDate(FakeProvider):
        def fetch_optional(self,dataset,trade_date=None):
            rows=super().fetch_optional(dataset,trade_date)
            if dataset == "limits": rows[0]["trade_date"] = "19900101"
            return rows
    wrong,_=build(tmp_path / "wrong-date",WrongDate())
    assert wrong["status"] == "completed" and wrong["capabilities"]["limits"] == "unavailable"

def test_empty_optional_daily_partition_is_valid_and_available(tmp_path: Path):
    class Empty(FakeProvider):
        def fetch_optional(self,dataset,trade_date=None):
            return [] if dataset == "suspend" else super().fetch_optional(dataset,trade_date)
    manifest,_=build(tmp_path,Empty())
    assert manifest["status"] == "completed" and manifest["capabilities"]["suspend"] == "available" and validate_snapshot(tmp_path).ok

def test_partial_resume_rebuild_keeps_partition_audits_and_digest(tmp_path: Path):
    first,_=build(tmp_path); entry=next(p for p in first["partitions"] if p["dataset"] == "daily" and p["trade_date"] == "20231009")
    (tmp_path/entry["path"]).write_bytes(b"bad")
    second,p=build(tmp_path)
    assert ("daily","20231009") in p.calls
    assert first["instrument_audit"] == second["instrument_audit"] and first["digest"] == second["digest"]

def test_namechange_shards_resume_and_skip_future_symbols(tmp_path: Path):
    class Future(FakeProvider):
        def fetch_stock_basic(self,statuses):
            return super().fetch_stock_basic(statuses) + [{"ts_code":"300999.SZ","symbol":"300999","name":"FUTURE","market":"Main","exchange":"SZSE","list_status":"P","list_date":"20240101","delist_date":""}]
    config=SnapshotConfig(root=str(tmp_path),start_date="20231009",end_date="20231010",test_only=True,namechange_shard_size=1,retry_delay_seconds=0)
    first=build_snapshot(config,Future())
    assert first["namechange"]["planned_symbol_count"] == 3 and first["namechange"]["planned_shard_count"] == 3
    second_provider=FakeProvider(); second=build_snapshot(config,second_provider)
    assert second["namechange"]["completed_shard_count"] == 3 and not [call for call in second_provider.calls if call[0] == "namechange"]

def test_combined_namechange_is_rebuilt_from_valid_shards_without_provider_calls(tmp_path: Path):
    config=SnapshotConfig(root=str(tmp_path),start_date="20231009",end_date="20231010",test_only=True,namechange_shard_size=1,retry_delay_seconds=0)
    first=build_snapshot(config,FakeProvider())
    combined=next(p for p in first["partitions"] if p["dataset"] == "namechange")
    (tmp_path/combined["path"]).write_bytes(b"corrupt")
    provider=FakeProvider(); rebuilt=build_snapshot(config,provider)
    assert not [call for call in provider.calls if call[0] == "namechange"]
    assert rebuilt["digest"] == first["digest"] and validate_snapshot(tmp_path).ok

def test_failed_namechange_shard_keeps_prior_checkpoints_and_cap_is_detected(tmp_path: Path):
    class Failing(FakeProvider):
        def fetch_namechange_by_ts_code(self,code):
            if code == "430001.BJ": raise RuntimeError("stop")
            return super().fetch_namechange_by_ts_code(code)
    config=SnapshotConfig(root=str(tmp_path),start_date="20231009",end_date="20231010",test_only=True,namechange_shard_size=1,retry_delay_seconds=0,max_retries=0)
    first=build_snapshot(config,Failing())
    assert first["capabilities"]["namechange"] == "incomplete" and first["status"] == "completed"
    assert len([p for p in first["partitions"] if p["dataset"] == "namechange_shard"]) >= 1
    resumed=FakeProvider(); build_snapshot(config,resumed)
    assert "000001.SZ" not in {call[1] for call in resumed.calls if call[0] == "namechange"}

def test_daily_coverage_and_partition_integrity_fail_validation(tmp_path: Path):
    manifest,_=build(tmp_path)
    entry=next(p for p in manifest["partitions"] if p["dataset"] == "daily_basic" and p["trade_date"] == "20231009")
    from quantpilot_core.all_a_share_snapshot.storage import atomic_write, digest
    info=atomic_write("daily_basic",tmp_path/entry["path"],[]); entry.update(info); raw=json.loads((tmp_path/"manifest.json").read_text())
    target=next(p for p in raw["partitions"] if p["dataset"] == "daily_basic" and p["trade_date"] == "20231009"); target.update(info); raw["digest"]=digest(raw)
    (tmp_path/"manifest.json").write_text(json.dumps(raw))
    assert any("daily coverage missing from daily_basic" in item for item in validate_snapshot(tmp_path).errors)


def test_truncated_calendar_is_replaced_and_only_new_sessions_are_fetched(tmp_path: Path):
    class RangeProvider(FakeProvider):
        def __init__(self, full): super().__init__(); self.full=full
        def fetch_trade_cal(self,start,end):
            self.calls.append(("trade_cal",start,end))
            rows=[{"exchange":"SSE","cal_date":"20230101","is_open":0},{"exchange":"SSE","cal_date":"20230103","is_open":1},
                  {"exchange":"SSE","cal_date":"20231229","is_open":1},{"exchange":"SSE","cal_date":"20231231","is_open":0}]
            return rows + ([{"exchange":"SSE","cal_date":"20240101","is_open":0},{"exchange":"SSE","cal_date":"20240102","is_open":1},
                            {"exchange":"SSE","cal_date":"20241231","is_open":1}] if self.full else [])
        def fetch_index_daily(self,s,start,end):
            return [self._bar(s, d) for d in ("20230103","20231229","20240102","20241231") if start <= d <= end]
    first=build_snapshot(SnapshotConfig(root=str(tmp_path),start_date="2023-01-01",end_date="2023-12-31",include_optional=False,test_only=True),RangeProvider(False))
    assert first["official_session_count"] == 2
    resumed=RangeProvider(True)
    final=build_snapshot(SnapshotConfig(root=str(tmp_path),start_date="2023-01-01",end_date="2024-12-31",include_optional=False,test_only=True),resumed)
    assert final["status"] == "completed" and final["actual_date_range"] == {"start":"20230103","end":"20241231"}
    assert final["official_session_count"] == 4 and [call for call in resumed.calls if call[0] == "daily"] == [("daily","20240102"),("daily","20241231")]
    assert validate_snapshot(tmp_path).ok


def test_truncated_calendar_response_is_not_committed_as_canonical(tmp_path: Path):
    class Truncated(FakeProvider):
        def fetch_trade_cal(self,start,end): return [{"exchange":"SSE","cal_date":"20230101","is_open":0},{"exchange":"SSE","cal_date":"20230103","is_open":1}]
    manifest,_=build(tmp_path,Truncated())
    assert manifest["status"] == "incomplete" and not [p for p in manifest["partitions"] if p["dataset"] == "calendar"]
    evidence=manifest["failed_partitions"][-1]
    assert evidence["dataset"] == "required" and evidence["attempt_count"] == 1 and evidence["reason"]


def test_optional_retry_and_failure_evidence_are_safe_for_required_snapshot(tmp_path: Path):
    class RetrySuspend(FakeProvider):
        def __init__(self): super().__init__(); self.attempts=0
        def fetch_optional(self,dataset,trade_date=None):
            if dataset == "suspend":
                self.attempts += 1
                if self.attempts == 1: raise TimeoutError("token=should-not-appear")
            return super().fetch_optional(dataset,trade_date)
    provider=RetrySuspend()
    manifest=build_snapshot(SnapshotConfig(root=str(tmp_path),start_date="20231009",end_date="20231010",test_only=True,max_retries=1,retry_delay_seconds=0),provider)
    assert manifest["status"] == "completed" and manifest["capabilities"]["suspend"] == "available" and provider.attempts == 3
    assert "should-not-appear" not in json.dumps(manifest)


def test_namechange_continues_after_failed_shard_and_later_resume_clears_evidence(tmp_path: Path):
    class MiddleFailure(FakeProvider):
        def fetch_namechange_by_ts_code(self,code):
            if code == "430001.BJ": raise RuntimeError("temporary shard failure")
            return super().fetch_namechange_by_ts_code(code)
    config=SnapshotConfig(root=str(tmp_path),start_date="20231009",end_date="20231010",test_only=True,namechange_shard_size=1,max_retries=0,retry_delay_seconds=0)
    first=build_snapshot(config,MiddleFailure())
    assert first["status"] == "completed" and first["capabilities"]["namechange"] == "incomplete"
    assert first["namechange"]["completed_shard_count"] == 2 and first["namechange"]["failed_shards"][0]["shard_identity"] == "shard-00001"
    resumed=FakeProvider(); final=build_snapshot(config,resumed)
    assert final["capabilities"]["namechange"] == "available" and not final["namechange"]["failed_shards"]
    assert [call for call in resumed.calls if call[0] == "namechange"] == [("namechange","430001.BJ")]


def test_production_pacing_has_headroom_and_test_only_builds_do_not_sleep(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    import quantpilot_core.all_a_share_snapshot.snapshot as module
    sleeps=[]; clock=iter((0.0, 0.10, 0.35))
    monkeypatch.setattr(module.time, "monotonic", lambda: next(clock)); monkeypatch.setattr(module.time, "sleep", sleeps.append)
    production=SnapshotConfig(root=str(tmp_path))
    assert production.min_request_interval_seconds >= 0.35
    pacer=_CallPacer(production); pacer.wait("daily"); pacer.wait("daily")
    assert sleeps == [pytest.approx(0.25)]
    sleeps.clear(); monkeypatch.setattr(module.time, "monotonic", lambda: 0.0); test_pacer=_CallPacer(SnapshotConfig(root=str(tmp_path),test_only=True))
    test_pacer.wait("daily"); test_pacer.wait("daily")
    assert not sleeps


def test_rate_limit_retries_with_bounded_cooldown_and_evidence(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    import quantpilot_core.all_a_share_snapshot.snapshot as module
    sleeps=[]; monkeypatch.setattr(module.time, "sleep", sleeps.append)
    config=SnapshotConfig(root=str(tmp_path),min_request_interval_seconds=0,retry_delay_seconds=0.1,rate_limit_cooldown_seconds=12,max_retries=1)
    manifest={"retry_count":0}; calls=[]
    def eventually_available():
        calls.append(1)
        if len(calls) == 1: raise RuntimeError("daily_basic frequency exceeded: 200 requests/minute")
        return []
    assert _fetch(eventually_available,config,manifest,_CallPacer(config),endpoint="daily_basic") == []
    assert manifest["retry_count"] == 1 and sleeps == [12]
    with pytest.raises(ProviderCallError) as error:
        _fetch(lambda: (_ for _ in ()).throw(RuntimeError("rate limit exceeded")),SnapshotConfig(root=str(tmp_path),max_retries=0),{"retry_count":0})
    assert _failure("daily_basic",error.value,trade_date="20230103",required=False)["exception_category"] == "retryable_rate_limit"


def test_nullable_suspend_timing_is_persisted_but_event_identity_remains_required(tmp_path: Path):
    class NullTiming(FakeProvider):
        def fetch_optional(self,dataset,trade_date=None):
            rows=super().fetch_optional(dataset,trade_date)
            if dataset == "suspend": rows[0]["suspend_timing"] = None
            return rows
    manifest,_=build(tmp_path,NullTiming()); assert manifest["capabilities"]["suspend"] == "available"
    assert SnapshotLoader(tmp_path).optional("suspend","20231009")[0]["suspend_timing"] is None and validate_snapshot(tmp_path).ok
    for field in ("ts_code","trade_date","suspend_type"):
        class MissingIdentity(FakeProvider):
            def fetch_optional(self,dataset,trade_date=None):
                rows=super().fetch_optional(dataset,trade_date)
                if dataset == "suspend": rows[0][field] = None
                return rows
        failed,_=build(tmp_path / field,MissingIdentity())
        assert failed["capabilities"]["suspend"] == "unavailable"


def test_cli_report_bounds_failure_records_without_losing_manifest_evidence():
    path=Path(__file__).parents[2] / "scripts/all_a_share_snapshot_v1.py"
    spec=importlib.util.spec_from_file_location("snapshot_cli_report",path); assert spec and spec.loader
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    failures=[{"dataset":"daily_basic","required":False,"exception_category":"retryable_rate_limit","reason":"x"} for _ in range(540)]
    failures += [{"dataset":"daily","required":True,"exception_category":"retryable_transport","reason":"y"} for _ in range(3)]
    manifest={"status":"completed","failed_partitions":failures,"partition_counts":{},"namechange":{},"capabilities":{}}
    report=module._report(manifest,"/snapshot")
    assert len(manifest["failed_partitions"]) == 543 and report["failure_count"] == 543
    assert report["required_failure_count"] == 3 and report["optional_failure_count"] == 540
    assert report["failure_counts_by_dataset"] == {"daily":3,"daily_basic":540}
    assert len(report["representative_failures"]) == 20 and report["failures_truncated"] is True
