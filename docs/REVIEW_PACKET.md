# Review Packet

## Task Name

Phase 6C-3B: Isolated RQAlpha Prototype Probe.

## Changed Files

- `docs/modules/phase_6c_3b_rqalpha_isolated_prototype/MODULE_KICKOFF_REVIEW.md`
- `docs/modules/phase_6c_3b_rqalpha_isolated_prototype/MODULE_CLOSURE_DRAFT.md`
- `tools/manual_backtest_prototypes/rqalpha_local_fixture_probe.py`
- `tools/manual_backtest_prototypes/summarize_rqalpha_probe.py`
- `docs/BACKTEST_PROTOTYPE_RESULTS.md`
- `docs/RQALPHA_PREFLIGHT_REVIEW.md`
- `docs/BACKTEST_PROTOTYPE_ISOLATION_PLAN.md`
- `docs/BACKTEST_ENGINE_CANDIDATES.md`
- `docs/CURRENT_PROJECT_STATE.md`
- `docs/DECISIONS.md`
- `docs/NEXT_CHAT_HANDOFF.md`
- `docs/REVIEW_PACKET.md`

## Safety Checks

- `src/` changed: No.
- `tools/` changed: Yes. Manual RQAlpha probe and summary scripts only.
- Dependencies changed: Project dependency files unchanged; isolated prototype environment changed.
- Packages installed: Yes, isolated environment only.
- Exact packages installed: `rqalpha==6.1.4`, `rqrisk==1.0.13`, `numpy==2.4.4`, `pandas==2.3.3`, `requests==2.34.0`, `python-dateutil==2.9.0.post0`, `six==1.17.0`, `logbook==1.9.2`, `click==8.3.3`, `jsonpickle==4.1.1`, `simplejson==4.1.1`, `PyYAML==6.0.3`, `tabulate==0.10.0`, `h5py==3.16.0`, `matplotlib==3.10.9`, `openpyxl==3.1.5`, `methodtools==0.4.7`, `filelock==3.29.0`, `typing-extensions==4.15.0`, `pytz==2026.2`, `tzdata==2026.2`, `colorama==0.4.6`, `contourpy==1.3.3`, `cycler==0.12.1`, `fonttools==4.62.1`, `kiwisolver==1.5.0`, `packaging==26.2`, `pillow==12.2.0`, `pyparsing==3.3.2`, `scipy==1.17.1`, `statsmodels==0.14.6`, `patsy==1.0.2`, `wirerope==1.0.0`, `et-xmlfile==2.0.0`, `charset_normalizer==3.4.7`, `idna==3.14`, `urllib3==2.7.0`, `certifi==2026.4.22`.
- Packages installed in main environment: No.
- Packages installed in isolated environment: Yes.
- Isolated environment path: `.venv-prototypes/rqalpha/`.
- `pyproject.toml` changed: No.
- RQAlpha installed: Yes, isolated environment only.
- RQAlpha imported: Yes, only inside `tools/manual_backtest_prototypes/rqalpha_local_fixture_probe.py` when run with isolated env Python.
- Market data/API used: No.
- Fake fixture only used: Yes, `data/fixtures/a_share_daily_sample_valid.csv`.
- `local_artifacts/` created: Yes.
- Raw artifacts are gitignored: Yes, `local_artifacts/` is ignored.
- Broker/live/order submission path created: No.
- Real backtest/model/agent implementation added: No.
- External frameworks installed/imported in `src/`: No.
- Final technical selections made: No.

## Prototype Commands and Results

`.\\tools\\prototype_envs\\create_prototype_env.ps1 -Name rqalpha`

Result: blocked by local PowerShell execution policy.

`powershell -ExecutionPolicy Bypass -File .\\tools\\prototype_envs\\create_prototype_env.ps1 -Name rqalpha`

Result: passed. Created `.venv-prototypes/rqalpha/`.

`.venv-prototypes\\rqalpha\\Scripts\\python.exe -m pip install --upgrade pip`

Result: pip was already present. The command could not check the remote index under sandboxed network, but no fallback to the main environment occurred.

`.venv-prototypes\\rqalpha\\Scripts\\python.exe -m pip install rqalpha`

Result: initial sandboxed attempt failed due network restrictions; escalated isolated-env install succeeded.

`.venv-prototypes\\rqalpha\\Scripts\\python.exe tools\\manual_backtest_prototypes\\rqalpha_local_fixture_probe.py`

Result: passed.

`python tools\\manual_backtest_prototypes\\summarize_rqalpha_probe.py`

Result: passed.

## Validation Commands and Results

`python -m compileall src`

Result: passed.

`python -m pytest`

Result: passed.

```text
collected 98 items
98 passed in 0.17s
```

`git status -sb`

Result:

```text
## main...origin/main
 M docs/BACKTEST_ENGINE_CANDIDATES.md
 M docs/BACKTEST_PROTOTYPE_ISOLATION_PLAN.md
 M docs/BACKTEST_PROTOTYPE_RESULTS.md
 M docs/CURRENT_PROJECT_STATE.md
 M docs/DECISIONS.md
 M docs/NEXT_CHAT_HANDOFF.md
 M docs/REVIEW_PACKET.md
 M docs/RQALPHA_PREFLIGHT_REVIEW.md
?? docs/modules/phase_6c_3b_rqalpha_isolated_prototype/
?? tools/manual_backtest_prototypes/rqalpha_local_fixture_probe.py
?? tools/manual_backtest_prototypes/summarize_rqalpha_probe.py
```

## RQAlpha Prototype Summary

- Provider: `rqalpha`.
- Environment: `.venv-prototypes/rqalpha/`.
- Fake fixture used: yes.
- Symbol: `000001.SZ`.
- Row count: 3.
- RQAlpha importable: true.
- RQAlpha version: `6.1.4`.
- Minimal local run attempted: false.
- Minimal local run succeeded: false.
- Data bundle/config requirement observed: likely required for normal RQAlpha execution; no bundle/provider setup was created.
- Fake fixture direct support observed: false.
- Output metrics available: false.
- Conclusion: RQAlpha installed and imported in the isolated environment, but fake-fixture-only local run support was not proven. Data bundle/config requirements need further review before any deeper prototype.

Unsupported A-share rules remain:

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

## Risks

- RQAlpha license/commercial suitability remains unresolved.
- RQAlpha may require data bundle/config setup before fake-fixture-only testing can proceed.
- RQAlpha includes trading-framework surfaces that must remain isolated from QuantPilot core.
- No production adapter exists.
- No real backtest evidence exists from this phase.
- No final backtest engine selection has been made.

## Recommended Next Step

ChatGPT should perform Phase 6C-3B closure review before any adapter implementation, deeper RQAlpha work, or final engine-selection discussion.
