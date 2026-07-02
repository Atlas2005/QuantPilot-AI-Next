# INFO3 Extended Information Agents

INFO3 extends the INFO2 deterministic information-agent layer over INFO1 normalized A-share frames. It is not a normalizer layer and does not fetch data.

## Added Roles

INFO3 reuses the existing typed contracts:

- `InformationAgentRole`
- `InformationDirection`
- `InformationHorizon`
- `InformationAgentSignal`
- `InformationDecisionReport`

New role values:

- `fund_positioning_agent`
- `valuation_agent`
- `concept_rotation_agent`
- `shareholder_dividend_agent`
- `moneyflow_structure_agent`

## Added Agents

- `run_fund_positioning_agent`: consumes normalized `fund_holdings` and summarizes fund positioning, concentration, crowding, and style-pressure evidence.
- `run_valuation_agent`: consumes normalized `valuation_snapshots` and `dividend_records` and summarizes valuation support or pressure using levels, optional percentile-style fields, dividend clues, and evidence text.
- `run_concept_rotation_agent`: consumes normalized `concept_memberships`, `news_events`, and `social_sentiment_events` and summarizes active, weak, or mixed concept-rotation evidence.
- `run_shareholder_dividend_agent`: consumes normalized `shareholder_snapshots`, `dividend_records`, and `announcement_events` and summarizes shareholder support or risk evidence.
- `run_moneyflow_structure_agent`: consumes normalized `moneyflow_snapshots` and summarizes institutional/retail flow-structure evidence.

## Registry Tools

The default `ToolRegistry` exposes all INFO3 agents as `PURE_IN_MEMORY`:

- `run_fund_positioning_agent`
- `run_valuation_agent`
- `run_concept_rotation_agent`
- `run_shareholder_dividend_agent`
- `run_moneyflow_structure_agent`

## Boundaries

INFO3 is pandas-only and in-memory. It does not download data, call external model services, manage credentials, connect to execution systems, create orders, emit buy/sell recommendations, or run training workflows.

Outputs are evidence-backed information diagnostics only. They do not claim prediction accuracy, profitability, or production readiness.
