# Open-Source Candidate Registry

The open-source candidate registry records external projects that may later be evaluated before QuantPilot-AI 2.0 builds major modules from scratch.

Phase 1 does not install, import, integrate, approve, or select any candidate.

## Registry Location

Candidate metadata is stored in:

```text
data/open_source_candidates/candidates.json
```

## Why This Exists

QuantPilot-AI 2.0 is open-source-first. Before custom implementation, external projects must be reviewed for license safety, maintenance, Windows compatibility, A-share fit, integration cost, reliability, and testability.

## Candidate Categories

- data sources
- data quality and storage
- research and backtesting
- factor, performance, and portfolio analytics
- agent, LLM, and workflow tooling

## Evaluation Fields

Each candidate records:

- name
- category
- subcategory
- homepage
- repository
- description
- primary use
- current phase action
- evaluation status
- recommended action
- license review status
- commercial risk
- maintenance risk
- Windows risk
- A-share relevance
- integration risk
- phase allowed
- notes

## recommended_action Meanings

`adopt_directly`
: Candidate may later be used directly after review. Not used as approval in Phase 1.

`wrap_with_adapter`
: Candidate may later enter through an adapter and contract tests. Not used as approval in Phase 1.

`borrow_architecture_only`
: Candidate may inform design without integration.

`prototype_required`
: Candidate needs a controlled future prototype before any decision.

`defer_until_foundation_ready`
: Candidate should wait until contracts, validation, and upstream foundations are stable.

`avoid_for_now`
: Candidate is not suitable for current project needs or risk posture.

## phase_allowed Meanings

`registry_only`
: Record only. No prototype or adapter is allowed yet.

`prototype_later`
: A future prototype may be considered after ChatGPT-led review.

`adapter_later`
: A future adapter may be considered after ChatGPT-led review and contract readiness.

`deferred`
: Do not act until later foundations exist.

## Module Boundary Rule

At every major module boundary, ChatGPT should refresh open-source alternatives before Codex implementation begins.

External projects must later enter through adapters and contract tests. Phase 1 creates the registry only.

