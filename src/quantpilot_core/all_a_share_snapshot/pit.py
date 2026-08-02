"""Point-in-time research-universe helpers, independent of execution permissions."""
from __future__ import annotations
from typing import Any, Mapping, Sequence

def is_listed_on(row: Mapping[str, Any], trade_date: str) -> bool:
    listed = str(row.get("list_date") or "")
    delisted = str(row.get("delist_date") or "")
    return bool(listed and listed <= trade_date and (not delisted or trade_date <= delisted))


def is_historical_code_active(resolution: Mapping[str, Any], trade_date: str) -> bool:
    """Return whether a resolved historical exchange code is active on a date."""
    effective = str(resolution.get("effective_date") or "")
    valid_from = str(resolution.get("historical_valid_from") or "")
    return (
        resolution.get("resolution_status") == "resolved"
        and len(effective) == 8 and effective.isdigit()
        and trade_date < effective
        and (not valid_from or valid_from <= trade_date)
    )


def stable_instrument_identity(
    ts_code: str, resolutions: Mapping[str, Mapping[str, Any]],
) -> str:
    """Resolve either side of a code transition to the same opaque identity."""
    direct = resolutions.get(ts_code, {})
    if direct.get("resolution_status") == "resolved" and direct.get("stable_instrument_id"):
        return str(direct["stable_instrument_id"])
    for item in resolutions.values():
        if (
            item.get("resolution_status") == "resolved"
            and item.get("current_ts_code") == ts_code
            and item.get("stable_instrument_id")
        ):
            return str(item["stable_instrument_id"])
    return f"a_share_security:{ts_code}"


def listed_universe(
    rows: Sequence[Mapping[str, Any]],
    trade_date: str,
    resolutions: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[Mapping[str, Any], ...]:
    """Build the exchange-code universe active on ``trade_date``.

    ``stock_basic`` is a current security master.  A verified transition may
    therefore need to expose the historical code before its effective date.
    The successor is never emitted early, and only one code is emitted for an
    issuer at a time.
    """
    transitions: dict[str, list[Mapping[str, Any]]] = {}
    for item in (resolutions or {}).values():
        current = str(item.get("current_ts_code") or "")
        if item.get("resolution_status") == "resolved" and current:
            transitions.setdefault(current, []).append(item)

    output: list[Mapping[str, Any]] = []
    for row in rows:
        current = str(row.get("ts_code") or "")
        active_aliases = [
            item
            for item in transitions.get(current, ())
            if is_historical_code_active(item, trade_date)
        ]
        if active_aliases:
            # For chained transitions, the nearest future boundary identifies
            # the code active at this point in time.  One stock-master row still
            # produces exactly one security code.
            item = min(active_aliases, key=lambda value: str(value["effective_date"]))
            historical = str(item["historical_ts_code"])
            alias = dict(row)
            alias["ts_code"] = historical
            alias["symbol"] = historical.partition(".")[0]
            alias["list_date"] = str(item.get("historical_valid_from") or row.get("list_date") or "")
            name = _historical_name(item, trade_date)
            if name:
                alias["name"] = name
            output.append(alias)
            continue
        if is_listed_on(row, trade_date):
            output.append(row)
    return tuple(sorted(output, key=lambda value: str(value.get("ts_code", ""))))


def _historical_name(resolution: Mapping[str, Any], trade_date: str) -> str | None:
    for period in resolution.get("name_history_periods", ()):
        start = str(period.get("start_date") or "")
        end = str(period.get("end_date") or "")
        if start and start <= trade_date and (not end or trade_date <= end):
            name = str(period.get("name") or "")
            return name or None
    return None
