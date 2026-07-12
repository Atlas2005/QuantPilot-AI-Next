from __future__ import annotations

from pathlib import Path

import pytest
from quantpilot_core.evaluation.deepseek_multi_agent_incremental_ablation import IncrementalAblationConfig, build_live_evidence, run_deepseek_multi_agent_incremental_ablation_v1
from quantpilot_core.quant_firm.deepseek_advisory import DeepSeekStructuredEvidenceClient, create_live_structured_evidence_client


def _artifact():
    rows = lambda total, excess: [{"fold_id": "fold-1", "status": "completed", "total_return": total, "benchmark_total_return": .01, "strategy_excess_return": excess, "max_drawdown": -.02, "turnover": 2, "cost_total": 1, "filled_trades": 2, "rejected_trades": 0, "validation_range": ("2024-01-01", "2024-01-10")}]
    return {"common_folds": [{"fold_id": "fold-1", "validation_end": "2024-01-10", "test_start": "2024-01-11"}], "per_candidate_fold_metrics": {"a": rows(.02, .01), "b": rows(.03, .02)}, "selection_history": [{"fold_id": "fold-1", "selected_candidate": "a"}]}


def _evidence(score_b=1):
    roles = ("investment_committee", "research_desk", "information_desk", "backtest_desk", "portfolio_desk", "execution_simulation_desk")
    return {"fold-1": {role: {"candidate_scores": {"a": 0, "b": score_b}, "preferred_candidate": "b", "abstain": False, "confidence": .8, "parameter_adjustments": {"reserve_cash_weight": .4}, "input_tokens": 100, "cache_hit_input_tokens": 20, "output_tokens": 10, "model": "deepseek-v4-flash"} for role in roles}}


def test_offline_replay_is_pit_safe_and_reuses_role_outputs():
    report = run_deepseek_multi_agent_incremental_ablation_v1(IncrementalAblationConfig(pr121_artifact=_artifact(), advisory_evidence=_evidence(), artifact_path=None))
    assert report.mode == "offline_replay"
    assert report.decision_packets[0]["uses_test_outcomes"] is False
    assert report.decision_packets[0]["evidence_before_test"] is True
    assert report.decisions["single_agent"][0]["selected_candidate"] == "b"
    assert report.decisions["multi_agent_independent"][0]["selected_candidate"] == "b"
    assert report.decisions["multi_agent_committee"][0]["selected_candidate"] == "b"
    assert report.usage["logical_role_evaluations"] == 6
    assert report.usage["physical_model_calls"] == 0
    assert report.role_outputs["fold-1"]["research_desk"]["adjustment_audit"]["accepted"]["reserve_cash_weight"] == .4


def test_missing_or_invalid_role_evidence_only_blocks_affected_ai_arm():
    evidence = _evidence(); evidence["fold-1"].pop("information_desk"); evidence["fold-1"]["investment_committee"]["candidate_scores"] = {"a": 1, "b": 1}
    report = run_deepseek_multi_agent_incremental_ablation_v1(IncrementalAblationConfig(pr121_artifact=_artifact(), advisory_evidence=evidence, artifact_path=None))
    assert report.arm_metrics["non_llm_baseline"]["available"] is True
    assert report.arm_metrics["single_agent"]["available"] is False
    assert report.arm_metrics["multi_agent_independent"]["available"] is False


def test_deterministic_digest_and_api_cost_are_stable():
    config = IncrementalAblationConfig(pr121_artifact=_artifact(), advisory_evidence=_evidence(), artifact_path=None)
    first, second = run_deepseek_multi_agent_incremental_ablation_v1(config), run_deepseek_multi_agent_incremental_ablation_v1(config)
    assert first.decision_packets[0]["packet_digest"] == second.decision_packets[0]["packet_digest"]
    assert first.usage["provider_cache_hit_input_tokens"] == 120
    assert first.arm_metrics["single_agent"]["estimated_api_cost"] > 0


def test_live_plan_is_bounded_and_cache_reuse_avoids_duplicate_calls(tmp_path):
    calls = []
    def fake(request):
        calls.append(request)
        return {"content": '{"candidate_scores":{"a":0,"b":1},"preferred_candidate":"b","confidence":0.8,"abstain":false,"parameter_adjustments":{}}', "finish_reason": "stop", "usage": {"prompt_tokens": 12, "prompt_cache_hit_tokens": 3, "completion_tokens": 4}}
    config = IncrementalAblationConfig(pr121_artifact=_artifact(), artifact_path=None)
    generated = build_live_evidence(config, fake, tmp_path, 6)
    assert len(calls) == 6
    assert generated["fold-1"]["research_desk"]["input_cache_miss_tokens"] == 9
    assert build_live_evidence(config, fake, tmp_path, 6)["fold-1"]
    assert len(calls) == 6
    with pytest.raises(ValueError, match="before call 1"):
        build_live_evidence(config, fake, tmp_path / "new", 1)


def test_evaluation_is_credential_agnostic_and_adapter_is_quant_firm_owned():
    evaluation_source = Path("src/quantpilot_core/evaluation/deepseek_multi_agent_incremental_ablation.py").read_text()
    cli_source = Path("scripts/run_deepseek_multi_agent_incremental_ablation_v1.py").read_text()
    assert "api_key" not in evaluation_source.lower()
    assert "openai" not in evaluation_source.lower()
    assert "os.environ" not in evaluation_source
    assert "create_live_structured_evidence_client" in cli_source
    assert isinstance(create_live_structured_evidence_client(), DeepSeekStructuredEvidenceClient)


def test_offline_replay_does_not_invoke_an_injected_client():
    calls = []

    def fake(_request):
        calls.append(_request)
        raise AssertionError("offline replay must not invoke a client")

    report = run_deepseek_multi_agent_incremental_ablation_v1(
        IncrementalAblationConfig(pr121_artifact=_artifact(), advisory_evidence=_evidence(), artifact_path=None)
    )
    assert report.mode == "offline_replay"
    assert calls == []


@pytest.mark.parametrize("raw", [{"candidate_scores":{"z":1},"preferred_candidate":"z","confidence":.5,"abstain":False}, {"candidate_scores":{"a":True,"b":1},"preferred_candidate":"b","confidence":.5,"abstain":False}, {"candidate_scores":{"a":0,"b":1},"preferred_candidate":"b","confidence":2,"abstain":False}])
def test_strict_invalid_structured_outputs_are_unavailable(raw):
    evidence = {"fold-1": {"investment_committee": raw}}
    report = run_deepseek_multi_agent_incremental_ablation_v1(IncrementalAblationConfig(pr121_artifact=_artifact(), advisory_evidence=evidence, artifact_path=None))
    assert report.arm_metrics["single_agent"]["available"] is False
