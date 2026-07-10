"""Optional runtime boundary for the all-A-share snapshot feature."""

from quantpilot_core.all_a_share_snapshot.parquet_runtime import (
    ALL_A_SHARE_INSTALL_COMMAND,
    PyArrowRuntime,
    PyArrowUnavailableError,
    require_pyarrow,
)
from quantpilot_core.all_a_share_snapshot.snapshot import SnapshotLoader, build_snapshot, validate_snapshot

__all__ = [
    "ALL_A_SHARE_INSTALL_COMMAND",
    "PyArrowRuntime",
    "PyArrowUnavailableError",
    "require_pyarrow",
    "SnapshotLoader",
    "build_snapshot",
    "validate_snapshot",
]
