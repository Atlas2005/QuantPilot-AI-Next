"""Agent skill contract boundary."""

from dataclasses import dataclass, field

from quantpilot_core.contracts.base import BaseContract


@dataclass(frozen=True)
class AgentSkillContract(BaseContract):
    """Interface shape for later-stage agent skill boundaries.

    This is not agent orchestration and does not call an LLM framework.
    """

    allowed_tools: tuple[str, ...] = field(default_factory=tuple)
    human_review_policy: tuple[str, ...] = (
        "Agent orchestration is later-stage only.",
        "Human review is required before any future operational workflow.",
    )

    def list_allowed_tools(self) -> list[str]:
        return list(self.allowed_tools)

    def explain_human_review_policy(self) -> list[str]:
        return list(self.human_review_policy)

