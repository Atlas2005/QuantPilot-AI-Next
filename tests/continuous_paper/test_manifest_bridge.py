"""Focused tests for the manifest-bridge production boundary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from quantpilot_core.continuous_paper.manifest_bridge import (
    FROZEN_MANIFEST_PARAMETER_NAMES,
    load_production_input_payload,
    load_production_pipeline_config,
    normalize_production_input_payload,
)
from quantpilot_core.production_candidate import (
    build_production_candidate_manifest,
    load_runtime_manifest,
    write_manifest_atomic,
)
from quantpilot_core.production_candidate.contracts import (
    ProductionCandidateContractError,
)
from quantpilot_core.real_candidate_pipeline import RealCandidatePipelineConfig


# ---------------------------------------------------------------------------
# Shared test helper: build a valid manifest dict and write it to disk.
# ---------------------------------------------------------------------------


def _write_valid_manifest(tmp_path: Path, **overrides) -> Path:
    """Write a valid runtime manifest JSON file and return its path."""
    a = tmp_path / "pr121.json"
    a.write_text("{}")
    b = tmp_path / "pr122.json"
    b.write_text("{}")
    values = dict(
        created_at="2026-07-12T00:00:00+00:00",
        code_revision="revision",
        snapshot_digest="a" * 64,
        benchmark={"symbol": "000300.SH"},
        source_artifacts={"pr121": str(a), "pr122": str(b)},
        frozen_strategy_parameters={
            "initial_capital": 100000.0,
            "target_symbol_count": 2,
            "max_execution_symbols": 6,
            "strategy_id": "equal_weight_baseline",
        },
        frozen_portfolio_parameters={
            "target_position_count": 2,
            "max_position_weight": 0.1,
            "reserve_cash_weight": 0.02,
        },
        frozen_execution_parameters={"min_order_lot": 100},
        fee_profile_policy={
            "profile_id": "engineering-default",
            "required_provenance": "engineering_fallback",
        },
        account_capability_policy={"capability_digest": "null"},
    )
    values.update(overrides)
    manifest = build_production_candidate_manifest(**values)
    path = write_manifest_atomic(manifest, tmp_path / "manifest.json")
    return Path(path)


# ---------------------------------------------------------------------------
# 1. Manifest file JSON is parsed and passed as Mapping.
# ---------------------------------------------------------------------------


def test_manifest_json_parsed_and_passed_as_mapping(tmp_path: Path) -> None:
    manifest_path = _write_valid_manifest(tmp_path)
    config = load_production_pipeline_config(
        manifest_path=manifest_path,
        decision_session="2026-04-03",
        state_path=str(tmp_path / "state.json"),
        report_path=str(tmp_path / "report.json"),
    )
    assert isinstance(config, RealCandidatePipelineConfig)
    # Verify the manifest was loaded and its frozen params applied.
    assert config.initial_capital == 100000.0
    assert config.target_symbol_count == 2
    assert config.max_execution_symbols == 6
    assert config.production_manifest is not None


def test_manifest_file_not_a_json_object_is_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("[1, 2, 3]")
    with pytest.raises(TypeError, match="JSON object"):
        load_production_pipeline_config(
            manifest_path=bad,
            decision_session="2026-04-03",
        )


def test_input_file_not_a_json_object_is_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "input.json"
    bad.write_text("[1, 2, 3]")
    with pytest.raises(TypeError, match="input JSON.*object"):
        load_production_input_payload(bad)


def test_input_file_uses_shared_field_validation(tmp_path: Path) -> None:
    bad = tmp_path / "input.json"
    bad.write_text('{"symbols": "600000.SH"}')
    with pytest.raises(TypeError, match="symbols must be an array"):
        load_production_input_payload(bad)


def test_shared_payload_schema_normalizes_every_supported_field() -> None:
    payload = normalize_production_input_payload(
        {
            "symbols": ["sh.600000", "600000.SH", "000001"],
            "bars": [{"symbol": "600000.SH"}],
            "information_signals": [
                {"signal": {"target": "600000.SH"}, "available_at": "timestamp"}
            ],
            "information_provenance": {"provider": "fixture"},
            "advisory_provenance": {"deepseek_live_call": False},
            "quant_firm_context": {"requested_action": "hold"},
        }
    )
    assert payload == {
        "symbols": ("600000.SH", "000001.SZ"),
        "input_bars": ({"symbol": "600000.SH"},),
        "information_signals": (
            {"signal": {"target": "600000.SH"}, "available_at": "timestamp"},
        ),
        "information_provenance": {"provider": "fixture"},
        "advisory_provenance": {"deepseek_live_call": False},
        "quant_firm_context": {"requested_action": "hold"},
    }


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ([], "payload must be an object"),
        ({"symbols": "600000.SH"}, "symbols must be an array"),
        ({"bars": [1]}, r"bars\[0\] must be an object"),
        ({"information_signals": ["buy"]}, r"information_signals\[0\]"),
        ({"information_provenance": []}, "information_provenance must be an object"),
        ({"unknown": 1}, "unknown production input fields"),
    ],
)
def test_shared_payload_schema_rejects_invalid_values(payload, message) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        normalize_production_input_payload(payload)


# ---------------------------------------------------------------------------
# 2. Old Path-to-load_runtime_manifest failure is eliminated.
# ---------------------------------------------------------------------------


def test_path_passed_to_bridge_not_to_load_runtime_manifest(tmp_path: Path) -> None:
    """The shared helper reads the file; callers never pass a Path to
    load_runtime_manifest directly."""
    manifest_path = _write_valid_manifest(tmp_path)
    # This must succeed — the bridge reads the file and passes a Mapping.
    config = load_production_pipeline_config(
        manifest_path=manifest_path,
        decision_session="2026-04-03",
        state_path=str(tmp_path / "state.json"),
        report_path=str(tmp_path / "report.json"),
    )
    assert config.target_symbol_count == 2


def test_raw_path_still_rejected_by_strict_loader() -> None:
    """Sanity: load_runtime_manifest itself still rejects a Path."""
    with pytest.raises(TypeError, match="ProductionCandidateManifest or mapping"):
        load_runtime_manifest(Path("/nonexistent/manifest.json"))


# ---------------------------------------------------------------------------
# 3. Manifest frozen parameters are actually applied to config.
# ---------------------------------------------------------------------------


def test_frozen_parameters_applied_to_pipeline_config(tmp_path: Path) -> None:
    manifest_path = _write_valid_manifest(tmp_path)
    config = load_production_pipeline_config(
        manifest_path=manifest_path,
        decision_session="2026-04-03",
    )
    assert config.initial_capital == 100000.0
    assert config.target_symbol_count == 2
    assert config.max_execution_symbols == 6
    assert config.target_position_count == 2
    assert config.max_position_weight == 0.1
    assert config.reserve_cash_weight == 0.02
    assert config.min_order_lot == 100
    assert config.strategy_id == "equal_weight_baseline"
    assert config.capital_profile_id == "default_paper_capital"


def test_frozen_params_override_dataclass_defaults(tmp_path: Path) -> None:
    """Frozen manifest values must be authoritative, not dataclass defaults."""
    manifest_path = _write_valid_manifest(
        tmp_path,
        frozen_strategy_parameters={
            "initial_capital": 250000.0,
            "target_symbol_count": 4,
            "max_execution_symbols": 5,
            "strategy_id": "equal_weight_baseline",
        },
        frozen_portfolio_parameters={
            "target_position_count": 4,
            "max_position_weight": 0.15,
            "reserve_cash_weight": 0.05,
        },
        frozen_execution_parameters={"min_order_lot": 200},
    )
    config = load_production_pipeline_config(
        manifest_path=manifest_path,
        decision_session="2026-04-03",
    )
    # Dataclass defaults: initial_capital=100000, max_execution_symbols=6,
    # target_symbol_count=1, max_position_weight=0.10, reserve_cash_weight=0.02,
    # min_order_lot=100.  All must be overridden by frozen values.
    assert config.initial_capital == 250000.0
    assert config.target_symbol_count == 4
    assert config.max_execution_symbols == 5
    assert config.max_position_weight == 0.15
    assert config.reserve_cash_weight == 0.05
    assert config.min_order_lot == 200


# ---------------------------------------------------------------------------
# 4. A conflicting caller override cannot replace frozen production values.
# ---------------------------------------------------------------------------


def test_frozen_params_are_authoritative_in_constructed_config(tmp_path: Path) -> None:
    """Once loaded, the RealCandidatePipelineConfig carries the frozen values
    and the production_manifest.  The pipeline itself will reject a runtime
    parameter that conflicts with a frozen value (via effective_parameter_payload)."""
    manifest_path = _write_valid_manifest(tmp_path)
    config = load_production_pipeline_config(
        manifest_path=manifest_path,
        decision_session="2026-04-03",
    )
    # The config was built from the manifest; the manifest is attached.
    assert config.production_manifest is not None
    # The manifest's frozen initial_capital is 100000; verify it is set.
    assert config.initial_capital == 100000.0
    # The effective_parameter_payload function (called by the pipeline) will
    # reject any runtime parameter that conflicts with a frozen value.
    from quantpilot_core.production_candidate import effective_parameter_payload

    runtime = {
        "initial_capital": 100000.0,
        "target_symbol_count": 2,
        "max_execution_symbols": 6,
        "target_position_count": 2,
        "max_position_weight": 0.1,
        "reserve_cash_weight": 0.02,
        "min_order_lot": 100,
        "strategy_id": "equal_weight_baseline",
        "capital_profile_id": "default_paper_capital",
    }
    # Matching runtime → OK.
    result = effective_parameter_payload(
        config.production_manifest, runtime_parameters=runtime
    )
    assert result["target_symbol_count"] == 2

    # Conflicting runtime → rejected.
    with pytest.raises(ProductionCandidateContractError, match="frozen parameter mismatch"):
        effective_parameter_payload(
            config.production_manifest,
            runtime_parameters={**runtime, "target_symbol_count": 99},
        )


@pytest.mark.parametrize("name", sorted(FROZEN_MANIFEST_PARAMETER_NAMES))
def test_pipeline_options_cannot_override_any_frozen_parameter(
    tmp_path: Path, name: str
) -> None:
    manifest_path = _write_valid_manifest(tmp_path)
    with pytest.raises(ValueError, match="frozen manifest parameters"):
        load_production_pipeline_config(
            manifest_path=manifest_path,
            decision_session="2026-04-03",
            pipeline_options={name: "caller-value"},
        )


def test_serialized_pipeline_options_become_runtime_contracts(tmp_path: Path) -> None:
    config = load_production_pipeline_config(
        manifest_path=_write_valid_manifest(tmp_path),
        decision_session="2026-04-03",
        pipeline_options={
            "input_calendar_sessions": ["2026-04-03", "2026-04-06"],
            "input_calendar_provider": "fixture",
            "account_capabilities": {
                "account_id": "paper-account",
                "supported_order_types": ["limit"],
            },
        },
    )
    assert config.input_calendar_sessions == ("2026-04-03", "2026-04-06")
    assert config.input_calendar_provider == "fixture"
    assert config.account_capabilities.account_id == "paper-account"
    assert config.account_capabilities.supported_order_types == ("limit",)


# ---------------------------------------------------------------------------
# 5. target_symbol_count > max_execution_symbols is rejected clearly.
# ---------------------------------------------------------------------------


def test_target_symbol_count_exceeds_max_execution_rejected(tmp_path: Path) -> None:
    manifest_path = _write_valid_manifest(
        tmp_path,
        frozen_strategy_parameters={
            "initial_capital": 100000.0,
            "target_symbol_count": 10,
            "max_execution_symbols": 6,
            "strategy_id": "equal_weight_baseline",
        },
    )
    with pytest.raises(ValueError, match="target_symbol_count.*exceeds max_execution_symbols"):
        load_production_pipeline_config(
            manifest_path=manifest_path,
            decision_session="2026-04-03",
        )


def test_compatible_target_and_max_symbols_are_accepted(tmp_path: Path) -> None:
    manifest_path = _write_valid_manifest(
        tmp_path,
        frozen_strategy_parameters={
            "initial_capital": 100000.0,
            "target_symbol_count": 6,
            "max_execution_symbols": 6,
            "strategy_id": "equal_weight_baseline",
        },
        frozen_portfolio_parameters={
            "target_position_count": 6,
            "max_position_weight": 0.1,
            "reserve_cash_weight": 0.02,
        },
    )
    config = load_production_pipeline_config(
        manifest_path=manifest_path,
        decision_session="2026-04-03",
    )
    assert config.target_symbol_count == 6
    assert config.max_execution_symbols == 6


# ---------------------------------------------------------------------------
# 6. Live mode without symbols is rejected.
# ---------------------------------------------------------------------------


def test_live_mode_without_symbols_rejected(tmp_path: Path) -> None:
    manifest_path = _write_valid_manifest(tmp_path)
    with pytest.raises(ValueError, match="live_market_data requires.*symbols"):
        load_production_pipeline_config(
            manifest_path=manifest_path,
            decision_session="2026-04-03",
            live_market_data=True,
            input_payload={"symbols": []},
        )


# ---------------------------------------------------------------------------
# 7. Live mode with explicit bounded symbol universe is forwarded.
# ---------------------------------------------------------------------------


def test_live_mode_with_bounded_symbols_is_forwarded(tmp_path: Path) -> None:
    manifest_path = _write_valid_manifest(tmp_path)
    config = load_production_pipeline_config(
        manifest_path=manifest_path,
        decision_session="2026-04-03",
        live_market_data=True,
        input_payload={"symbols": ["sh.600000", "000001"]},
    )
    assert config.live_market_data is True
    assert config.symbols == ("600000.SH", "000001.SZ")
    assert len(config.symbols) <= config.max_execution_symbols


def test_live_mode_rejects_more_than_six_normalized_symbols(tmp_path: Path) -> None:
    manifest_path = _write_valid_manifest(tmp_path)
    with pytest.raises(ValueError, match="at most 6"):
        load_production_pipeline_config(
            manifest_path=manifest_path,
            decision_session="2026-04-03",
            live_market_data=True,
            input_payload={
                "symbols": [
                    "600000.SH",
                    "600001.SH",
                    "600002.SH",
                    "600003.SH",
                    "600004.SH",
                    "600005.SH",
                    "600006.SH",
                ]
            },
        )


# ---------------------------------------------------------------------------
# 8. Offline mode remains deterministic and offline-safe.
# ---------------------------------------------------------------------------


def test_offline_mode_no_live_market_data_by_default(tmp_path: Path) -> None:
    manifest_path = _write_valid_manifest(tmp_path)
    config = load_production_pipeline_config(
        manifest_path=manifest_path,
        decision_session="2026-04-03",
    )
    assert config.live_market_data is False
    assert config.symbols == ()
    assert config.input_bars == ()


def test_offline_mode_with_input_bars_stays_offline(tmp_path: Path) -> None:
    manifest_path = _write_valid_manifest(tmp_path)
    bars = (
        {
            "symbol": "600000.SH",
            "date": "2026-04-03",
            "open": 10.0,
            "high": 10.5,
            "low": 9.8,
            "close": 10.2,
            "previous_close": 10.0,
            "volume": 100000.0,
            "amount": 1020000.0,
            "is_suspended": False,
            "provider": "test",
        },
    )
    config = load_production_pipeline_config(
        manifest_path=manifest_path,
        decision_session="2026-04-03",
        live_market_data=False,
        input_payload={"bars": list(bars)},
    )
    assert config.live_market_data is False
    assert len(config.input_bars) == 1


# ---------------------------------------------------------------------------
# 9. Active shadow remains non-authoritative.
# ---------------------------------------------------------------------------


def test_shadow_desk_evidence_is_forwarded_but_not_authoritative(tmp_path: Path) -> None:
    manifest_path = _write_valid_manifest(tmp_path)
    shadow = {"desk_vote": "abstain", "recommendation": "hold"}
    config = load_production_pipeline_config(
        manifest_path=manifest_path,
        decision_session="2026-04-03",
        pipeline_options={"shadow_desk_evidence": shadow},
    )
    # Shadow evidence is stored but never drives the production config.
    assert config.shadow_desk_evidence == shadow
    # Production execution arm must remain non_llm_baseline (enforced by
    # the manifest, not by shadow evidence).
    manifest = load_runtime_manifest(
        json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    )
    assert manifest.production_execution_arm == "non_llm_baseline"


# ---------------------------------------------------------------------------
# 10. No broker/order-submission path is enabled.
# ---------------------------------------------------------------------------


def test_no_broker_execution_path_in_pipeline_config(tmp_path: Path) -> None:
    """RealCandidatePipelineConfig has no broker/order fields — execution is
    paper-only by construction."""
    manifest_path = _write_valid_manifest(tmp_path)
    config = load_production_pipeline_config(
        manifest_path=manifest_path,
        decision_session="2026-04-03",
    )
    # Verify there is no broker-related attribute.
    for attr in dir(config):
        assert "broker" not in attr.lower()
        assert "order_submit" not in attr.lower()
        assert "live_trading" not in attr.lower()


def test_broker_provider_remains_none_in_manifest(tmp_path: Path) -> None:
    """The production manifest enforces non_llm_baseline execution arm."""
    manifest_path = _write_valid_manifest(tmp_path)
    manifest = load_runtime_manifest(
        json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    )
    assert manifest.production_execution_arm == "non_llm_baseline"
    # Any attempt to use a live execution arm is rejected at manifest level.
    sub = tmp_path / "sub"
    sub.mkdir()
    with pytest.raises(ProductionCandidateContractError, match="non_llm_baseline"):
        _write_valid_manifest(
            sub,
            production_execution_arm="live_broker",
        )
