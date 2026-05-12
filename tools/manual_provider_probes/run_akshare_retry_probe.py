from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "local_artifacts" / "provider_probes"
SUMMARY_PATH = OUTPUT_DIR / "akshare_retry_probe_summary.json"
MAX_ROWS = 10
REQUIRED_FIELDS = ["symbol", "trade_date", "open", "high", "low", "close", "volume", "amount"]


def _write_summary(summary: dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")


def _base_summary(status: str, warnings: list[str], notes: str) -> dict[str, Any]:
    return {
        "provider_name": "AkShare",
        "status": status,
        "row_count": 0,
        "mapped_field_count": 0,
        "missing_required_fields": REQUIRED_FIELDS,
        "output_path": str(SUMMARY_PATH),
        "raw_data_committed": False,
        "approved_for_adapter": False,
        "approved_for_alpha_validation": False,
        "decision": "retry_later",
        "warnings": warnings,
        "notes": notes,
    }


def _records_from_provider_result(result: Any) -> list[dict[str, Any]]:
    if hasattr(result, "head") and hasattr(result, "to_dict"):
        return list(result.head(MAX_ROWS).to_dict("records"))
    if isinstance(result, list):
        return [row for row in result[:MAX_ROWS] if isinstance(row, dict)]
    return []


def _mapped_fields(records: list[dict[str, Any]]) -> tuple[int, list[str]]:
    if not records:
        return 0, REQUIRED_FIELDS

    first = records[0]
    source_candidates = {
        "symbol": ["symbol", "代码", "code"],
        "trade_date": ["trade_date", "日期", "date"],
        "open": ["open", "开盘"],
        "high": ["high", "最高"],
        "low": ["low", "最低"],
        "close": ["close", "收盘"],
        "volume": ["volume", "成交量"],
        "amount": ["amount", "成交额"],
    }
    mapped = [
        target
        for target, candidates in source_candidates.items()
        if any(candidate in first for candidate in candidates)
    ]
    missing = [field for field in REQUIRED_FIELDS if field not in mapped]
    return len(mapped), missing


def run_probe() -> dict[str, Any]:
    try:
        import akshare as ak  # type: ignore[import-not-found]
    except ImportError:
        return _base_summary(
            "skipped",
            ["AkShare is not installed in this environment."],
            "Manual retry probe skipped without installing packages.",
        )

    try:
        result = ak.stock_zh_a_hist(
            symbol="600000",
            period="daily",
            start_date="20240102",
            end_date="20240110",
            adjust="qfq",
        )
        records = _records_from_provider_result(result)
        mapped_count, missing = _mapped_fields(records)
        status = "success" if records else "inconclusive"
        decision = "candidate_for_manual_review" if records else "retry_later"
        warnings = [
            "Tiny controlled sample only.",
            "No provider is approved by this probe.",
            "No alpha validation is allowed from this output.",
        ]
        summary = _base_summary(status, warnings, "AkShare retry readiness probe summary only.")
        summary.update(
            {
                "row_count": len(records),
                "mapped_field_count": mapped_count,
                "missing_required_fields": missing,
                "decision": decision,
            }
        )
        return summary
    except Exception as exc:  # pragma: no cover - manual provider/network path
        return _base_summary(
            "failed",
            [f"AkShare probe failed safely: {exc}"],
            "Provider, network, or schema failure captured without raw data commit.",
        )


def main() -> None:
    summary = run_probe()
    _write_summary(summary)
    print(f"Wrote AkShare retry probe summary to {SUMMARY_PATH}")


if __name__ == "__main__":
    main()
