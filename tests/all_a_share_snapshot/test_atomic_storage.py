"""Regression coverage for durable cross-platform Parquet replacement."""

from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest

from quantpilot_core.all_a_share_snapshot.snapshot import ProviderCallError, _failure
from quantpilot_core.all_a_share_snapshot import storage


STOCK_BASIC_ROWS = (
    {
        "ts_code": "000001.SZ",
        "symbol": "000001",
        "name": "平安银行",
        "area": "深圳",
        "industry": "银行",
        "market": "主板",
        "exchange": "SZSE",
        "list_status": "L",
        "list_date": "19910403",
        "delist_date": "",
    },
)


def test_atomic_parquet_sync_owns_a_live_descriptor_and_leaves_no_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "stock_basic" / "part-00000.parquet"
    synchronized: list[int] = []
    real_fsync = os.fsync

    def recording_fsync(descriptor: int) -> None:
        # This is the Windows failure boundary: the descriptor must still be
        # valid at the exact point where fsync/_commit is invoked.
        os.fstat(descriptor)
        synchronized.append(descriptor)
        real_fsync(descriptor)

    monkeypatch.setattr(storage.os, "fsync", recording_fsync)

    result = storage.atomic_write("stock_basic", target, STOCK_BASIC_ROWS)

    assert result["row_count"] == 1
    assert target.is_file()
    assert not storage.temporary_path(target).exists()
    assert storage.read_table(target).to_pylist() == list(STOCK_BASIC_ROWS)
    assert synchronized
    for descriptor in set(synchronized):
        with pytest.raises(OSError):
            os.fstat(descriptor)


def test_failed_finalization_cleans_temp_preserves_canonical_and_can_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "stock_basic" / "part-00000.parquet"
    storage.atomic_write("stock_basic", target, STOCK_BASIC_ROWS)
    original_bytes = target.read_bytes()

    replacement = (dict(STOCK_BASIC_ROWS[0], name="replacement"),)
    with monkeypatch.context() as context:
        context.setattr(
            storage,
            "_sync_file",
            lambda _: (_ for _ in ()).throw(OSError(errno.EBADF, "Bad file descriptor")),
        )
        with pytest.raises(OSError, match="Bad file descriptor"):
            storage.atomic_write("stock_basic", target, replacement)

    assert target.read_bytes() == original_bytes
    assert not storage.temporary_path(target).exists()

    storage.atomic_write("stock_basic", target, replacement)
    assert storage.read_table(target).to_pylist()[0]["name"] == "replacement"
    assert not storage.temporary_path(target).exists()


def test_stale_temp_is_replaced_without_deleting_canonical(tmp_path: Path) -> None:
    target = tmp_path / "stock_basic" / "part-00000.parquet"
    storage.atomic_write("stock_basic", target, STOCK_BASIC_ROWS)
    storage.temporary_path(target).write_bytes(b"orphaned partial parquet")

    storage.discard_temporary(target)

    assert target.is_file()
    assert storage.read_table(target).num_rows == 1
    assert not storage.temporary_path(target).exists()


def test_local_oserror_is_not_provider_transport_and_reason_is_sanitized() -> None:
    local = _failure(
        "required",
        OSError(errno.EBADF, "Bad file descriptor token=private-value"),
        required=True,
    )
    transport = _failure(
        "daily",
        ProviderCallError(ConnectionError("provider connection reset"), attempts=3),
        required=True,
    )

    assert local["exception_category"] == "local_filesystem"
    assert local["retry_exhausted"] is False
    assert "private-value" not in local["reason"]
    assert transport["exception_category"] == "retryable_transport"
    assert transport["retry_exhausted"] is True
