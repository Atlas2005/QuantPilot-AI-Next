# INFO2 Information Decision Agents

INFO2 Phase 1 converts INFO1 normalized A-share information frames into deterministic, evidence-backed information signals. It is a pandas-only in-memory layer.

## Scope

Phase 1 includes exactly three agents:

- `run_news_impact_agent`: consumes normalized news and announcement frames, then infers positive, negative, neutral, or mixed event impact from sentiment, importance, and announcement severity clues.
- `run_northbound_flow_agent`: consumes normalized northbound holding frames, then infers accumulation, distribution, or neutral flow state from holding changes and net-buy evidence.
- `run_liquidity_regime_agent`: consumes normalized macro/policy, margin, money-flow, and stabilization clue frames, then infers expansion, contraction, or neutral liquidity regime.

The aggregation entrypoint is `build_information_decision_report`, which combines agent signals into `aggregate_bias`, `aggregate_score`, conflicts, limitations, and the original signals.

## Contracts

The typed contracts live in `quantpilot_core.information_agents`:

- `InformationAgentRole`
- `InformationDirection`
- `InformationHorizon`
- `InformationAgentSignal`
- `InformationDecisionReport`

Each signal includes:

- `agent_role`
- `target`
- `direction`
- `score`
- `confidence`
- `horizon`
- `regime`
- `evidence`
- `limitations`

## Registry Tools

The default `ToolRegistry` exposes these INFO2 tools as `PURE_IN_MEMORY`:

- `run_news_impact_agent`
- `run_northbound_flow_agent`
- `run_liquidity_regime_agent`
- `build_information_decision_report`

## Boundaries

INFO2 Phase 1 does not fetch data, call model services, manage credentials, connect to execution systems, create orders, emit buy/sell recommendations, or run training workflows. It only summarizes supplied normalized frames into deterministic information evidence.

The northbound flow agent always includes this limitation: northbound holding frequency may be quarterly after 2024-08-19.

These outputs are information-layer diagnostics only. They do not claim prediction accuracy, profitability, or production readiness.
