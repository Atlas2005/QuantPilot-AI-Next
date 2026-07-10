"""Point-in-time research-universe helpers, independent of execution permissions."""
from __future__ import annotations
from typing import Any, Mapping, Sequence

def is_listed_on(row: Mapping[str, Any], trade_date: str) -> bool:
    listed = str(row.get("list_date") or "")
    delisted = str(row.get("delist_date") or "")
    return bool(listed and listed <= trade_date and (not delisted or trade_date <= delisted))

def listed_universe(rows: Sequence[Mapping[str, Any]], trade_date: str) -> tuple[Mapping[str, Any], ...]:
    return tuple(sorted((row for row in rows if is_listed_on(row, trade_date)), key=lambda r: str(r.get("ts_code", ""))))
