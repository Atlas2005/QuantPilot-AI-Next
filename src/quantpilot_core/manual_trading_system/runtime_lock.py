"""Cross-platform single-writer ownership lock for one runtime directory.

Uses only the standard library. A second intraday instance pointed at the same
system directory fails fast with the owner PID and token instead of corrupting
shared files. Crashed processes never leave a permanently blocking lock: a
lock whose recorded owner is dead is treated as stale and recovered.

Process liveness probing is non-destructive on every platform:

- POSIX uses ``os.kill(pid, 0)``, which sends no signal.
- Windows never calls ``os.kill`` (any signal other than
  CTRL_C_EVENT/CTRL_BREAK_EVENT would terminate the owner). It probes with
  ``ctypes``: ``OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE)``,
  ``GetExitCodeProcess`` (STILL_ACTIVE), and ``CloseHandle``.
"""

from __future__ import annotations

import ctypes
import json
import os
import secrets
import socket
import sys
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

_WINDOWS = sys.platform == "win32"
_LOCK_GRACE_SECONDS = 30.0
_STILL_ACTIVE = 259
_SYNCHRONIZE = 0x00100000
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_ERROR_ACCESS_DENIED = 5


class _FILETIME(ctypes.Structure):
    """Windows FILETIME: 100-nanosecond intervals since 1601-01-01."""

    _fields_ = [
        ("dwLowDateTime", wintypes.DWORD),
        ("dwHighDateTime", wintypes.DWORD),
    ]


def _load_kernel32() -> Any:
    """Return a kernel32 handle with explicit, ABI-correct prototypes.

    Without ``argtypes``/``restype``, ctypes defaults to ``c_int`` and
    truncates pointer-sized HANDLE values on 64-bit Windows. Every function
    used here is configured explicitly; the default restype is only ever
    replaced with ``wintypes.HANDLE``/``wintypes.BOOL``.
    """

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _configure_kernel32_prototypes(kernel32)
    return kernel32


def _configure_kernel32_prototypes(kernel32: Any) -> None:
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.GetProcessTimes.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_FILETIME),
        ctypes.POINTER(_FILETIME),
        ctypes.POINTER(_FILETIME),
        ctypes.POINTER(_FILETIME),
    ]
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL


class RuntimeLockError(RuntimeError):
    """Another live process owns the requested runtime directory."""


class SystemDirLock:
    """Exclusive owner marker for one system directory, acquired with O_EXCL."""

    def __init__(
        self,
        system_dir: str | Path,
        *,
        clock: Callable[[], datetime] | None = None,
        grace_seconds: float = _LOCK_GRACE_SECONDS,
    ) -> None:
        self.system_dir = Path(system_dir)
        self.lock_path = self.system_dir / ".qp_intraday.lock"
        self.grace_seconds = max(0.0, float(grace_seconds))
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._owned = False
        self._token: Mapping[str, str] | None = None

    def acquire(self) -> None:
        if self._owned:
            return
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        token = {
            "pid": str(os.getpid()),
            "nonce": secrets.token_hex(16),
            "started_at": self._clock().isoformat(timespec="seconds"),
            "host": socket.gethostname(),
            "mode": "intraday",
            "process_start_identity": _process_start_identity(os.getpid()),
        }
        for _attempt in range(3):
            try:
                descriptor = os.open(
                    self.lock_path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o644,
                )
            except FileExistsError:
                self._handle_existing_owner()
                continue
            try:
                os.write(descriptor, json.dumps(token, sort_keys=True).encode("utf-8"))
            finally:
                os.close(descriptor)
            self._owned = True
            self._token = token
            return
        raise RuntimeLockError(
            f"intraday lock file {self.lock_path} exists and cannot be recovered"
        )

    def release(self) -> None:
        if not self._owned:
            return
        owner = _read_lock_token(self.lock_path)
        if owner is not None and _token_owned_by_us(owner, self._token):
            _best_effort_remove(self.lock_path)
        self._owned = False
        self._token = None

    def _handle_existing_owner(self) -> None:
        owner = _read_lock_token(self.lock_path)
        if owner is None:
            # The lock is being written or its write was torn. Never delete a
            # fresh unparseable lock; wait out the grace period for a truly
            # abandoned torn write.
            age = _lock_age_seconds(self.lock_path, self._clock)
            if age is not None and age > self.grace_seconds:
                _best_effort_remove(self.lock_path)
                return
            raise RuntimeLockError(
                f"intraday lock {self.lock_path} exists but is unreadable "
                "(it may be being created); retry shortly"
            )
        host = str(owner.get("host") or "").strip()
        if host and host != socket.gethostname():
            # A foreign-host lock must not be deleted based on a local PID
            # check: the owner is alive from our perspective.
            raise RuntimeLockError(
                f"intraday instance already running for {self.system_dir} on "
                f"host {host}: pid={_lock_pid(owner)} started_at={owner.get('started_at', 'unknown')}"
            )
        if _owner_alive(owner):
            raise RuntimeLockError(
                f"intraday instance already running for {self.system_dir}: "
                f"owner pid={_lock_pid(owner)} started_at={owner.get('started_at', 'unknown')} "
                f"nonce={str(owner.get('nonce', ''))[:8]}"
            )
        # The owner is dead. Require the lock to be older than the grace
        # period so a just-created orphaned lock is not stolen mid-write.
        age = _lock_age_seconds(self.lock_path, self._clock)
        if age is not None and age <= self.grace_seconds:
            raise RuntimeLockError(
                f"intraday lock {self.lock_path} owner pid={_lock_pid(owner)} "
                "recently exited; retry after the grace period"
            )
        _best_effort_remove(self.lock_path)


def _token_owned_by_us(
    owner: Mapping[str, Any],
    token: Mapping[str, Any] | None,
) -> bool:
    if token is None:
        return False
    return (
        str(owner.get("pid")) == str(token.get("pid"))
        and str(owner.get("nonce")) == str(token.get("nonce"))
        and str(owner.get("host")) == str(token.get("host"))
    )


def _owner_alive(owner: Mapping[str, Any]) -> bool:
    pid = _lock_pid(owner)
    if pid <= 0:
        return False
    if _WINDOWS:
        alive = _windows_pid_alive(pid)
    else:
        alive = _posix_pid_alive(pid)
    if not alive:
        return False
    # PID-reuse guard: when both the lock token and the current process
    # expose a start identity, a mismatch means the PID now belongs to an
    # unrelated process and the lock is stale.
    expected_identity = str(owner.get("process_start_identity") or "").strip()
    if expected_identity:
        actual_identity = str(_process_start_identity(pid) or "").strip()
        if actual_identity and actual_identity != expected_identity:
            return False
    return True


def _posix_pid_alive(pid: int) -> bool:
    """Signal-0 probe, used only on POSIX platforms."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    return True


def _windows_pid_alive(pid: int) -> bool:
    """Non-destructive Windows probe: open, query exit code, close.

    Never sends a signal and never terminates the owner. Every successful
    OpenProcess is paired with CloseHandle.
    """

    kernel32 = _load_kernel32()
    handle = kernel32.OpenProcess(
        _PROCESS_QUERY_LIMITED_INFORMATION | _SYNCHRONIZE,
        False,
        pid,
    )
    if not handle:
        # ERROR_ACCESS_DENIED means the process exists but we cannot open it.
        return ctypes.get_last_error() == _ERROR_ACCESS_DENIED
    try:
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.pointer(exit_code)):
            return True  # cannot read the exit code: be conservative
        return int(exit_code.value) == _STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def _process_start_identity(pid: int) -> str:
    """Best-effort process creation identity used to detect PID reuse."""
    if _WINDOWS:
        return _windows_process_creation_identity(pid)
    if sys.platform.startswith("linux"):
        return _linux_start_time_identity(pid)
    return ""


def _linux_start_time_identity(pid: int) -> str:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="ascii", errors="replace")
        tail = stat.rsplit(")", 1)[1].split()
        return f"linux-starttime:{tail[19]}" if len(tail) > 19 else ""
    except (OSError, IndexError):
        return ""


def _windows_process_creation_identity(pid: int) -> str:
    kernel32 = _load_kernel32()
    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        creation = _FILETIME()
        exit_time = _FILETIME()
        kernel_time = _FILETIME()
        user_time = _FILETIME()
        if not kernel32.GetProcessTimes(
            handle,
            ctypes.pointer(creation),
            ctypes.pointer(exit_time),
            ctypes.pointer(kernel_time),
            ctypes.pointer(user_time),
        ):
            return ""  # never fabricate an identity when the query fails
        raw = (int(creation.dwHighDateTime) << 32) | int(creation.dwLowDateTime)
        return f"win-creation:{raw}"
    finally:
        kernel32.CloseHandle(handle)


def _read_lock_token(path: Path) -> Mapping[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, Mapping) else None


def _lock_pid(owner: Mapping[str, Any]) -> int:
    try:
        return int(owner.get("pid", -1))
    except (TypeError, ValueError):
        return -1


def _lock_age_seconds(
    path: Path,
    clock: Callable[[], datetime],
) -> float | None:
    try:
        modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None
    now = clock()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return max(0.0, (now - modified).total_seconds())


def _best_effort_remove(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass
