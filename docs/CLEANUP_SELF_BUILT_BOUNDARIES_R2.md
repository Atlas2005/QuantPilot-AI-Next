# Cleanup Self-Built Boundaries R2

## What Was Downgraded

R2 cleanup downgraded remaining gate/preflight/readiness modules that still affected the executable trading path:

- `provider_probe_gate` now behaves as provider probe policy / manifest validation. Review metadata gaps are advisory unless the request is malformed or asks for unsafe live/broker/order behavior.
- `small_sample_data_gate` now behaves as small-sample data quality validation. Historical R4/R3/R2 provenance references and non-fatal review gaps are advisory messages.
- `provider_sample_fetch_preflight` now treats undersized or metadata-incomplete samples as quality warnings when bars are structurally usable.
- `account_profile_preflight` now treats missing evidence and concentration breaches as warnings/config notes while preserving fatal account and cash constraints.
- `small_capital_readiness_gate` now emits capital sizing metrics. Non-fatal metric misses become manual-review metrics instead of a central trading blocker.
- `broker_sandbox_adapter_preflight` now treats readiness results as broker sandbox adapter config context. Fatal instruction, permission, cash, sellable quantity, and account status checks remain.
- `final_readiness_release_hardening` no longer requires historical preflight/gate modules as default release blockers.

## Blockers Removed

Removed as hard blockers:

- Historical R4 gate decision reference.
- Historical R3/R2 compatibility markers.
- License/review metadata gaps for provider probe and small samples.
- Minimum sample size as a hard downstream blocker when normalized bars are available.
- Account evidence refs as a hard blocker.
- Concentration/readiness metrics as central trading blockers.
- Broker sandbox readiness FAIL as a blanket instruction blocker.
- Final-readiness requirements for provider sample fetch, PIT feature store, account profile, small-sample data gate, small-capital readiness, and broker sandbox preflight modules.

## Fatal Safety Checks That Remain

Fatal checks still block where they represent real operational danger or impossible execution:

- Credential leakage or unauthorized live broker path.
- Broker/live/order execution flags where a module is not allowed to perform them.
- Malformed provider/sample requests.
- Structurally unusable fetched data, such as no normalized bars.
- Negative cash, invalid total equity, invalid fee values, invalid sellable quantity, duplicate positions, and invalid permissions.
- Suspended or non-active account states for executable broker sandbox handoff.
- Insufficient cash.
- Invalid sellable quantity.
- Missing buy/sell permission.
- A-share lot-size violations unless explicitly allowed as odd-lot handling.
- Estimated notional mismatch or impossible instruction shape.

## Project Direction

Safety must not mean no trading.

Non-fatal issues become warnings, metrics, or config notes. They should guide sizing, data quality, and operations rather than stopping normal paper replay or controlled trading progress.

AI is for profitability optimization, strategy improvement, parameter tuning, execution realism, and continuous improvement. It must not become a blocking preflight layer.

## R3 Direction

Future R3 cleanup should replace the remaining self-built replay/fill chain with mature framework-backed replay and backtesting using vectorbt, RQAlpha, and Qlib where practical.

Current future cleanup/replacement targets include:

- `gate_pruning_tradability_fill_loop`
- `explicit_fill_simulation_boundary`
- `executable_candidate_paper_bridge`
- `paper_ledger_dry_run`
- `multi_day_paper_replay`
- `real_provider_mixed_etf_paper_replay`
