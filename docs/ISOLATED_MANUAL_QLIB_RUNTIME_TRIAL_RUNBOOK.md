# P43 Isolated Manual Qlib Runtime Trial Runbook

P43 makes the next manual Qlib runtime trial executable in an isolated environment without polluting the default project environment.

This stage does not install Qlib, modify `pyproject.toml`, run qrun in default tests, require Qlib for pytest, connect to brokers, call LLM runtimes, fetch network data, or claim real profitability.

## Objective

P43 answers:

- is the project ready for an isolated manual Qlib runtime trial?
- did the default pytest environment remain unchanged?
- did the project avoid dependency-file changes?
- is there an artifact checklist?
- are manual command templates provided?
- is a P42-compatible result capture template provided?
- is qrun still not executed by default?
- is Qlib still optional?
- is the safety barrier still at or below `140%`?

## Isolated Environment Plan

The runbook supports:

- isolated virtual environment
- Conda environment
- optional container environment

The plan records:

- environment type and name
- default project environment unchanged
- project dependency files unchanged
- Qlib as optional dependency
- installation commands as documentation only
- Python version note
- cleanup commands
- rollback notes
- warnings

No package installation is performed by this patch.

## Artifact Checklist

Required artifacts:

- P41 dataset spec
- P41 workflow config
- P41 factor mapping
- P42 manual execution plan
- approved local provider export sample
- cost model assumptions
- execution assumptions
- benchmark candidate
- result import template

Each checklist item records whether it is required, present, source module, validation note, and blocker if missing.

## Manual Command Plan

The command plan provides templates only:

- isolated environment creation command
- optional Qlib installation command
- dataset preparation command placeholder
- qrun or by-code runtime command template
- result export command placeholder
- result import command placeholder

Commands are documentation only. Default tests do not execute qrun. The plan contains no broker, account, or credential commands and uses local filesystem paths.

## Result Capture Template

The result capture template aligns with the P42 import boundary:

- local result source
- dataset id
- workflow config id
- benchmark
- stock count
- ETF count
- IC / RankIC or missing reason
- cost-aware metric or missing reason
- manual/import-only execution mode
- `profitability_claim = false`
- warnings

## Safety Boundary

P43 does not:

- install Qlib in the default environment
- modify `pyproject.toml`
- execute qrun in default tests
- require Qlib for default pytest
- connect to brokers
- read accounts
- place orders
- call DeepSeek
- call OpenAI
- make network calls in default tests
- claim real profitability

## Recommended Next Step

Use this runbook to manually run Qlib inside an isolated environment, then capture the local runtime result record and import it through the P42 boundary.
