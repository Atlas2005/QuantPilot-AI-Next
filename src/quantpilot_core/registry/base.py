"""Minimal in-memory registry placeholder for Phase 0B."""

from collections.abc import Mapping
from typing import Any


class SimpleRegistry:
    """Small in-memory registry for names and metadata."""

    def __init__(self) -> None:
        self._items: dict[str, dict[str, Any]] = {}

    def register(self, name: str, metadata: Mapping[str, Any]) -> None:
        self._items[name] = dict(metadata)

    def get(self, name: str) -> dict[str, Any]:
        return dict(self._items[name])

    def list_names(self) -> list[str]:
        return sorted(self._items)

