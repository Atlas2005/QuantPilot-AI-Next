import pytest

from quantpilot_core.pit_feature_store_preflight import (
    PITFeatureRecord,
    PITFeatureStoreManifest,
    PITFeatureStoreStatus,
    parse_iso_date,
    run_pit_feature_store_preflight,
    validate_pit_feature_manifest,
    validate_pit_feature_record,
)


def manifest(**overrides):
    values = {
        "feature_set_id": "r18.alpha.baseline",
        "version": "2026-06-30",
        "source_ref": "offline-gated-provider-sample",
    }
    values.update(overrides)
    return PITFeatureStoreManifest(**values)


def record(**overrides):
    values = {
        "symbol": "600000",
        "feature_name": "close_to_open_ratio",
        "feature_value": 1.01,
        "observation_date": "2026-06-26",
        "available_date": "2026-06-26",
        "as_of_date": "2026-06-27",
        "evidence_refs": ("sample:600000:2026-06-26",),
    }
    values.update(overrides)
    return PITFeatureRecord(**values)


def test_valid_pit_feature_set_is_ready_for_sandbox_preflight() -> None:
    result = run_pit_feature_store_preflight(manifest(), [record()])

    assert result.ok is True
    assert result.status is PITFeatureStoreStatus.READY
    assert result.accepted_record_count == 1
    assert result.rejected_record_count == 0
    assert result.can_feed_sandbox is True
    assert result.reasons == ()


def test_manifest_requires_identifiers_and_sandbox_only_flags() -> None:
    reasons = validate_pit_feature_manifest(
        manifest(
            feature_set_id=" ",
            version=" ",
            source_ref=" ",
            sandbox_only=False,
            no_live_trading=False,
            no_order_execution=False,
            point_in_time=False,
        )
    )

    assert "feature_set_id_missing" in reasons
    assert "version_missing" in reasons
    assert "source_ref_missing" in reasons
    assert "sandbox_only_required" in reasons
    assert "no_live_trading_required" in reasons
    assert "no_order_execution_required" in reasons
    assert "point_in_time_required" in reasons


def test_empty_feature_records_are_rejected() -> None:
    result = run_pit_feature_store_preflight(manifest(), [])

    assert result.ok is False
    assert result.status is PITFeatureStoreStatus.REJECTED
    assert "feature_records_missing" in result.reasons


def test_record_rejects_lookahead_observation_date() -> None:
    reasons = validate_pit_feature_record(
        record(observation_date="2026-06-28", as_of_date="2026-06-27")
    )

    assert "observation_after_as_of" in reasons


def test_record_rejects_available_date_after_as_of() -> None:
    reasons = validate_pit_feature_record(
        record(available_date="2026-06-28", as_of_date="2026-06-27")
    )

    assert "available_after_as_of" in reasons


def test_record_rejects_available_date_before_observation() -> None:
    reasons = validate_pit_feature_record(
        record(observation_date="2026-06-27", available_date="2026-06-26")
    )

    assert "available_before_observation" in reasons


def test_record_requires_symbol_feature_name_numeric_value_and_evidence() -> None:
    reasons = validate_pit_feature_record(
        record(
            symbol=" ",
            feature_name=" ",
            feature_value=float("nan"),
            evidence_refs=(),
        )
    )

    assert "symbol_missing" in reasons
    assert "feature_name_missing" in reasons
    assert "feature_value_not_finite_number" in reasons
    assert "evidence_refs_missing" in reasons


def test_record_date_parsing_is_strict_iso_date() -> None:
    assert parse_iso_date("2026-06-30").isoformat() == "2026-06-30"

    with pytest.raises(ValueError, match="invalid ISO date"):
        parse_iso_date("20260630")


def test_preflight_prefixes_record_reasons_and_counts_rejections() -> None:
    result = run_pit_feature_store_preflight(
        manifest(),
        [
            record(),
            record(feature_name=" ", available_date="2026-06-28"),
        ],
    )

    assert result.ok is False
    assert result.accepted_record_count == 1
    assert result.rejected_record_count == 1
    assert "record[1]:feature_name_missing" in result.reasons
    assert "record[1]:available_after_as_of" in result.reasons


def test_duplicate_feature_keys_warn_without_rejecting_valid_records() -> None:
    result = run_pit_feature_store_preflight(
        manifest(),
        [
            record(),
            record(feature_value=1.02),
        ],
    )

    assert result.ok is True
    assert result.accepted_record_count == 2
    assert result.warnings == (
        "duplicate_feature_key:600000:close_to_open_ratio:2026-06-27",
    )
