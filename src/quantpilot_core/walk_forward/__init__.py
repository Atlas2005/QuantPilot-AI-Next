"""Walk-forward paper evaluation with deterministic leakage controls."""

from quantpilot_core.walk_forward.contracts import (
    OOSDailySessionResult,
    WalkForwardInput,
    WalkForwardResult,
    WalkForwardWindow,
    WalkForwardWindowContext,
    WalkForwardWindowExecutionResult,
    WalkForwardWindowResult,
    WindowRunner,
    WindowRunnerFactory,
)
from quantpilot_core.walk_forward.engine import WalkForwardEngine, run_walk_forward_paper_evaluation
from quantpilot_core.walk_forward.leakage import LeakageGuard
from quantpilot_core.walk_forward.pit_helpers import rows_through_execution
from quantpilot_core.walk_forward.snapshot import (
    SnapshotManifest,
    build_and_persist_snapshot,
    build_fixture_manifest,
    load_and_validate_snapshot,
)

__all__ = [
    "LeakageGuard",
    "OOSDailySessionResult",
    "SnapshotManifest",
    "WalkForwardEngine",
    "WalkForwardInput",
    "WalkForwardResult",
    "WalkForwardWindow",
    "WalkForwardWindowContext",
    "WalkForwardWindowExecutionResult",
    "WalkForwardWindowResult",
    "WindowRunner",
    "WindowRunnerFactory",
    "build_and_persist_snapshot",
    "build_fixture_manifest",
    "load_and_validate_snapshot",
    "rows_through_execution",
    "run_walk_forward_paper_evaluation",
]
