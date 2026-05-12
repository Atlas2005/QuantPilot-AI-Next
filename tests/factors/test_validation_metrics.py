from quantpilot_core.factors.validation_metrics import (
    EvidenceQuality,
    FactorMetricResult,
    FactorValidationReport,
    compute_grouped_forward_returns,
    compute_toy_information_coefficient,
    build_factor_validation_report,
)


def test_compute_toy_information_coefficient_returns_metric_result() -> None:
    result = compute_toy_information_coefficient([1.0, 2.0, 3.0], [0.1, 0.2, 0.3])

    assert isinstance(result, FactorMetricResult)
    assert result.metric_name == "toy_information_coefficient"
    assert result.sample_size == 3
    assert any("no statistical significance" in item for item in result.limitations)


def test_small_sample_produces_warnings() -> None:
    result = compute_toy_information_coefficient([1.0], [0.1])

    assert result.evidence_quality == EvidenceQuality.insufficient_sample
    assert result.warnings


def test_build_factor_validation_report_keeps_safety_flags_false() -> None:
    report = build_factor_validation_report("toy_factor", [1.0, 2.0], [0.1, 0.2])

    assert isinstance(report, FactorValidationReport)
    assert report.alpha_claim_allowed is False
    assert report.trading_ready is False
    assert report.evidence_quality == EvidenceQuality.insufficient_sample


def test_grouped_forward_returns_handles_tiny_samples_safely() -> None:
    grouped = compute_grouped_forward_returns([1.0], [0.1], group_count=3)

    assert grouped["groups"] == []
    assert grouped["warnings"]


def test_report_limitations_include_required_evidence_gaps() -> None:
    report = build_factor_validation_report("toy_factor", [1.0, 2.0, 3.0], [0.1, 0.2, 0.3])
    limitations = report.metric_results[0].limitations

    assert "fake fixture only" in limitations
    assert "no OOS" in limitations
    assert "no walk-forward" in limitations
    assert all("significant" not in warning.lower() for warning in report.metric_results[0].warnings)
