# Phase 6C-3A Module Kickoff Review

This document records the ChatGPT-approved kickoff review for Phase 6C-3A. Codex is not the project architect and is only implementing the scoped RQAlpha preflight review package.

## Purpose

Create an RQAlpha preflight package before any isolated prototype run.

## Upstream

- Phase 6A backtest engine evaluation
- Phase 6B prototype isolation plan
- Phase 6C-1 vectorbt prototype
- Phase 6C-1.1 environment isolation policy
- Phase 6C-2 Backtrader prototype

## Downstream

Possible Phase 6C-3B isolated RQAlpha prototype.

## Why RQAlpha Is Relevant

RQAlpha is relevant because it is a Python algorithmic backtest/trading framework with China-market relevance. That makes it worth reviewing for A-share-style research.

## Why RQAlpha Is Sensitive

RQAlpha is also sensitive because it is a backtest/trading framework. License, maintenance, Windows compatibility, dependency footprint, data bundle behavior, A-share rule fit, and broker/live/order isolation must be reviewed before any install or prototype.

## Scope

Allowed:

- create static preflight metadata
- add a standard-library metadata validator
- document review questions and future prototype requirements
- add validation tests

Prohibited:

- no install
- no import
- no backtest
- no adapter
- no final selection
- no market data/API use
- no broker/live/order path

## Success Criteria

- RQAlpha preflight metadata exists and remains conservative.
- Validation proves install/import/prototype/final selection are disabled in this phase.
- Future RQAlpha work is gated on `.venv-prototypes/rqalpha/`.
- Review packet records that no RQAlpha installation, import, or prototype occurred.
