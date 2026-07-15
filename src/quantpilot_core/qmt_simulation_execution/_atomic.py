"""Small standard-library-only atomic file primitives."""

from __future__ import annotations

import os
import secrets
import stat
from pathlib import Path

from .errors import AtomicWriteError, IntentConflictError


def write_immutable_atomic(target: Path, encoded: bytes, *, maximum: int) -> Path:
    """Publish bytes once through a same-directory temporary and exclusive lock."""

    if not encoded or len(encoded) > maximum:
        raise AtomicWriteError("artifact bytes are outside protocol bounds", path=target)
    target.parent.mkdir(parents=True, exist_ok=True)
    existing = _read_existing(target, maximum=maximum)
    if existing is not None:
        if existing == encoded:
            return target
        raise IntentConflictError("intent identity already has different content", path=target)

    lock = target.with_name("." + target.name + ".lock")
    try:
        lock_fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        existing = _read_existing(target, maximum=maximum)
        if existing == encoded:
            return target
        raise IntentConflictError("intent identity is already claimed", path=target) from None
    except OSError as exc:
        raise AtomicWriteError("intent publication lock cannot be created", path=target) from exc

    temp: Path | None = None
    try:
        os.close(lock_fd)
        existing = _read_existing(target, maximum=maximum)
        if existing is not None:
            if existing == encoded:
                return target
            raise IntentConflictError("intent identity already has different content", path=target)
        temp = _write_temp(target, encoded)
        existing = _read_existing(target, maximum=maximum)
        if existing is not None:
            if existing == encoded:
                return target
            raise IntentConflictError("intent identity already has different content", path=target)
        os.replace(temp, target)
        temp = None
        _fsync_directory(target.parent)
        return target
    except IntentConflictError:
        raise
    except OSError as exc:
        raise AtomicWriteError("intent cannot be published atomically", path=target) from exc
    finally:
        if temp is not None:
            _unlink_quietly(temp)
        _unlink_quietly(lock)


def write_replace_atomic(target: Path, encoded: bytes, *, maximum: int) -> Path:
    """Atomically replace one mutable state/result identity."""

    if not encoded or len(encoded) > maximum:
        raise AtomicWriteError("artifact bytes are outside protocol bounds", path=target)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp: Path | None = None
    try:
        temp = _write_temp(target, encoded)
        os.replace(temp, target)
        temp = None
        _fsync_directory(target.parent)
        return target
    except OSError as exc:
        raise AtomicWriteError("artifact cannot be published atomically", path=target) from exc
    finally:
        if temp is not None:
            _unlink_quietly(temp)


def read_bounded_file(
    target: Path,
    *,
    maximum: int,
    missing_error: type[Exception],
    invalid_error: type[Exception] | None = None,
) -> bytes:
    invalid = invalid_error or missing_error
    try:
        observed = target.lstat()
    except OSError as exc:
        raise missing_error("completed artifact is unavailable", path=target) from exc
    if (
        stat.S_ISLNK(observed.st_mode)
        or not stat.S_ISREG(observed.st_mode)
        or observed.st_size <= 0
        or observed.st_size > maximum
    ):
        raise invalid("completed artifact is outside protocol bounds", path=target)
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(str(target), flags)
    except OSError as exc:
        raise missing_error("completed artifact is unavailable", path=target) from exc
    try:
        opened = os.fstat(fd)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_size <= 0
            or opened.st_size > maximum
            or (observed.st_ino and opened.st_ino and observed.st_ino != opened.st_ino)
            or (observed.st_dev and opened.st_dev and observed.st_dev != opened.st_dev)
        ):
            raise invalid("completed artifact changed during inspection", path=target)
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining > 0:
            chunk = os.read(fd, min(remaining, 64 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        encoded = b"".join(chunks)
    finally:
        os.close(fd)
    if not encoded or len(encoded) > maximum:
        raise invalid("completed artifact is outside protocol bounds", path=target)
    return encoded


def _read_existing(target: Path, *, maximum: int) -> bytes | None:
    try:
        observed = target.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise AtomicWriteError("existing intent cannot be inspected safely", path=target) from exc
    if (
        stat.S_ISLNK(observed.st_mode)
        or not stat.S_ISREG(observed.st_mode)
        or observed.st_size <= 0
        or observed.st_size > maximum
    ):
        raise IntentConflictError("existing intent is not a regular file", path=target)
    try:
        fd = os.open(str(target), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise AtomicWriteError("existing intent cannot be inspected safely", path=target) from exc
    try:
        opened = os.fstat(fd)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_size <= 0
            or opened.st_size > maximum
            or (observed.st_ino and opened.st_ino and observed.st_ino != opened.st_ino)
            or (observed.st_dev and opened.st_dev and observed.st_dev != opened.st_dev)
        ):
            raise IntentConflictError("existing intent changed during inspection", path=target)
        encoded = os.read(fd, maximum + 1)
    finally:
        os.close(fd)
    if not encoded or len(encoded) > maximum:
        raise IntentConflictError("existing intent is outside protocol bounds", path=target)
    return encoded


def _write_temp(target: Path, encoded: bytes) -> Path:
    temp = target.with_name("." + target.name + "." + secrets.token_hex(8) + ".tmp")
    fd = os.open(
        str(temp),
        os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        view = memoryview(encoded)
        try:
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise OSError("short atomic artifact write")
                view = view[written:]
        finally:
            view.release()
        os.fsync(fd)
    finally:
        os.close(fd)
    return temp


def _fsync_directory(directory: Path) -> None:
    if os.name == "nt":
        return
    try:
        fd = os.open(str(directory), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _unlink_quietly(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass
