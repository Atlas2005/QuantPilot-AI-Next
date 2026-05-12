import json
from pathlib import Path

from quantpilot_core.data.provider_probe_readiness import (
    summarize_provider_probe_summaries,
    validate_provider_probe_summary,
)


ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "data" / "provider_probe_readiness" / "provider_probe_policy_v0_1.json"


def _valid_summary() -> dict:
    return {
        "provider_name": "AkShare",
        "status": "success",
        "row_count": 3,
        "mapped_field_count": 8,
        "missing_required_fields": [],
        "output_path": "local_artifacts/provider_probes/akshare_retry_probe_summary.json",
        "raw_data_committed": False,
        "approved_for_adapter": False,
        "approved_for_alpha_validation": False,
        "decision": "candidate_for_manual_review",
        "warnings": ["tiny sample only"],
        "notes": "manual readiness probe only",
    }


def test_provider_probe_policy_loads_and_blocks_approval() -> None:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))

    assert policy["approved_data_sources"] == []
    assert policy["approved_for_adapter"] is False
    assert policy["approved_for_alpha_validation"] is False
    assert policy["raw_data_commit_allowed"] is False
    assert policy["large_fetch_allowed"] is False
    assert policy["max_rows_per_probe"] <= 10
    assert {"AkShare", "Baostock"}.issubset(set(policy["target_providers"]))


def test_validate_provider_probe_summary_accepts_conservative_summary() -> None:
    assert validate_provider_probe_summary(_valid_summary()) == []


def test_validate_provider_probe_summary_rejects_adapter_approval() -> None:
    summary = _valid_summary()
    summary["approved_for_adapter"] = True

    errors = validate_provider_probe_summary(summary)

    assert "approved_for_adapter must be false" in errors


def test_validate_provider_probe_summary_rejects_alpha_validation_approval() -> None:
    summary = _valid_summary()
    summary["approved_for_alpha_validation"] = True

    errors = validate_provider_probe_summary(summary)

    assert "approved_for_alpha_validation must be false" in errors


def test_validate_provider_probe_summary_rejects_nonlocal_output_path() -> None:
    summary = _valid_summary()
    summary["output_path"] = "data/provider_probe_summary.json"

    errors = validate_provider_probe_summary(summary)

    assert "output_path must point under local_artifacts/provider_probes/ or be empty" in errors


def test_summarize_provider_probe_summaries() -> None:
    akshare = _valid_summary()
    baostock = _valid_summary()
    baostock["provider_name"] = "Baostock"
    baostock["status"] = "skipped"
    baostock["row_count"] = 0
    baostock["decision"] = "retry_later"

    summary = summarize_provider_probe_summaries([akshare, baostock])

    assert summary["summary_count"] == 2
    assert summary["status_counts"]["success"] == 1
    assert summary["status_counts"]["skipped"] == 1
    assert summary["approved_for_adapter_count"] == 0
    assert summary["approved_for_alpha_validation_count"] == 0
    assert summary["any_data_source_approved"] is False
