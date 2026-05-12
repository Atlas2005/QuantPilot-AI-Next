"""Minimal base contract placeholder for Phase 0B."""

from dataclasses import dataclass


@dataclass(frozen=True)
class BaseContract:
    """Small descriptive contract placeholder.

    This is intentionally generic. Domain-specific contracts belong to later
    phases after ChatGPT-led review.
    """

    name: str
    version: str = "0.0.1"

    def describe(self) -> dict[str, str]:
        """Return a serializable description of the contract."""

        return {"name": self.name, "version": self.version}

