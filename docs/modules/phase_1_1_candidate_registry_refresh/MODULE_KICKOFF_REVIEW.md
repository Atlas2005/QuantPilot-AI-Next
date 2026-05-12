# Module Kickoff Review: Phase 1.1 Candidate Registry Refresh Patch

This document records the ChatGPT-approved Phase 1.1 correction. It is not Codex's independent strategic judgment.

## Reason for Patch

After Phase 2, ChatGPT identified that Phase 1 underrepresented professional financial terminals, terminal-like product benchmarks, and open-source financial terminal/dashboard candidates.

## Purpose

Patch the candidate registry so QuantPilot-AI 2.0 tracks professional terminal/product benchmarks, open-source financial terminal/dashboard candidates, and commercial/license risk for terminal-like projects.

## Upstream

- Phase 1 candidate registry
- Phase 2 core contracts

## Downstream

- Phase 3 data contracts
- future dashboard/productization

## Allowed Scope

- Python standard library only
- existing pytest dev dependency
- static candidate metadata updates
- registry schema extension
- tests for terminal benchmark records and license-risk fields
- documentation and review packet updates

## Prohibited Scope

- external integration
- package installation
- terminal cloning
- source-code copying
- dashboard implementation
- trading terminal implementation
- broker/order/execution paths
- live trading
- backtesting
- model training
- agent orchestration
- final product architecture selection
- trading-readiness claims
- profitability claims

## Success Criteria

- registry supports `candidate_type`, `benchmark_role`, and `integration_policy`
- older candidate records remain loadable through conservative defaults
- Bloomberg Terminal is reference-only
- FinceptTerminal requires license review and has high commercial risk
- professional terminal benchmarks are not approved for adapters
- all candidates remain conservative for Phase 1.1
- `python -m compileall src` passes
- `python -m pytest` passes

