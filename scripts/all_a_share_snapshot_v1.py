#!/usr/bin/env python
"""Offline-safe CLI for PR #118 all-A-share snapshot build/validate/summary."""
from __future__ import annotations
import argparse, json
from quantpilot_core.all_a_share_snapshot.contracts import SnapshotConfig
from quantpilot_core.all_a_share_snapshot.provider import TushareAllAShareProvider
from quantpilot_core.all_a_share_snapshot.snapshot import build_snapshot, validate_snapshot

def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description="All-A-share Parquet snapshot (direct Tushare only).")
    parser.add_argument("command",choices=("build","validate","summary")); parser.add_argument("--root",default=".cache/all_a_share_snapshot_v1")
    parser.add_argument("--start-date",default="20231009"); parser.add_argument("--end-date",default="20251231"); parser.add_argument("--no-optional",action="store_true")
    args=parser.parse_args(argv)
    if args.command == "build":
        manifest=build_snapshot(SnapshotConfig(root=args.root,start_date=args.start_date,end_date=args.end_date,include_optional=not args.no_optional),TushareAllAShareProvider())
        print(json.dumps({"status":manifest["status"],"digest":manifest["digest"],"root":args.root},sort_keys=True)); return 0 if manifest["status"]=="completed" else 1
    result=validate_snapshot(args.root)
    if args.command == "validate": print(json.dumps({"ok":result.ok,"errors":result.errors,"checked_partitions":result.checked_partitions},sort_keys=True)); return 0 if result.ok else 1
    m=result.manifest; print(json.dumps({"status":m.get("status"),"digest":m.get("digest"),"symbols":m.get("symbol_counts",{}).get("total"),"sessions":m.get("official_session_count"),"partitions":sum(m.get("partition_counts",{}).values())},sort_keys=True)); return 0 if result.ok else 1
if __name__ == "__main__": raise SystemExit(main())
