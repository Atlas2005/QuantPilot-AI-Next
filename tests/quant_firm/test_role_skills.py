from __future__ import annotations

from quantpilot_core.quant_firm import (
    DeepSeekAdvisoryRole,
    QuantFirmRoleSkill,
    QuantFirmRoleSkillRegistry,
    build_default_role_skill_registry,
)
from quantpilot_core.tool_registry import ToolSideEffectLevel, build_default_tool_registry


def test_every_deepseek_advisory_role_has_mapped_and_enabled_skills() -> None:
    registry = build_default_role_skill_registry()

    assert registry.validate_each_role_has_useful_skill() == ()
    for role in DeepSeekAdvisoryRole:
        assert registry.list_by_role(role)
        assert registry.list_enabled_skills(role)
        assert all(skill.role is role for skill in registry.list_by_role(role))


def test_no_broker_or_live_skill_is_enabled_by_default() -> None:
    registry = build_default_role_skill_registry()

    assert registry.validate_no_broker_live_enabled_by_default() == ()
    enabled_text = " ".join(
        f"{skill.skill_name} {skill.tool_name} {skill.source_layer} {skill.purpose}"
        for skill in registry.list_enabled_skills()
    ).lower()
    assert "broker" not in enabled_text
    assert "live_trading" not in enabled_text
    assert "live trading" not in enabled_text


def test_deepseek_advisory_skills_have_no_direct_broker_or_live_binding() -> None:
    registry = build_default_role_skill_registry()
    deepseek_skills = tuple(
        skill
        for skill in registry.list_skills()
        if skill.tool_name == "run_deepseek_advisory_fallback"
    )

    assert deepseek_skills
    assert registry.validate_deepseek_has_no_direct_broker_live_skill() == ()
    assert all(skill.enabled_by_default for skill in deepseek_skills)


def test_mature_framework_labels_cover_current_adapter_layers() -> None:
    labels = {
        skill.mature_framework
        for skill in build_default_role_skill_registry().list_skills()
        if skill.mature_framework is not None
    }

    assert "qlib_artifact_adapter" in labels
    assert "vectorbt_adapter" in labels
    assert "vectorbt_order_intent_adapter" in labels
    assert "rqalpha_artifact_adapter" in labels
    assert "rqalpha_order_intent_adapter" in labels
    assert "backtrader_order_intent_adapter" in labels
    assert "paper_trading_loop" in labels
    assert "walk_forward_paper_evaluation" in labels
    assert "mlflow_style_in_memory_experiment_tracking" in labels
    assert "deepseek_advisory_fallback" in labels


def test_enabled_skills_reference_known_tool_registry_tools_and_placeholders_are_disabled() -> None:
    role_registry = build_default_role_skill_registry()
    tool_registry = build_default_tool_registry()

    assert role_registry.validate_known_tools_or_disabled_placeholders(tool_registry.list_names()) == ()
    known = set(tool_registry.list_names())
    placeholders = tuple(skill for skill in role_registry.list_skills() if skill.tool_name not in known)

    assert placeholders
    assert all(not skill.enabled_by_default for skill in placeholders)
    assert {skill.tool_name for skill in placeholders} == {
        "backtrader_order_intent_adapter_placeholder",
        "build_rqalpha_isolated_prototype_runner_review_report",
        "evaluate_cost_after_fill",
        "learning_desk_outputs",
        "rqalpha_order_intent_adapter_placeholder",
    }


def test_role_skill_registry_lists_enabled_skills_by_role() -> None:
    skill = QuantFirmRoleSkill(
        role=DeepSeekAdvisoryRole.PORTFOLIO_DESK,
        skill_name="portfolio_test_skill",
        tool_name="build_portfolio_allocation_plan",
        source_layer="execution_optimizer",
        purpose="Test skill.",
        side_effect_level=ToolSideEffectLevel.PURE_IN_MEMORY,
        mature_framework="internal_exec2_optimizer",
        enabled_by_default=True,
    )
    disabled = QuantFirmRoleSkill(
        role=DeepSeekAdvisoryRole.PORTFOLIO_DESK,
        skill_name="disabled_test_skill",
        tool_name="future_tool",
        source_layer="future",
        purpose="Disabled future placeholder.",
        side_effect_level=ToolSideEffectLevel.PURE_IN_MEMORY,
        mature_framework=None,
        enabled_by_default=False,
    )
    registry = QuantFirmRoleSkillRegistry((skill, disabled))

    assert registry.list_by_role("portfolio_desk") == (skill, disabled)
    assert registry.list_enabled_skills(DeepSeekAdvisoryRole.PORTFOLIO_DESK) == (skill,)
