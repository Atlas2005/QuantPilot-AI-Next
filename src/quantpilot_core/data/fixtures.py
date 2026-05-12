"""Helpers for locating local fixture files."""

from pathlib import Path


def get_sample_fixture_path(name: str) -> Path:
    """Return the repository-local fixture path for a known fixture name."""

    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / "data" / "fixtures" / name

