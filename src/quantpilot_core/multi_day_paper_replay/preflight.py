"""Input validation for R23 multi-day paper replay."""

from __future__ import annotations

from datetime import date
from typing import Iterable

from quantpilot_core.account_profile_preflight import (
    AccountProfile,
    RiskSeverity as AccountRiskSeverity,
    run_account_profile_preflight,
)
from quantpilot_core.multi_day_paper_replay.contracts import (
    PaperReplayDayInput,
    PaperReplayRiskFlag,
    RiskSeverity,
)


def validate_replay_inputs(
    days: Iterable[PaperReplayDayInput],
    account_profile: AccountProfile,
) -> tuple[PaperReplayRiskFlag, ...]:
    """Validate replay shape before daily dry-run orchestration."""

    day_inputs = tuple(days)
    flags: list[PaperReplayRiskFlag] = []
    account_preflight = run_account_profile_preflight(account_profile)
    if not account_preflight.ok:
        flags.extend(
            _critical(
                f"account_preflight:{flag.code}",
                f"Account preflight failed: {flag.message}",
            )
            for flag in account_preflight.risk_flags
            if flag.severity == AccountRiskSeverity.CRITICAL.value
        )

    previous_date: date | None = None
    seen_dates: set[str] = set()
    seen_proposal_ids: set[str] = set()
    for day_index, day in enumerate(day_inputs):
        if not day.trading_date.strip():
            flags.append(_critical(f"day[{day_index}]:trading_date_missing", "Trading date is required."))
            continue
        parsed_date = _parse_strict_iso_date(day.trading_date)
        if parsed_date is None:
            flags.append(
                _critical(
                    f"day[{day_index}]:trading_date_invalid",
                    "Trading date must use YYYY-MM-DD.",
                )
            )
            continue
        if day.trading_date in seen_dates:
            flags.append(_critical("duplicate_trading_date", "Duplicate trading_date is not allowed."))
        seen_dates.add(day.trading_date)
        if previous_date is not None and parsed_date <= previous_date:
            flags.append(
                _critical(
                    "trading_dates_not_strictly_increasing",
                    "Replay days must be strictly increasing by trading_date.",
                )
            )
        previous_date = parsed_date

        for instruction in day.instructions:
            proposal_id = instruction.proposal_id
            if proposal_id in seen_proposal_ids:
                flags.append(
                    _critical(
                        "duplicate_proposal_id_across_replay",
                        "Duplicate proposal_id across replay is not allowed.",
                    )
                )
            seen_proposal_ids.add(proposal_id)

    return tuple(flags)


def _parse_strict_iso_date(value: str) -> date | None:
    if len(value) != 10 or value[4] != "-" or value[7] != "-":
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _critical(code: str, message: str) -> PaperReplayRiskFlag:
    return PaperReplayRiskFlag(
        code=code,
        severity=RiskSeverity.CRITICAL.value,
        message=message,
    )
