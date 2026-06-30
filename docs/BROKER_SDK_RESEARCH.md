# P33 Broker SDK Research

P33 creates an isolated broker SDK research boundary for comparing A-share broker integration options without integrating any broker into the production execution path.

This is research and preflight only. It does not connect to a broker, read a real account, submit orders, store credentials, import vendor SDKs in the default runtime, or create a live trading route.

## Purpose

After P31 real data stability and P32 offline Qlib runtime planning, the next safe question is not "which broker do we connect to?" It is "which broker integration path deserves isolated manual research?"

P33 answers that with metadata-only contracts and reports:

- candidate identity and boundary type
- license, source, and maintenance classification
- supported markets and asset classes
- account-read capability classification
- order-submission capability classification
- sandbox or paper availability
- credential handling boundary
- default network/runtime boundary
- manual approval requirement
- A-share rule acknowledgement

## Candidate Boundaries

P33 models these research options:

- vn.py style boundary
- QMT / MiniQMT style gateway boundary
- easytrader style boundary
- broker native SDK boundary
- manual CSV / semi-manual execution boundary

These are metadata classifications only. P33 does not import, install, or invoke any of these tools.

## Required Safety Classifications

Each candidate must declare:

- license
- source
- maintenance status
- supported market
- sandbox or paper mode availability
- manual approval requirement
- integration boundary evidence
- forbidden-scope evidence

Account-read capability may be classified, but it must be disabled by default. Order-submit capability may be classified, but it must be disabled by default.

## A-Share Constraints

Every candidate must acknowledge:

- 100-share lot
- T+1
- price limit
- suspension
- fees
- stamp duty
- sellable quantity

Missing A-share constraints block the candidate.

## Forbidden Scope

P33 blocks metadata that implies:

- repository credential handling
- default network dependency
- vendor SDK import in default runtime
- live order path
- account-read enabled by default
- order-submit enabled by default
- missing manual approval

This package intentionally avoids executable broker connectivity.

## Report Output

`build_broker_research_report` emits:

- recommended research priority
- blockers
- warnings
- manual investigation checklist
- integration boundary evidence
- forbidden scope evidence

Candidates with no blockers or warnings are `research_ready`. Candidates with warnings are `manual_review`. Candidates with critical safety gaps are `blocked`.

## Safety Boundary

P33 does not:

- install broker SDKs
- import broker SDKs
- connect to brokers
- read real accounts
- submit orders
- store credentials
- handle secrets
- call DeepSeek
- call OpenAI
- call the network in default tests
- create production execution routes

## Recommended Next Step

Use P33 reports to pick a single candidate for a separate isolated manual investigation branch. Any future broker work must remain behind manual approval, sandbox-only boundaries, account/capital checks, and the existing broker sandbox preflight.
