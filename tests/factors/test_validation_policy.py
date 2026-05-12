import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "data" / "factor_validation" / "validation_metric_policy.json"


def test_validation_metric_policy_loads() -> None:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))

    assert policy["policy_name"] == "phase_7b_factor_validation_metric_policy"


def test_validation_metric_policy_keeps_claims_disabled() -> None:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))

    assert policy["alpha_claim_allowed"] is False
    assert policy["trading_ready"] is False


def test_validation_metric_policy_requires_later_evidence() -> None:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))

    assert policy["oos_required_later"] is True
    assert policy["walk_forward_required_later"] is True
    assert policy["paper_feedback_required_later"] is True
    assert policy["transaction_cost_required_later"] is True
    assert policy["a_share_rule_required_later"] is True


def test_validation_metric_policy_defers_external_libraries() -> None:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    deferred = set(policy["deferred_external_libraries"])

    assert policy["approved_external_libraries"] == []
    assert "Alphalens Reloaded" in deferred
    assert "quantstats" in deferred
    assert "empyrical / empyrical-reloaded" in deferred
    assert "Qlib" in deferred
