# Current Project State

- Status date: 2026-08-15
- Bilingual overview: [README.md](../README.md)
- Chinese overview: [README.zh-CN.md](../README.zh-CN.md)
- English overview: [README.en.md](../README.en.md)

## Verdict

QuantPilot-AI-Next is an implemented A-share quant research, paper-trading, and manual decision-support platform. It is no longer an early planning skeleton. It is also not a proven-profitable or autonomous live-trading product.

The previous version of this document was materially stale: it described an early information-layer phase and claimed that real data, provider adapters, model calls, and broker boundaries did not exist. The repository has since implemented all of those controlled capabilities. Those historical prohibitions must not be used to describe the current code.

## Authoritative branch state

| Layer | Ref | Evidence-backed state |
|---|---|---|
| Default merged baseline | `main`; functional baseline `8c232f2` | Merged through PR #130; public and covered by CI |
| Completed feature baseline | `feat/tdx-prediction-integration-v1` at `3e76235` | Implements the TDX prediction and manual workflow; 15 post-baseline commits; not merged into `main` |
| Latest paused WIP | `fix/tdx-runtime-stability-v1` at `baf992c` | Adds runtime-stability fixes; must pass code review and Windows acceptance before merge |

The full local suite at the WIP checkpoint completed with `2170 passed, 6 skipped` on 2026-08-15. The project-suspension record reports the same totals at the August 3 checkpoint. Passing tests are implementation evidence, not trading-readiness or profitability evidence.

## Merged capabilities on `main`

- Core contracts, registries, integration policies, and A-share market-reality rules.
- TuShare and BaoStock data adapters, provider fallback/cross-checking, real trading calendars, and TDX Level1 market data.
- Full-A-share snapshots, PIT handling, tradability metadata, and provider/data validation.
- Deterministic and ML factor research, walk-forward/OOS evaluation, after-cost baselines, turnover optimization, and attribution.
- Qlib, VectorBT, and RQAlpha adapter/evaluation work behind optional dependency boundaries.
- Executable-candidate sizing, cost, tradability, fill simulation, paper ledger, multi-day replay, daily evaluation, and continuous paper operation.
- DeepSeek multi-agent contracts, information/research roles, bounded runtime routing, and shadow/advisory integration.
- Windows runtime bootstrap, DPAPI secret handling, Docker-backed control-center services, Runtime Doctor, and lifecycle scripts.
- QMT built-in read-only snapshot bridge, TDX manual signal bridge, and TDX Level1 adapter.

## Implemented after the current `main` baseline

The completed feature checkpoint `3e76235` adds:

- TDX prediction replay and live-shadow integration.
- Walk-forward-trained probability provider and evaluation hardening.
- Human-experience plans, markers, QPTY visibility, and TQ protocol repairs.
- Daily production input from validated full-A PIT data.
- Historical A-share code-transition reconciliation and Windows-safe atomic snapshot writes.
- A three-part manual system for after-close analysis, intraday monitoring, and end-of-day recording.
- Real DeepSeek seven-desk calls with physical-call accounting and a strict JSON output contract.

The WIP checkpoint `baf992c` additionally addresses:

- single-instance runtime locking;
- reconnect-storm suppression;
- clean Ctrl+C shutdown;
- empty TQ arguments;
- TDX V6.06 formula compatibility.

These WIP changes are not accepted release functionality until the Windows checks pass.

## Evidence for progress

- The latest code is 16 implementation/fix commits beyond the code baseline currently shown on `main`.
- The latest complete local suite passes 2170 tests with 6 skips.
- The code contains explicit real-data, A-share rule, walk-forward/OOS, cost, paper, model-budget, Windows runtime, TDX, and QMT read-only boundaries.
- A 2026-08-03 live holdout was archived and classified as `live_holdout=true`.

## Evidence against readiness

- The archived holdout used `decision_source=deterministic_baseline` and `deepseek_mode=cached_evidence_only`; it is not proof that live DeepSeek decisions improve returns.
- One holdout day is statistically inadequate and must not be retrospectively tuned.
- The latest runtime branch remains explicitly blocked on final review and Windows acceptance.
- Automated live order execution is not part of the accepted default path.
- No release/tag exists, and the repository has no explicit license file.
- No available evidence establishes durable out-of-sample profitability after fees, slippage, regime changes, and operational failures.

## Current decision

The correct label is: **advanced research / continuous paper / manual decision support; paused pending Windows runtime acceptance**.

Do not label the project as any of the following:

- production-ready;
- proven profitable;
- autonomous live trading;
- safe for unattended real-capital execution;
- a stable versioned SDK.

## Resume order

1. Review `fix/tdx-runtime-stability-v1` and its suspension checkpoint.
2. Run `scripts/windows/quantpilot-single-instance-smoke.ps1` on the intended Windows/TDX runtime.
3. Run a short intraday acceptance and verify reconnect, shutdown, locking, formulas, and QPTY visibility.
4. Merge only after the review and Windows evidence pass.
5. Rerun the full Linux and Windows CI matrix.
6. Accumulate multi-regime, non-retrospectively-tuned paper/holdout evidence.
7. Evaluate promotion using after-cost return, maximum drawdown, turnover, stability, and benchmark-relative performance.
8. Keep any real-order or capital-test work in a separate, explicitly approved, hard-limited phase.

## Stop conditions

Stop promotion or capital discussion if any of the following occurs:

- point-in-time leakage or untraceable data;
- no persistent after-cost edge;
- drawdown beyond a predefined risk threshold;
- unstable provider, Windows runtime, TDX, QMT, database, or orchestration behavior;
- model decisions that cannot be reproduced or audited;
- secret/account data entering Git, logs, reports, or model prompts;
- any path that bypasses explicit human approval or broker safety boundaries.

## Related documents

- [Bilingual project overview](../README.md)
- [Chinese project overview](../README.zh-CN.md)
- [English project overview](../README.en.md)
- [Windows runtime](windows_runtime.md)
- [Project positioning](PROJECT_POSITIONING.md)
- [Success metrics](SUCCESS_METRICS.md)
- [Profit-first integration architecture](PROFIT_FIRST_INTEGRATION_ARCHITECTURE.md)
- [A-share market rules](A_SHARE_MARKET_RULES.md)
- [Historical roadmap](QUANTPILOT_AI_2_0_ROADMAP.md)
