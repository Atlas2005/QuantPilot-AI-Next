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
- professional terminal benchmarks
- open-source financial terminal candidates

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
- candidate type
- benchmark role
- integration policy

## Professional Terminal Benchmarks

Professional terminals such as Bloomberg Terminal, LSEG Workspace, FactSet, Wind Financial Terminal, iFinD, and Choice Financial Terminal are product and workflow benchmarks.

They may help future review think about user workflows, financial terminal information density, analytics surfaces, portfolio views, and product expectations. They are not dependencies, not integration targets, and not candidates for direct use.

Proprietary terminals can guide product/workflow design but must not be treated as software components to integrate, clone, or emulate in a legally risky way.

## Open-Source Financial Terminal Candidates

Open-source terminal or dashboard projects such as FinceptTerminal and OpenBB Platform / OpenBB Terminal are recorded as candidates for future review only.

Terminal-like projects can carry significant commercial, licensing, and derivative-work risk. AGPL or commercial-license-sensitive terminal projects require explicit license review before cloning, copying, integrating, commercializing, or deriving product work from them.

Phase 1.1 does not install, import, clone, integrate, or select any terminal/dashboard project.

## Benchmark, Dependency, Adapter, and Architecture Reference

Benchmark:
: A product or workflow reference. It is not integrated into QuantPilot-AI 2.0.

Dependency:
: A package or tool that would be installed or required by the project. Phase 1.1 adds no terminal dependencies.

Adapter:
: A future wrapper around an external system that must satisfy contracts and tests after ChatGPT-led review.

Architecture reference:
: A source of design ideas only. It does not permit copying source code or bypassing license review.

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

## integration_policy Meanings

`no_integration_reference_only`
: Candidate is reference-only and must not be integrated.

`registry_only`
: Candidate is recorded only.

`prototype_later`
: A future prototype may be considered after review.

`adapter_later`
: A future adapter may be considered after review and contract readiness.

`license_review_required`
: No cloning, copying, integration, commercial use, or derivative work before explicit license review.

`avoid_for_now`
: Candidate should not be used under current conditions.

## Module Boundary Rule

At every major module boundary, ChatGPT should refresh open-source alternatives before Codex implementation begins.

External projects must later enter through adapters and contract tests. Phase 1 creates the registry only.
