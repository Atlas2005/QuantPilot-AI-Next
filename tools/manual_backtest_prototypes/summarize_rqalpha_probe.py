from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SUMMARY_PATH = ROOT / "local_artifacts" / "backtest_prototypes" / "rqalpha" / "rqalpha_probe_summary.json"


def _load_summary() -> dict[str, Any]:
    if not SUMMARY_PATH.exists():
        raise FileNotFoundError(f"Missing RQAlpha probe summary: {SUMMARY_PATH}")
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


def main() -> int:
    try:
        summary = _load_summary()
    except Exception as exc:
        print(f"Unable to summarize RQAlpha probe: {exc}")
        return 1

    lines = [
        f"provider: {summary.get('provider')}",
        f"environment_path: {summary.get('environment_path')}",
        f"symbol: {summary.get('symbol')}",
        f"row_count: {summary.get('row_count')}",
        f"rqalpha_importable: {summary.get('rqalpha_importable')}",
        f"rqalpha_version: {summary.get('rqalpha_version')}",
        f"minimal_local_run_attempted: {summary.get('minimal_local_run_attempted')}",
        f"minimal_local_run_succeeded: {summary.get('minimal_local_run_succeeded')}",
        f"data_bundle_required_or_observed: {summary.get('data_bundle_required_or_observed')}",
        f"fake_fixture_direct_support_observed: {summary.get('fake_fixture_direct_support_observed')}",
        f"output_metrics_available: {summary.get('output_metrics_available')}",
        f"unsupported_a_share_rules: {summary.get('unsupported_a_share_rules')}",
        f"errors: {summary.get('errors')}",
        f"warnings: {summary.get('warnings')}",
        f"conclusion: {summary.get('conclusion')}",
    ]
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
