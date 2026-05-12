# Decisions

## Step 0A Decisions

- QuantPilot-AI-Next is the official next-generation project for QuantPilot-AI 2.0.
- The old v2 project is a legacy research archive only.
- Step 0A is planning package only.
- Codex is not the project architect.
- ChatGPT owns architecture review and strategic decisions.
- Codex owns file creation, documentation organization, validation commands, and review packet production.
- Open-source candidates are recorded but not selected.
- Agent orchestration is late-stage.
- No source implementation is allowed in Step 0A.
- No dependency installation is allowed in Step 0A.
- No market data, API, broker, backtest, model, live trading, or order path is allowed in Step 0A.

## Step 0B Decisions

- ChatGPT approved the Step 0B kickoff before Codex implementation.
- Step 0B may create a minimal `src` layout Python package.
- Runtime dependencies remain empty.
- `pytest` is allowed as a dev/test dependency only.
- No quant, data-source, broker, ML, or agent framework integration is allowed in Step 0B.
- Safety flags default to false.
- The package remains not trading-ready.

## Phase 1 Decisions

- ChatGPT approved the Phase 1 kickoff before Codex implementation.
- Phase 1 creates candidate registry foundation only.
- Phase 1 makes no final technical selection.
- Phase 1 adds no dependency installation.
- Every candidate remains registry-only until ChatGPT-led module review.
- External frameworks must later enter through adapters and contract tests.
- Candidate metadata is static and stored in `data/open_source_candidates/candidates.json`.
- Candidate validation uses Python standard library only.

## Phase 2 Decisions

- ChatGPT approved the Phase 2 kickoff before Codex implementation.
- Phase 2 creates contracts only.
- Phase 2 creates no real adapters.
- Phase 2 makes no final engine selection.
- Phase 2 adds no external imports.
- Agent skill contract exists only as a late-stage boundary, not an implementation.
- Market rule contract exists only as a boundary before the actual market rule engine phase.
- Core contracts expose descriptive metadata and scope warnings only.

## Phase 1.1 Decisions

- Professional terminals are product/workflow benchmarks, not dependencies.
- Proprietary terminals are reference-only.
- FinceptTerminal requires license review before any cloning, integration, commercial use, or derivative work.
- The registry must include commercial/product benchmarks, not only GitHub libraries.
- Future module kickoff reviews must include both open-source search and professional benchmark scan.
- Phase 1.1 makes no final terminal, dashboard, or product architecture selection.

## Phase 3 Decisions

- Phase 3 uses local fixtures only.
- Phase 3 adds no pandas, Polars, DuckDB, PyArrow, Pandera, or Great Expectations.
- Phase 3 uses no real market data.
- Phase 3 creates no data-source adapters.
- A-share daily OHLCV schema is provisional and will be refined before prototypes.
- Phase 3 validation checks shape only and does not validate real market truth.

## Phase 4A Decisions

- Phase 4A creates prototype harness only.
- Phase 4A adds no package installation.
- Phase 4A performs no network data fetching.
- CI must not fetch market data.
- Data-source prototypes are manual-only until approved.
- SimTradeData is registry/reference only until license review.
- Field mappings are provisional until manual verification.

## Phase 4B Decisions

- Phase 4B tests AkShare and Baostock only.
- Tushare is deferred because of token and permission concerns.
- OpenBB is deferred because it is platform-level, not the first A-share daily source.
- SimTradeData remains reference-only because of license and commercial risk.
- Provider packages are not project dependencies yet.
- Raw provider output must not be committed.
- Phase 4B makes no final data-source selection.

## Phase 5 Decisions

- Phase 5 creates source-versioned market rule profiles.
- Market rules are configurable, not permanent hard-coded truth.
- Official exchange rules must be refreshed before production use.
- Fee, slippage, corporate action, and special-case handling remains deferred.
- No broker or execution path exists.
- No backtest engine exists.
