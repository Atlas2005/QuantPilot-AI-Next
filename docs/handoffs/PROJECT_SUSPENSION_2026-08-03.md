# QuantPilot-AI-Next Suspension Checkpoint

Date: 2026-08-03
Status: Paused for an extended period

## Repository

- Base: `feat/tdx-prediction-integration-v1` at `3e76235`
- WIP: `fix/tdx-runtime-stability-v1`
- Latest reported tests: `2170 passed, 6 skipped`
- Review artifact: `~/Desktop/tdx-runtime-stability-v1.review.v3.patch`
- Do not merge this WIP branch before final code review and Windows acceptance.

## Completed

- Real DeepSeek seven-desk HTTP acceptance and JSON contract repair.
- Windows/TongDaXin manual marker path.
- 2026-08-03 live holdout archived with SHA256.
- WIP runtime fixes: empty TQ arguments, reconnect storm, single-instance lock, clean Ctrl+C, TDX V6.06 formula compatibility.

## Holdout classification

- `live_holdout = true`
- `decision_source = deterministic_baseline`
- `deepseek_mode = cached_evidence_only`
- Not proof of profitability; do not retrospectively tune to this day.

## Resume order

1. Review the v3 patch.
2. Run `scripts/windows/quantpilot-single-instance-smoke.ps1`.
3. Run a short Windows intraday acceptance.
4. Merge the runtime-stability PR only after approval.
5. Make DeepSeek primary for daily candidates.
6. Make DeepSeek primary for event-driven intraday lifecycle decisions.
7. Keep `deterministic_baseline` only as explicit fallback.
8. Reuse existing Qlib/VectorBT/RQAlpha/paper evidence.
9. Validate out-of-sample profitability before real-money use.

## Principles

Profit-first; mature integration before self-building; A-share realism; DeepSeek multi-agent primary decision architecture; no generic overblocking; deterministic T+1, lots, fees, slippage, limits, suspensions, holdings and account constraints; no broker/order changes without a separate controlled phase.

## Resume commands

```bash
git fetch origin --prune
git switch fix/tdx-runtime-stability-v1
git status -sb
git log -5 --oneline --decorate
cat docs/handoffs/PROJECT_SUSPENSION_2026-08-03.md
```
