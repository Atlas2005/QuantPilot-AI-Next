# Open-Source Replacement Strategy

R1 makes integration review a first-class architecture layer.

QuantPilot should avoid building large custom modules before reviewing whether mature external tools can be adopted, wrapped, prototyped, benchmarked, deferred, or avoided.

## Replacement Paths

`adopt`
: Use directly after future review, tests, dependency approval, and license approval.

`wrap`
: Keep QuantPilot contracts stable and place the external tool behind an adapter.

`prototype`
: Test in an isolated environment before any adapter decision.

`benchmark_only`
: Use as a workflow, architecture, or metric reference without integration.

`defer`
: Revisit when prerequisite gates are complete.

`avoid`
: Keep out of the project under the current risk posture.

## R1 Candidate Areas

- A-share data providers: AkShare, Baostock, Tushare, SimTradeData
- A-share and quant platforms: Hikyuu, Qlib
- backtest engines: RQAlpha, vectorbt, Backtrader
- data quality: Pandera, Great Expectations
- factor and performance analytics: Alphalens Reloaded, empyrical, quantstats
- agent runtimes: LangGraph, OpenAI Agents SDK, CrewAI, AutoGen
- execution platform benchmark: vn.py / VeighNa

## Replacement Rule

Any future module proposal should state:

- what custom module would be built
- which external candidates were reviewed first
- whether the candidate should be adopted, wrapped, prototyped, benchmarked, deferred, or avoided
- why the choice moves the project closer to capital-test readiness

R1 does not install or select any external package.
