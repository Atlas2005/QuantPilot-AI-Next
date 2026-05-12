from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "local_artifacts" / "provider_probes"
SUMMARY_PATH = OUTPUT_DIR / "baostock_retry_probe_summary.json"
MAX_ROWS = 10
REQUIRED_FIELDS = ["symbol", "trade_date", "open", "high", "low", "close", "volume", "amount"]


def _write_summary(summary: dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")


def _base_summary(status: str, warnings: list[str], notes: str) -> dict[str, Any]:
    return {
        "provider_name": "Baostock",
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


def _mapped_fields(records: list[dict[str, Any]]) -> tuple[int, list[str]]:
    if not records:
        return 0, REQUIRED_FIELDS

    first = records[0]
    source_candidates = {
        "symbol": ["symbol", "code"],
        "trade_date": ["trade_date", "date"],
        "open": ["open"],
        "high": ["high"],
        "low": ["low"],
        "close": ["close"],
        "volume": ["volume"],
        "amount": ["amount"],
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
        import baostock as bs  # type: ignore[import-not-found]
    except ImportError:
        return _base_summary(
            "skipped",
            ["Baostock is not installed in this environment."],
            "Manual retry probe skipped without installing packages.",
        )

    logged_in = False
    try:
        login = bs.login()
        logged_in = True
        if getattr(login, "error_code", "1") != "0":
            return _base_summary(
                "failed",
                [f"Baostock login failed: {getattr(login, 'error_msg', 'unknown error')}"],
                "Login failure captured without falling back to another provider.",
            )

        result = bs.query_history_k_data_plus(
            "sh.600000",
            "date,code,open,high,low,close,volume,amount",
            start_date="2024-01-02",
            end_date="2024-01-10",
            frequency="d",
            adjustflag="2",
        )
        if getattr(result, "error_code", "1") != "0":
            return _base_summary(
                "failed",
                [f"Baostock query failed: {getattr(result, 'error_msg', 'unknown error')}"],
                "Query failure captured without raw data commit.",
            )

        records: list[dict[str, Any]] = []
        fields = list(getattr(result, "fields", []))
        while len(records) < MAX_ROWS and result.next():
            records.append(dict(zip(fields, result.get_row_data())))

        mapped_count, missing = _mapped_fields(records)
        status = "success" if records else "inconclusive"
        decision = "candidate_for_manual_review" if records else "retry_later"
        warnings = [
            "Tiny controlled sample only.",
            "No provider is approved by this probe.",
            "No alpha validation is allowed from this output.",
        ]
        summary = _base_summary(status, warnings, "Baostock retry readiness probe summary only.")
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
            [f"Baostock probe failed safely: {exc}"],
            "Provider, network, or schema failure captured without raw data commit.",
        )
    finally:
        if logged_in:
            try:
                bs.logout()
            except Exception:
                pass


def main() -> None:
    summary = run_probe()
    _write_summary(summary)
    print(f"Wrote Baostock retry probe summary to {SUMMARY_PATH}")


if __name__ == "__main__":
    main()
