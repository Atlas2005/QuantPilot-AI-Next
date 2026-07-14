"""Explicitly non-mutating facade over the snapshot reader."""

from __future__ import annotations

from datetime import datetime
from typing import NoReturn

from .errors import OrderSubmissionNotEnabledError, ReadOnlyBridgeError
from .reader import QmtBuiltinBridgeReader
from .records import QmtBridgeSnapshot


class QmtBuiltinReadOnlyBridge:
    """Expose snapshots while making every broker-mutation attempt fail closed."""

    _SUBMISSION_METHODS = frozenset(
        {
            "submit_order",
            "place_order",
            "send_order",
            "execute_order",
            "passorder",
        }
    )
    _CANCELLATION_METHODS = frozenset({"cancel", "cancel_order", "cancel_task"})

    def __init__(self, reader: QmtBuiltinBridgeReader) -> None:
        self.reader = reader

    def read_latest(self, *, now: datetime | None = None) -> QmtBridgeSnapshot:
        return self.reader.read_latest(now=now)

    def __getattr__(self, name: str) -> NoReturn:
        """Reject conventional mutation entry points before a call can be made."""

        if name in self._SUBMISSION_METHODS:
            raise OrderSubmissionNotEnabledError(
                "order submission is not enabled for the read-only QMT bridge"
            )
        if name in self._CANCELLATION_METHODS:
            raise ReadOnlyBridgeError(
                "order cancellation is forbidden by the read-only QMT bridge"
            )
        raise AttributeError(name)
