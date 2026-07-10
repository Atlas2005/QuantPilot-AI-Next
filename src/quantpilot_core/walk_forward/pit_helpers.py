"""Point-in-time helpers shared across walk-forward and daily evaluation."""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping


def rows_through_execution(
    rows: tuple[Mapping[str, Any], ...], execution: date
) -> tuple[Mapping[str, Any], ...]:
    """Return rows with ``date <= execution`` (D+1 inclusive).

    Canonical single implementation.  Used by:
    * ``daily_evaluation.evaluator``
    * ``walk_forward.canonical_baseline``
    """
    return tuple(
        row for row in rows
        if date.fromisoformat(str(row["date"])) <= execution
    )
