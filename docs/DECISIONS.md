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

## Phase 6A Decisions

- Phase 6A creates evaluation metadata only.
- No backtest framework is installed.
- No final backtest engine selection is made.
- Live-trading-capable engines must be isolated from early core.
- Future engine integration must happen through adapters and contract tests.
- Phase 6A does not run prototypes or backtests.

## Phase 6B Decisions

- Phase 6B creates prototype isolation plan only.
- First-wave prototype order is vectorbt, Backtrader, RQAlpha.
- Qlib is second-wave because it is more ML research platform than minimal backtest adapter.
- LEAN, vn.py / VeighNa, and NautilusTrader are deferred because live-trading and full-platform risks must remain isolated.
- No framework is installed or selected in Phase 6B.
- Phase 6B does not run backtests.

## Phase 6C-1 Decisions

- Phase 6C-1 tests vectorbt only.
- Backtrader and RQAlpha remain deferred to later manual prototypes.
- vectorbt is not a project dependency.
- The vectorbt prototype result does not equal engine selection.
- No vectorbt adapter exists yet.
- The prototype used only the fake Phase 3 local fixture and did not prove A-share trading realism.

## Phase 6C-1.1 Decisions

- Future external framework prototypes require isolated `.venv-prototypes/<tool-name>/` environments.
- The main Python environment must not be used for Backtrader, RQAlpha, Qlib, or deeper vectorbt prototype installs.
- Prototype dependencies remain out of `pyproject.toml` until a later approved adapter phase.
- Package install and uninstall operations require explicit approval.
- Prototype helper scripts may create environments but must not install packages or run prototypes automatically.

## Phase 6C-2 Decisions

- Phase 6C-2 tests Backtrader only.
- Backtrader must run only in isolated `.venv-prototypes/backtrader/`.
- Backtrader is not a project dependency.
- The Backtrader prototype result does not equal engine selection.
- No Backtrader adapter exists yet.
- Live trading capable framework risk remains isolated from QuantPilot core.

## Phase 6C-3A Decisions

- Phase 6C-3A reviews RQAlpha before installation.
- RQAlpha must not be installed in the main environment.
- RQAlpha requires isolated `.venv-prototypes/rqalpha/` if a prototype is later approved.
- RQAlpha is not a project dependency.
- No RQAlpha adapter exists.
- The preflight result does not equal engine selection.

## Phase 6C-3B Decisions

- Phase 6C-3B tests RQAlpha only in isolated `.venv-prototypes/rqalpha/`.
- RQAlpha is not a project dependency.
- The RQAlpha prototype result does not equal engine selection.
- RQAlpha commercial/license issue remains unresolved.
- No RQAlpha adapter exists yet.
- No broker/live/order path is allowed.
- Fake-fixture-only RQAlpha execution was not proven in this phase.

## Phase 6D Decisions

- Phase 6D compares evidence before adapter selection.
- vectorbt and Backtrader produced toy fake-fixture evidence only.
- RQAlpha produced install/import evidence only.
- Qlib remains a metadata/preflight candidate.
- Python remains appropriate for the current research/runtime layer, but language/runtime decisions will be reviewed at every major module.
- No final backtest engine selection is made.

## Phase 7A Decisions

- Phase 7A starts alpha/factor foundation using fake fixtures only.
- Python standard library is the correct runtime for this module.
- No pandas, NumPy, Alphalens, quantstats, or empyrical are introduced.
- Toy factor output is not alpha evidence.
- Final backtest engine selection is not required before factor contract foundation.
- No strategy tournament is created.

## Phase 7B Decisions

- Phase 7B creates validation metrics foundation using fake fixtures only.
- Python standard library is the correct runtime for this module.
- No pandas, NumPy, Alphalens, quantstats, or empyrical are introduced.
- Toy IC-like metrics are not alpha evidence.
- OOS, walk-forward, transaction costs, A-share rules, turnover, capacity, and paper feedback are required before real alpha claims.
- No strategy tournament is created.

## Phase 7C Decisions

- Phase 7C creates a conservative factor candidate library using fake fixtures only.
- Python standard library is the correct runtime for this module.
- No pandas, NumPy, Alphalens, quantstats, or empyrical are introduced.
- Factor candidates are not alpha evidence.
- No factor is validated or trading-ready.
- No strategy tournament is created.

## Phase 7D Decisions

- Phase 7D creates external analytics preflight only.
- Python standard library is the correct runtime for this module.
- No Alphalens, quantstats, empyrical, or Qlib package is installed.
- External analytics require larger real data and evidence gates.
- No external library can substitute for OOS, walk-forward, transaction costs, A-share execution rules, and paper feedback.
- No strategy tournament is created.

## Phase 7E Decisions

- Phase 7E creates real-data readiness gate only.
- Python standard library is the correct runtime for this module.
- No real data fetch occurs.
- No data source is approved.
- Raw data must not be committed.
- OOS, walk-forward, transaction costs, A-share rules, capacity, reproducibility, and paper feedback are required before real alpha claims.
- No strategy tournament is created.

## Phase 7F Decisions

- Phase 7F creates a controlled manual provider retry readiness probe layer.
- Provider scripts are manual only and are not test dependencies.
- Raw provider data must not be committed.
- A successful provider probe does not approve a data source.
- A successful provider probe does not prove alpha.
- No strategy tournament is created.
