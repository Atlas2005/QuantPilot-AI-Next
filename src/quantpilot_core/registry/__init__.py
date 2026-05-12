"""Registry placeholders for QuantPilot-AI 2.0."""

from quantpilot_core.registry.base import SimpleRegistry
from quantpilot_core.registry.candidate import CandidateMetadata
from quantpilot_core.registry.candidate_loader import (
    CandidateRegistryError,
    load_candidate_registry,
)

__all__ = [
    "CandidateMetadata",
    "CandidateRegistryError",
    "SimpleRegistry",
    "load_candidate_registry",
]
