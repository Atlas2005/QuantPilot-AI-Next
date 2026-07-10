"""Deterministic Parquet partitions and manifest integrity primitives."""
from __future__ import annotations
import hashlib, importlib, json, os
from pathlib import Path
from typing import Any, Mapping, Sequence
from quantpilot_core.all_a_share_snapshot.parquet_runtime import require_pyarrow

FORMAT_VERSION = 2
SCHEMA_VERSION = 2
DIGEST_EXCLUDED = frozenset({"digest", "created_at", "completed_at", "status", "failed_partitions", "retry_count", "resume_count", "historical_code_resolution_calls"})

SCHEMAS: dict[str, tuple[tuple[str, str], ...]] = {
 "stock_basic": (("ts_code","string"),("symbol","string"),("name","string"),("area","string"),("industry","string"),("market","string"),("exchange","string"),("list_status","string"),("list_date","string"),("delist_date","string")),
 "calendar": (("exchange","string"),("cal_date","string"),("is_open","int64")),
 "daily": (("ts_code","string"),("trade_date","string"),("open","float64"),("high","float64"),("low","float64"),("close","float64"),("pre_close","float64"),("change","float64"),("pct_chg","float64"),("vol","float64"),("amount","float64")),
 "adj_factor": (("ts_code","string"),("trade_date","string"),("adj_factor","float64")),
 "daily_basic": (("ts_code","string"),("trade_date","string"),("close","float64"),("turnover_rate","float64"),("pe","float64"),("pb","float64"),("total_mv","float64")),
 "suspend": (("ts_code","string"),("trade_date","string"),("suspend_timing","string"),("suspend_type","string")),
 "limits": (("ts_code","string"),("trade_date","string"),("up_limit","float64"),("down_limit","float64")),
 "namechange": (("ts_code","string"),("name","string"),("start_date","string"),("end_date","string"),("ann_date","string"),("change_reason","string")),
 "namechange_shard": (("ts_code","string"),("name","string"),("start_date","string"),("end_date","string"),("ann_date","string"),("change_reason","string")),
 "benchmark": (("ts_code","string"),("trade_date","string"),("open","float64"),("high","float64"),("low","float64"),("close","float64"),("pre_close","float64"),("change","float64"),("pct_chg","float64"),("vol","float64"),("amount","float64")),
}

def digest(payload: Mapping[str, Any]) -> str:
    clean = {k:v for k,v in payload.items() if k not in DIGEST_EXCLUDED}
    return hashlib.sha256(json.dumps(clean, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
def schema_fingerprint(schema: Any) -> str:
    return hashlib.sha256(str(schema).encode()).hexdigest()
def table_for(dataset: str, rows: Sequence[Mapping[str, Any]]) -> Any:
    pa = require_pyarrow().module
    fields = SCHEMAS[dataset]
    schema = pa.schema([(name, typ) for name,typ in fields])
    normalized=[]
    for row in rows:
        item={}
        for name, typ in fields:
            value=row.get(name)
            if value is not None and typ == "string": value=str(value)
            if value is not None and typ == "int64": value=int(value)
            if value is not None and typ == "float64": value=float(value)
            item[name]=value
        normalized.append(item)
    return pa.Table.from_pylist(normalized, schema=schema)
def atomic_write(dataset: str, path: Path, rows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    runtime=require_pyarrow().module; pq=importlib.import_module("pyarrow" + ".parquet")
    path.parent.mkdir(parents=True, exist_ok=True); table=table_for(dataset, rows); tmp=path.with_name("."+path.name+".tmp")
    pq.write_table(table, tmp, compression="zstd")
    with tmp.open("rb") as fh: os.fsync(fh.fileno())
    os.replace(tmp,path)
    return {"path":str(path),"row_count":table.num_rows,"sha256":file_hash(path),"schema_fingerprint":schema_fingerprint(table.schema)}
def read_table(path: Path) -> Any:
    # ParquetDataset infers Hive columns from the parent trade_date= directory,
    # which conflicts with the explicit string trade_date field.  Reading the
    # single file directly preserves the declared schema and avoids any scan.
    return importlib.import_module("pyarrow" + ".parquet").ParquetFile(path).read()
def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); tmp=path.with_name("."+path.name+".tmp")
    with tmp.open("w",encoding="utf-8") as fh:
        json.dump(payload,fh,sort_keys=True,indent=2,ensure_ascii=True); fh.write("\n"); fh.flush(); os.fsync(fh.fileno())
    os.replace(tmp,path)
