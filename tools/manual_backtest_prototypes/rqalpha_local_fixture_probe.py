from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
ENVIRONMENT_PATH = ROOT / ".venv-prototypes" / "rqalpha"
INPUT_FIXTURE = ROOT / "data" / "fixtures" / "a_share_daily_sample_valid.csv"
ARTIFACT_DIR = ROOT / "local_artifacts" / "backtest_prototypes" / "rqalpha"
SUMMARY_PATH = ARTIFACT_DIR / "rqalpha_probe_summary.json"
SYMBOL = "000001.SZ"
UNSUPPORTED_A_SHARE_RULES = [
    "T+1 not proven",
    "limit-up/limit-down not proven",
    "suspension handling not proven",
    "ST/delisting special cases not proven",
    "liquidity constraints not proven",
    "realistic fees/slippage not proven",
    "realistic A-share order matching not proven",
    "corporate actions not proven",
    "production data bundle reliability not proven",
    "commercial/license suitability not proven",
]
LICENSE_WARNING = (
    "RQAlpha is research/prototype-only in this phase. Do not commercialize, vendor, "
    "copy source, integrate, or create derivative production adapter code before license review."
)


def _base_summary() -> dict[str, Any]:
    return {
        "provider": "rqalpha",
        "environment_path": str(ENVIRONMENT_PATH),
        "input_fixture": str(INPUT_FIXTURE),
        "input_is_fake_fixture": True,
        "symbol": SYMBOL,
        "row_count": 0,
        "rqalpha_importable": False,
        "rqalpha_version": None,
        "minimal_local_run_attempted": False,
        "minimal_local_run_succeeded": False,
        "data_bundle_required_or_observed": "unknown",
        "fake_fixture_direct_support_observed": False,
        "output_metrics_available": False,
        "a_share_rule_support_observed": [],
        "unsupported_a_share_rules": UNSUPPORTED_A_SHARE_RULES,
        "license_commercial_warning": LICENSE_WARNING,
        "errors": [],
        "warnings": [],
        "conclusion": "Not run yet.",
    }


def _write_summary(summary: dict[str, Any]) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def _load_symbol_rows() -> list[dict[str, str]]:
    if not INPUT_FIXTURE.exists():
        raise FileNotFoundError(f"Missing fixture: {INPUT_FIXTURE}")

    with INPUT_FIXTURE.open("r", encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row.get("symbol") == SYMBOL]

    return sorted(rows, key=lambda row: row["trade_date"])


def _safe_module_attrs(module: Any) -> list[str]:
    names = []
    for name in ("run", "run_file", "cli", "__version__", "version"):
        if hasattr(module, name):
            names.append(name)
    return names


def main() -> int:
    summary = _base_summary()

    try:
        import rqalpha  # type: ignore[import-not-found]
    except Exception as exc:
        summary["errors"].append(f"rqalpha_not_importable:{exc}")
        summary["conclusion"] = "RQAlpha is not importable in this environment."
        _write_summary(summary)
        return 2

    summary["rqalpha_importable"] = True
    summary["rqalpha_version"] = getattr(rqalpha, "__version__", None) or getattr(rqalpha, "version", None)
    summary["warnings"].append(f"Safe module attributes observed: {_safe_module_attrs(rqalpha)}")

    try:
        rows = _load_symbol_rows()
        summary["row_count"] = len(rows)
        if not rows:
            raise ValueError(f"No rows found for symbol {SYMBOL}")

        summary["minimal_local_run_attempted"] = False
        summary["minimal_local_run_succeeded"] = False
        summary["data_bundle_required_or_observed"] = (
            "Likely required for normal RQAlpha execution; no data bundle/provider setup was created in this phase."
        )
        summary["fake_fixture_direct_support_observed"] = False
        summary["output_metrics_available"] = False
        summary["a_share_rule_support_observed"] = [
            "None proven. RQAlpha was imported and inspected only; no backtest was run."
        ]
        summary["warnings"].extend(
            [
                "Probe stopped before any full RQAlpha run because fake-fixture-only execution path was not proven without bundle/config setup.",
                "No broker, live trading, order, mod-ctp, mod-vnpy, or provider functionality was used.",
            ]
        )
        summary["conclusion"] = (
            "RQAlpha installed and imported in the isolated environment, but fake-fixture-only local run support "
            "was not proven. Data bundle/config requirements need further review before any deeper prototype."
        )
        _write_summary(summary)
        return 0
    except Exception as exc:
        summary["errors"].append(f"rqalpha_probe_failed:{exc}")
        summary["conclusion"] = "RQAlpha probe failed safely."
        _write_summary(summary)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
