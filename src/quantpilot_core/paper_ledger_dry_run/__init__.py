"""R22 paper ledger dry-run integration."""

from quantpilot_core.paper_ledger_dry_run.contracts import (
    PaperLedgerDryRunDecision,
    PaperLedgerDryRunInstructionResult,
    PaperLedgerDryRunInstructionStatus,
    PaperLedgerDryRunResult,
    PaperLedgerDryRunRiskFlag,
    RiskSeverity,
)
from quantpilot_core.paper_ledger_dry_run.dry_run import (
    run_paper_ledger_dry_run,
    simulate_instruction,
)
from quantpilot_core.paper_ledger_dry_run.preflight import (
    validate_dry_run_instruction,
)

__all__ = [
    "PaperLedgerDryRunDecision",
    "PaperLedgerDryRunInstructionResult",
    "PaperLedgerDryRunInstructionStatus",
    "PaperLedgerDryRunResult",
    "PaperLedgerDryRunRiskFlag",
    "RiskSeverity",
    "run_paper_ledger_dry_run",
    "simulate_instruction",
    "validate_dry_run_instruction",
]
