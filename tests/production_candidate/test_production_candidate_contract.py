from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from quantpilot_core.production_candidate import (
    build_production_candidate_manifest,
    effective_parameter_digest,
    effective_parameter_payload,
    manifest_payload,
    load_runtime_manifest,
    verify_manifest_digest,
)
from quantpilot_core.quant_firm import CANONICAL_DEEPSEEK_DESKS, build_quant_firm_operating_contract, build_shadow_committee_report


def _valid_runtime_manifest(tmp_path, **overrides):
    a = tmp_path / "pr121.json"; a.write_text("{}")
    b = tmp_path / "pr122.json"; b.write_text("{}")
    values = dict(created_at="2026-07-12T00:00:00+00:00", code_revision="revision", snapshot_digest="a" * 64, benchmark={"symbol": "000300.SH"}, source_artifacts={"pr121": a, "pr122": b}, frozen_strategy_parameters={"initial_capital": 100000.0, "target_symbol_count": 2, "max_execution_symbols": 6, "strategy_id": "equal_weight_baseline"}, frozen_portfolio_parameters={"target_position_count": 2, "max_position_weight": .1, "reserve_cash_weight": .02}, frozen_execution_parameters={"min_order_lot": 100}, fee_profile_policy={"profile_id": "engineering-default", "required_provenance": "engineering_fallback"}, account_capability_policy={"capability_digest": "null"})
    values.update(overrides)
    return build_production_candidate_manifest(**values)


def test_manifest_is_compact_deterministic_and_digest_verified(tmp_path) -> None:
    first = _valid_runtime_manifest(tmp_path)
    second = _valid_runtime_manifest(tmp_path)
    assert first.manifest_digest == second.manifest_digest
    assert verify_manifest_digest(first)
    payload = manifest_payload(first)
    assert payload["strategy_candidate_id"] == "equal_weight_baseline"
    assert payload["production_execution_arm"] == "non_llm_baseline"
    assert payload["ai_firm_mode"] == "shadow_bound"
    assert 'recommendation' not in str(payload["source_artifacts"])


def test_effective_parameters_reject_frozen_mismatch(tmp_path) -> None:
    manifest = _valid_runtime_manifest(tmp_path)
    runtime = {"target_position_count": 2, "target_symbol_count": 2, "max_execution_symbols": 6, "max_position_weight": .1, "reserve_cash_weight": .02, "min_order_lot": 100, "initial_capital": 100000, "strategy_id": "equal_weight_baseline", "capital_profile_id": "default_paper_capital"}
    assert effective_parameter_payload(manifest, runtime_parameters=runtime)["target_position_count"] == 2
    assert len(effective_parameter_digest(manifest, runtime_parameters=runtime)) == 64
    try:
        effective_parameter_payload(manifest, runtime_parameters={**runtime, "target_position_count": 3})
    except ValueError as exc:
        assert "frozen parameter mismatch" in str(exc)
    else:
        raise AssertionError("frozen mismatch must fail")


def test_runtime_loader_rejects_incomplete_or_unknown_manifest() -> None:
    for bad in ({"schema_version": "production_candidate_v1"}, {"unknown": "field"}):
        try: load_runtime_manifest(bad)
        except ValueError: pass
        else: raise AssertionError("invalid runtime manifest accepted")


def test_complete_valid_runtime_manifest_strict_loads(tmp_path) -> None:
    assert load_runtime_manifest(_valid_runtime_manifest(tmp_path)).strategy_candidate_id == "equal_weight_baseline"


def test_runtime_manifest_rejects_pre_pr123_shadow_mode(tmp_path) -> None:
    manifest = dict(manifest_payload(_valid_runtime_manifest(tmp_path)))
    manifest["ai_firm_mode"] = "active" + "_shadow"
    try:
        load_runtime_manifest(manifest)
    except ValueError as exc:
        assert "shadow_bound" in str(exc)
    else:
        raise AssertionError("pre-PR #123 shadow mode accepted")


def test_empty_benchmark_is_rejected(tmp_path) -> None:
    try: _valid_runtime_manifest(tmp_path, benchmark={})
    except ValueError as exc: assert "benchmark" in str(exc)
    else: raise AssertionError("empty benchmark accepted")


def _cli_artifacts(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    pr121 = tmp_path / "pr121.json"; pr121.write_text(json.dumps({"run_status": "completed", "recommendation": "equal_weight_baseline", "common_folds": [{"id": 1}]}))
    pr122 = tmp_path / "pr122.json"; pr122.write_text(json.dumps({"mode": "offline_replay", "recommendation": "no_ai_arm", "usage": {"physical_model_calls": 0}}))
    return pr121, pr122


def _cli_args(tmp_path, benchmark=None):
    pr121, pr122 = _cli_artifacts(tmp_path); output = tmp_path / "manifest.json"
    args = [sys.executable, "scripts/build_production_candidate_manifest_v1.py", "--pr121-artifact", str(pr121), "--pr122-artifact", str(pr122), "--output", str(output), "--code-revision", "revision", "--created-at", "2026-07-12T00:00:00+00:00", "--snapshot-digest", "a" * 64, "--initial-capital", "100000", "--target-symbol-count", "2", "--target-position-count", "2", "--max-execution-symbols", "6", "--max-position-weight", "0.1", "--reserve-cash-weight", "0.02", "--min-order-lot", "100", "--fee-policy-json", '{"profile_id":"engineering-default","required_provenance":"engineering_fallback"}', "--account-policy-json", '{"capability_digest":"null"}']
    if benchmark is not None: args += ["--benchmark-json", benchmark]
    return args, output


def test_cli_missing_benchmark_json_fails(tmp_path) -> None:
    args, _ = _cli_args(tmp_path)
    assert subprocess.run(args, capture_output=True, text=True).returncode != 0


def test_cli_rejects_malformed_empty_and_nonobject_benchmark(tmp_path) -> None:
    for value in ("{", "{}", "[]", '"x"', "1", "null"):
        args, _ = _cli_args(tmp_path / value.replace("{", "bad"), value)
        assert subprocess.run(args, capture_output=True, text=True).returncode != 0


def test_cli_writes_exact_benchmark_and_strict_manifest(tmp_path) -> None:
    benchmark = '{"symbol":"000300.SH","kind":"index"}'
    args, output = _cli_args(tmp_path, benchmark)
    assert subprocess.run(args, capture_output=True, text=True).returncode == 0
    payload = json.loads(output.read_text())
    assert payload["benchmark"] == json.loads(benchmark)
    assert load_runtime_manifest(payload).manifest_digest == payload["manifest_digest"]


def test_cli_rejects_failed_top_level_pr121_even_with_nested_completed(tmp_path) -> None:
    args, _ = _cli_args(tmp_path, '{"symbol":"000300.SH"}')
    path = Path(args[args.index("--pr121-artifact") + 1])
    path.write_text(json.dumps({"run_status": "failed", "nested": {"run_status": "completed"}, "recommendation": "equal_weight_baseline", "common_folds": [1]}))
    assert subprocess.run(args, capture_output=True, text=True).returncode != 0


def test_seven_desk_contract_and_missing_evidence_abstain() -> None:
    contract = build_quant_firm_operating_contract()
    assert contract.ai_firm_mode == "shadow_bound"
    assert tuple(desk.role for desk in contract.desks) == CANONICAL_DEEPSEEK_DESKS
    assert all(not desk.may_influence_production_execution for desk in contract.desks)
    shadow = build_shadow_committee_report(
        evidence={},
        execution_timestamp="2026-07-12T09:30:00+08:00",
        production_final_recommendation="approve_offline_shadow_cycle",
    )
    assert shadow["status"] == "shadow_bound"
    assert shadow["ai_firm_mode"] == "shadow_bound"
    assert shadow["shadow_committee_decision"]["decision"] == "abstain"
    assert shadow["order_mutation"] is False
    assert shadow["account_state_mutation"] is False
