# RQAlpha Preflight Review

RQAlpha is being reviewed because it is a Python algorithmic backtest/trading framework with China-market relevance. That relevance is promising for A-share-style research, but it is not enough for selection.

## Phase 6C-3A Boundary

RQAlpha is not installed in Phase 6C-3A.

RQAlpha is not imported in Phase 6C-3A.

No RQAlpha prototype, backtest, adapter, or final engine selection is made in Phase 6C-3A.

## Checks Required Before Installation

Before any future isolated prototype, ChatGPT must review:

- license and commercial use risk
- maintenance and release activity
- Windows compatibility
- dependency footprint
- data bundle requirements
- whether RQAlpha can use local fake fixture data
- A-share market rule coverage
- T+1 behavior
- lot size behavior
- price-limit handling
- suspension handling
- fees and slippage assumptions
- broker/live/order path isolation

## Future Phase 6C-3B Requirements

If ChatGPT approves a future RQAlpha prototype, it must follow these rules:

- use isolated `.venv-prototypes/rqalpha/`
- no `pyproject.toml` change
- no main environment install
- fake fixture only
- no real market data
- raw outputs stay under `local_artifacts/`
- no adapter
- no final engine selection
- no broker/live/order path

## Current Status

Phase 6C-3A creates only static preflight metadata and validation tests. It does not prove RQAlpha compatibility, A-share realism, profitability, or production readiness.
