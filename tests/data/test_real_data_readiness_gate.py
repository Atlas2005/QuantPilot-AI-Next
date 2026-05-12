from pathlib import Path

from quantpilot_core.data.real_data_readiness import (
    ReadinessStatus,
    evaluate_readiness_gate,
    load_readiness_gate,
    summarize_readiness_report,
    validate_readiness_gate,
)


ROOT = Path(__file__).resolve().parents[2]
GATE_PATH = ROOT / "data" / "real_data_readiness" / "real_data_gate_v0_1.json"


def test_real_data_gate_loads_and_validates() -> None:
    gate = load_readiness_gate(GATE_PATH)

    assert gate["gate_name"] == "real_data_readiness_gate"
    assert validate_readiness_gate(gate) == []


def test_real_data_gate_blocks_claims_and_fetches() -> None:
    gate = load_readiness_gate(GATE_PATH)

    assert gate["alpha_claim_allowed"] is False
    assert gate["trading_ready"] is False
    assert gate["real_data_fetch_allowed_in_this_phase"] is False
    assert gate["approved_data_sources"] == []


def test_required_readiness_checks_exist_and_block() -> None:
    gate = load_readiness_gate(GATE_PATH)
    codes = {check["code"] for check in gate["checks"]}
    required = {
        "data_source_license_review",
        "data_source_reliability_probe",
        "schema_mapping_coverage",
        "qfq_hfq_raw_adjustment_policy",
        "symbol_format_policy",
        "duplicate_date_symbol_check",
        "missing_bar_policy",
        "suspension_policy",
        "corporate_action_policy",
        "minimum_symbol_count",
        "minimum_date_count",
        "train_validation_test_split",
        "oos_required",
        "walk_forward_required",
        "transaction_cost_model_required",
        "a_share_market_rule_integration_required",
        "liquidity_capacity_policy",
        "raw_data_storage_policy",
        "raw_data_not_committed_policy",
        "reproducibility_manifest_required",
        "provider_failure_handling_policy",
        "paper_feedback_required_before_live",
        "no_alpha_claim_without_evidence",
    }

    assert required.issubset(codes)
    assert any(check["severity"] == "blocking" for check in gate["checks"])


def test_readiness_evaluation_is_not_ready() -> None:
    gate = load_readiness_gate(GATE_PATH)
    report = evaluate_readiness_gate(gate)
    summary = summarize_readiness_report(report)

    assert report.status in {ReadinessStatus.not_ready, ReadinessStatus.partially_ready}
    assert report.blocking_count > 0
    assert report.alpha_claim_allowed is False
    assert report.trading_ready is False
    assert summary["alpha_claim_allowed"] is False
    assert summary["trading_ready"] is False
