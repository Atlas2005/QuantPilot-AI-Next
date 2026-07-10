"""Lazy PyArrow boundary for the future all-A-share Parquet snapshot.

This module intentionally owns no provider, token, or network behavior.  PyArrow
is imported only when Parquet functionality explicitly requests it.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from types import ModuleType
from typing import Callable


ALL_A_SHARE_INSTALL_COMMAND = 'python -m pip install -e ".[all-a-share]"'


class PyArrowUnavailableError(RuntimeError):
    """Raised when the optional all-A-share Parquet runtime is unavailable."""


@dataclass(frozen=True)
class PyArrowRuntime:
    """The lazily loaded PyArrow module and its reported version."""

    module: ModuleType
    version: str


def require_pyarrow(
    importer: Callable[[str], ModuleType] | None = None,
) -> PyArrowRuntime:
    """Load PyArrow only when all-A-share Parquet functionality is invoked.

    Version compatibility is declared by the ``all-a-share`` packaging extra;
    this boundary reports the installed version and does not suppress failures
    caused by an incompatible runtime.
    """
    package_importer = importer or importlib.import_module
    try:
        module = package_importer("pyarrow")
    except ModuleNotFoundError as exc:
        if exc.name != "pyarrow":
            raise
        raise PyArrowUnavailableError(
            "PyArrow is required for all-A-share Parquet snapshots. "
            f"Install it with: {ALL_A_SHARE_INSTALL_COMMAND}"
        ) from None

    version = getattr(module, "__version__", None)
    if not isinstance(version, str) or not version.strip():
        raise RuntimeError("PyArrow runtime does not expose a usable __version__.")
    return PyArrowRuntime(module=module, version=version)
