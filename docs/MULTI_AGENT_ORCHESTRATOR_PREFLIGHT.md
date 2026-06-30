# R27 Multi-Agent Orchestrator Preflight

R27 adds a deterministic preflight layer for the future multi-agent orchestration path.

It does not run agents, call DeepSeek, call the network, connect to brokers, place orders, mutate accounts, train models, update live strategy weights, run Qlib, or run RQAlpha. It is a contract and validation boundary for deciding whether a proposed multi-agent pipeline is safe enough to proceed to a later runtime phase.

## Canonical Pipeline Order

The canonical R27 order is:

1. Runtime router
2. PIT feature store
3. News / event agent
4. Account profile
5. AI action bridge
6. Paper ledger dry run
7. Multi-day replay
8. Performance attribution
9. Small-capital readiness
10. Broker sandbox preflight

R27 enforces the key dependencies between these stages:

- runtime routing must precede agent-facing stages
- PIT feature store must precede news / event processing
- account profile must precede AI action bridge
- AI action bridge must precede paper ledger dry run
- paper ledger dry run must precede multi-day replay
- multi-day replay must precede performance attribution
- performance attribution must precede small-capital readiness
- small-capital readiness must precede broker sandbox preflight

## Hard Gates

Core control stages must be present and marked required:

- runtime router
- PIT feature store
- account profile
- AI action bridge
- paper ledger dry run
- multi-day replay
- performance attribution
- small-capital readiness

The news / event stage can be optional in a plan, but if present it must still appear after PIT feature validation. Optional failure creates a warning rather than a blocking failure.

Required stages must provide evidence references. Required failed, pending, or skipped stages block the plan.

## Manual Review

A required stage in manual review produces a manual-review decision when manual review is allowed.

If manual review is disabled, the same required manual-review stage blocks the plan. This keeps human escalation explicit instead of letting it become an implicit pass.

## Broker Sandbox Gating

Broker sandbox preflight is allowed only when `allow_broker_sandbox` is true.

When broker sandbox preflight is present:

- small-capital readiness must be present
- small-capital readiness must have passed
- broker sandbox preflight must come after readiness

This keeps the R26 broker sandbox handoff behind the R25 small-capital readiness gate.

## Preflight-Only Boundary

R27 is intentionally narrow. It validates the intended orchestration sequence and dependency state, but it does not perform runtime orchestration.

There is no:

- DeepSeek call
- network call
- broker connection
- account mutation
- order placement
- Qlib run
- RQAlpha run
- model training
- live strategy update

## Future Use

R27 prepares the control-plane contract for later runtime orchestration. Future phases can attach real orchestrator adapters, stats/factor stages, Qlib fixture checks, or RQAlpha dry-run preparation behind this preflight boundary.

Those future phases should continue to treat generic infrastructure as integration candidates and keep project-specific code focused on contracts, adapters, glue, A-share constraints, account/capital constraints, safety gates, orchestration boundaries, and validation layers.
