"""Deterministic Parquet partitions and manifest integrity primitives."""
from __future__ import annotations

import errno
import hashlib
import importlib
import json
import os
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


def temporary_path(path: Path) -> Path:
    """Return the private path used while atomically replacing ``path``."""
    return path.with_name("." + path.name + ".tmp")


def discard_temporary(path: Path) -> None:
    """Remove only an incomplete temporary sibling, never the canonical file."""
    temporary_path(path).unlink(missing_ok=True)


def _sync_file(path: Path) -> None:
    """Flush a completed file through a descriptor owned by this context.

    Windows' CRT can reject ``fsync``/``_commit`` for a read-only descriptor.
    Reopening the path read/write avoids sharing PyArrow's already-closed file
    handle and keeps ``fileno`` and ``fsync`` inside the owning context.
    """
    with path.open("rb+") as handle:
        handle.flush()
        os.fsync(handle.fileno())


def _sync_directory(path: Path) -> None:
    """Best-effort directory sync on platforms that expose directory fds."""
    if os.name == "nt" or not hasattr(os, "O_DIRECTORY"):
        return
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        try:
            os.fsync(descriptor)
        except OSError as exc:
            unsupported = {errno.EBADF, errno.EINVAL, errno.EPERM}
            for name in ("ENOTSUP", "EOPNOTSUPP"):
                value = getattr(errno, name, None)
                if value is not None:
                    unsupported.add(value)
            if exc.errno not in unsupported:
                raise
    finally:
        os.close(descriptor)


def atomic_write(dataset: str, path: Path, rows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    pq = importlib.import_module("pyarrow" + ".parquet")
    path.parent.mkdir(parents=True, exist_ok=True)
    table = table_for(dataset, rows)
    tmp = temporary_path(path)
    discard_temporary(path)
    try:
        # Give PyArrow a path so it owns and closes its own file handle before
        # this process opens a separate descriptor for durable finalization.
        pq.write_table(table, tmp, compression="zstd")
        _sync_file(tmp)
        # Every temporary-file handle is closed before Windows sees replace.
        os.replace(tmp, path)
        _sync_directory(path.parent)
    except BaseException:
        # Preserve any completed canonical partition.  Only the private sibling
        # from this failed attempt is eligible for cleanup.
        try:
            discard_temporary(path)
        except OSError:
            pass
        raise
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
