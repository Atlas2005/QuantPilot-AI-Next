# Backtest Prototype Results

## Phase 6C-1: vectorbt Manual Local-Fixture Prototype

This result is manual prototype evidence only. It is not production integration, not a real A-share backtest, not a final engine selection, and not trading-ready.

## Commands Run

```text
python tools/manual_backtest_prototypes/vectorbt_local_fixture_probe.py
python -m pip install vectorbt
python tools/manual_backtest_prototypes/vectorbt_local_fixture_probe.py
python tools/manual_backtest_prototypes/summarize_vectorbt_probe.py
```

The first probe run confirmed clean failure behavior when `vectorbt` was missing.

## Package Status

`vectorbt` was installed manually for the local prototype only. It was not added to `pyproject.toml` and is not a project dependency.

The install pulled vectorbt-related packages into the local Python environment and downgraded an already-present `pandas` installation from `3.0.2` to `2.3.3` because of vectorbt's dependency constraint. This is a local environment risk and should be reviewed before future prototype work.

Phase 6C-1.1 adds the follow-up policy: future external-framework prototypes must run in isolated `.venv-prototypes/<tool-name>/` environments. The vectorbt result remains useful as local fixture shape-compatibility evidence, but it is not enough for engine selection. Any deeper vectorbt test should be rerun in an isolated prototype environment if needed.

## Prototype Result

- Fake local fixture used: yes, `data/fixtures/a_share_daily_sample_valid.csv`.
- Real market data used: no.
- Provider/API used: no.
- Symbol selected: `000001.SZ`.
- Row count: 3.
- vectorbt importable after manual install: yes.
- Prototype ran: yes.
- Output metrics produced: yes, 28 metric keys were available.
- Production adapter created: no.

The prototype indicates that vectorbt can consume the Phase 3 fake daily OHLCV fixture shape and produce toy portfolio metrics from a minimal signal. This is shape-compatibility evidence only.

## A-share Rule Gaps

- T+1 not proven.
- Limit-up/limit-down not proven.
- Suspension handling not proven.
- ST/delisting special cases not proven.
- Liquidity constraints not proven.
- Realistic fees/slippage not proven.

## Recommendation

vectorbt deserves a deeper isolated prototype later if ChatGPT approves. The next prototype should remain manual-only and should focus on whether A-share market-rule constraints can be represented cleanly without polluting QuantPilot core contracts or creating a production adapter prematurely.

## Phase 6C-2: Backtrader Manual Local-Fixture Prototype

This result is manual prototype evidence only. It is not production integration, not a real A-share backtest, not a final engine selection, and not trading-ready.

## Environment

Backtrader was installed only inside:

```text
.venv-prototypes/backtrader/
```

Backtrader was not installed into the main project Python environment, was not added to `pyproject.toml`, and is not a project dependency.

## Commands Run

```text
powershell -ExecutionPolicy Bypass -File .\tools\prototype_envs\create_prototype_env.ps1 -Name backtrader
.venv-prototypes\backtrader\Scripts\python.exe -m pip install --upgrade pip
.venv-prototypes\backtrader\Scripts\python.exe -m pip install backtrader
.venv-prototypes\backtrader\Scripts\python.exe tools\manual_backtest_prototypes\backtrader_local_fixture_probe.py
python tools\manual_backtest_prototypes\summarize_backtrader_probe.py
```

The direct PowerShell helper invocation was blocked by local execution policy, so the helper was run with process-local `ExecutionPolicy Bypass`.

## Prototype Result

- Fake local fixture used: yes, `data/fixtures/a_share_daily_sample_valid.csv`.
- Real market data used: no.
- Provider/API used: no.
- Symbol selected: `000001.SZ`.
- Row count: 3.
- Backtrader importable inside isolated env: yes.
- Prototype ran: yes.
- Toy output produced: yes.
- Starting cash: `100000.0`.
- Final value: `99999.79999999999`.
- Toy closed trade count if available: `0`.
- Production adapter created: no.
- Broker/live store integration used: no.

The prototype indicates that Backtrader can consume a converted fake local daily OHLCV fixture and produce a minimal event-driven toy result. This is shape-compatibility and basic execution-flow evidence only.

## Backtrader A-share Rule Gaps

- T+1 not proven.
- Limit-up/limit-down not proven.
- Suspension handling not proven.
- ST/delisting special cases not proven.
- Liquidity constraints not proven.
- Realistic fees/slippage not proven.
- Realistic A-share order matching not proven.
- Corporate actions not proven.

## Backtrader Risks

- Backtrader has live-trading related capabilities and must remain isolated from QuantPilot core.
- The PyPI release appears old enough that maintenance status must be refreshed before any adapter phase.
- The toy result used a fake three-row fixture and default broker simulation, so it is not real performance evidence.

## Backtrader Recommendation

Backtrader deserves closure review before any deeper prototype. If ChatGPT approves additional work, the next Backtrader step should focus on A-share rule fit and broker/live isolation risk, still inside `.venv-prototypes/backtrader/`.

## Phase 6C-3A: RQAlpha Preflight Only

vectorbt and Backtrader now have toy fake-fixture prototype evidence.

RQAlpha has preflight metadata only. It has not been installed, imported, or run, and there is no RQAlpha prototype result yet.

No final backtest engine has been selected.

## Phase 6C-3B: RQAlpha Isolated Prototype Probe

This result is manual prototype evidence only. It is not production integration, not a real A-share backtest, not a final engine selection, and not trading-ready.

## RQAlpha Environment

RQAlpha was installed only inside:

```text
.venv-prototypes/rqalpha/
```

RQAlpha was not installed into the main project Python environment, was not added to `pyproject.toml`, and is not a project dependency.

## RQAlpha Commands Run

```text
powershell -ExecutionPolicy Bypass -File .\tools\prototype_envs\create_prototype_env.ps1 -Name rqalpha
.venv-prototypes\rqalpha\Scripts\python.exe -m pip install --upgrade pip
.venv-prototypes\rqalpha\Scripts\python.exe -m pip install rqalpha
.venv-prototypes\rqalpha\Scripts\python.exe tools\manual_backtest_prototypes\rqalpha_local_fixture_probe.py
python tools\manual_backtest_prototypes\summarize_rqalpha_probe.py
```

The direct PowerShell helper invocation was blocked by local execution policy, so the helper was run with process-local `ExecutionPolicy Bypass`.

## RQAlpha Prototype Result

- Fake local fixture used: yes, `data/fixtures/a_share_daily_sample_valid.csv`.
- Real market data used: no.
- Provider/API used: no.
- Symbol selected: `000001.SZ`.
- Row count: 3.
- RQAlpha importable inside isolated env: yes.
- RQAlpha version observed: `6.1.4`.
- Minimal local fake-fixture run attempted: no.
- Minimal local fake-fixture run succeeded: no.
- Data bundle/config blocker: likely required for normal RQAlpha execution; no bundle/provider setup was created.
- Direct fake fixture support observed: no.
- Output metrics produced: no.
- Production adapter created: no.
- Broker/live/order functionality used: no.

The probe indicates that RQAlpha can be installed and imported in the isolated environment, but fake-fixture-only local run support was not proven. Data bundle/config requirements need further review before any deeper prototype.

## RQAlpha A-share Rule Gaps

- T+1 not proven.
- Limit-up/limit-down not proven.
- Suspension handling not proven.
- ST/delisting special cases not proven.
- Liquidity constraints not proven.
- Realistic fees/slippage not proven.
- Realistic A-share order matching not proven.
- Corporate actions not proven.
- Production data bundle reliability not proven.
- Commercial/license suitability not proven.

## RQAlpha License and Commercial Warning

RQAlpha remains research/prototype-only. Do not commercialize, vendor, copy source, integrate, or create derivative production adapter code before license review.

## RQAlpha Recommendation

RQAlpha may deserve a deeper prototype only if ChatGPT approves a data-bundle/config review. Any future work must remain isolated in `.venv-prototypes/rqalpha/`, use fake fixtures unless explicitly approved otherwise, and avoid adapter or engine-selection decisions.
