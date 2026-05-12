# Open-Source Candidate Universe

This file records the candidate universe policy. The structured candidate registry is stored in:

```text
data/open_source_candidates/candidates.json
```

Phase 1 does not install, import, integrate, approve, or select any candidate.

## Classification System

Each candidate should later be classified as one of:

- `adopt_directly`
- `wrap_with_adapter`
- `borrow_architecture_only`
- `prototype_required`
- `defer_until_foundation_ready`
- `avoid_for_now`

## Data Sources

- AkShare
- Baostock
- Tushare
- OpenBB
- Qlib data workflow
- future paid/vendor data source

## Data Quality and Storage

- Pandera
- Great Expectations
- Polars
- DuckDB
- PyArrow / Parquet
- DVC later

## Research and Backtesting

- Qlib
- LEAN
- vectorbt
- vn.py / VeighNa
- Backtrader
- RQAlpha
- Zipline-reloaded
- NautilusTrader
- backtesting.py
- bt

## Factor, Performance, and Portfolio Analytics

- Alphalens
- quantstats
- pyfolio / empyrical
- PyPortfolioOpt
- riskfolio-lib

## Agent / LLM / Workflow

- TradingAgents
- FinRobot
- FinGPT
- RD-Agent
- LangGraph
- AutoGen
- CrewAI
- OpenAI Agents SDK
- OpenAI Skills
- Scrapling
- MCP ecosystem
- Warp
- Ruflo

## Professional Terminal / Product Benchmarks

- Bloomberg Terminal
- LSEG Workspace
- FactSet
- Wind Financial Terminal
- iFinD
- Choice Financial Terminal

## Open-Source Financial Terminal / Dashboard Candidates

- FinceptTerminal
- OpenBB Platform / OpenBB Terminal

Terminal-like projects are not automatically safe to integrate. Proprietary terminals are product/workflow benchmarks only, and open-source terminal projects require license and commercial-risk review before any cloning, copying, integration, commercialization, or derivative work.

## Agent Timing Constraint

Agent orchestration is late-stage. TradingAgents, LangGraph, AutoGen, CrewAI, OpenAI Agents SDK, and OpenAI Skills should not be integrated before data, contracts, validation, and backtest foundations are stable.
