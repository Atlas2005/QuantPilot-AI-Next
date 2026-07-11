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
        print(json.dumps(_report(manifest, args.root),sort_keys=True)); return 0 if manifest["status"]=="completed" else 1
    result=validate_snapshot(args.root)
    if args.command == "validate": print(json.dumps({"ok":result.ok,"errors":result.errors,"checked_partitions":result.checked_partitions},sort_keys=True)); return 0 if result.ok else 1
    m=result.manifest; print(json.dumps(_report(m, args.root),sort_keys=True)); return 0 if result.ok else 1

def _report(manifest, root):
    required = {"stock_basic", "calendar", "daily", "adj_factor", "benchmark"}
    failures = list(manifest.get("failed_partitions", ()))
    required_failures = [item for item in failures if item.get("required", item.get("dataset") in required)]
    optional_failures = [item for item in failures if not item.get("required", item.get("dataset") in required)]
    by_dataset = {}
    by_category = {}
    for item in failures:
        dataset = str(item.get("dataset", "unknown")); category = str(item.get("exception_category", "unspecified"))
        by_dataset[dataset] = by_dataset.get(dataset, 0) + 1
        by_category[category] = by_category.get(category, 0) + 1
    limit = 20
    return {"status":manifest.get("status"), "required_completed":manifest.get("status") == "completed",
            "digest":manifest.get("digest"), "root":root, "requested_date_range":manifest.get("requested_date_range", {}),
            "actual_date_range":manifest.get("actual_date_range", {}), "official_session_count":manifest.get("official_session_count"),
            "capabilities":manifest.get("capabilities", {}), "failure_count":len(failures),
            "required_failure_count":len(required_failures), "optional_failure_count":len(optional_failures),
            "failure_counts_by_dataset":dict(sorted(by_dataset.items())), "failure_counts_by_exception_category":dict(sorted(by_category.items())),
            "missing_required_partition_count":len(required_failures), "remaining_optional_partition_count":len(optional_failures),
            "remaining_namechange_shards":manifest.get("namechange", {}).get("remaining_shard_count", 0),
            "representative_failures":failures[:limit], "failures_truncated":len(failures) > limit,
            "resumed_existing_data":bool(manifest.get("resume_count")),
            "symbols":manifest.get("symbol_counts",{}).get("total"), "partitions":sum(manifest.get("partition_counts",{}).values())}
if __name__ == "__main__": raise SystemExit(main())
