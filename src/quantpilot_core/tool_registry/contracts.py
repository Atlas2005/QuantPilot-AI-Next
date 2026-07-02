"""Typed contracts for deterministic local QuantPilot tools."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any


class ToolSideEffectLevel(str, Enum):
    """Declared side-effect boundary for a registered tool."""

    PURE_IN_MEMORY = "pure_in_memory"


@dataclass(frozen=True)
class ToolExecutionResult:
    """Structured result returned by registry-mediated tool execution."""

    ok: bool
    tool_name: str
    side_effect_level: ToolSideEffectLevel
    output: Any | None = None
    error: str | None = None
    error_type: str | None = None


@dataclass(frozen=True)
class QuantPilotTool:
    """A narrow callable tool contract for deterministic local compute."""

    name: str
    description: str
    callable: Callable[..., Any]
    side_effect_level: ToolSideEffectLevel = ToolSideEffectLevel.PURE_IN_MEMORY

    def execute(self, **kwargs: Any) -> ToolExecutionResult:
        """Execute the wrapped callable and capture failures as data."""

        try:
            output = self.callable(**kwargs)
        except Exception as exc:
            return ToolExecutionResult(
                ok=False,
                tool_name=self.name,
                side_effect_level=self.side_effect_level,
                error=str(exc),
                error_type=type(exc).__name__,
            )
        return ToolExecutionResult(
            ok=True,
            tool_name=self.name,
            side_effect_level=self.side_effect_level,
            output=output,
        )


class ToolRegistry:
    """Deterministic in-memory registry for QuantPilot tools."""

    def __init__(self, tools: tuple[QuantPilotTool, ...] = ()) -> None:
        self._tools: dict[str, QuantPilotTool] = {}
        for tool in tools:
            self.register(tool)

    def register(self, tool: QuantPilotTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> QuantPilotTool:
        return self._tools[name]

    def list_tools(self) -> tuple[QuantPilotTool, ...]:
        return tuple(self._tools[name] for name in sorted(self._tools))

    def list_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))

    def execute(self, name: str, **kwargs: Any) -> ToolExecutionResult:
        try:
            tool = self.get(name)
        except KeyError:
            return ToolExecutionResult(
                ok=False,
                tool_name=name,
                side_effect_level=ToolSideEffectLevel.PURE_IN_MEMORY,
                error=f"unknown tool: {name}",
                error_type="KeyError",
            )
        return tool.execute(**kwargs)
