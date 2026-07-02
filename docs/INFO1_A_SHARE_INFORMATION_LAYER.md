# INFO1 A-Share Information Layer

INFO1 adds a narrow securities-firm-style information substrate for future
QuantPilot agents. It defines normalized in-memory schemas for information that
research, strategy, risk, and review agents may later consume alongside market
data.

The layer currently covers:

- news events
- macro and policy events
- social sentiment events
- northbound and foreign-capital holdings
- stabilization and ETF-flow clues
- public fund holdings
- shareholder snapshots
- dividend records
- valuation snapshots
- concept and theme memberships
- margin-trading snapshots
- money-flow snapshots
- announcement events

Each normalizer accepts a pandas DataFrame that has already been loaded by the
caller, resolves common provider aliases, and emits a deterministic normalized
DataFrame with date or datetime fields, source, provider, evidence text, and
schema-specific numeric or text fields. Symbol-level schemas canonicalize common
A-share symbol formats to `000001.SZ` style identifiers.

INFO1 is intentionally only a contract and normalization layer. It does not
fetch external data, configure credentials, create orders, issue trade
instructions, call model services, run training workflows, or claim prediction
accuracy, profitability, or production readiness.
