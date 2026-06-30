# Cost-Aware DeepSeek Runtime Router Preflight

R17 adds a contract-only runtime routing layer for future DeepSeek-backed agents.

## Why R17 Exists

R16 defined typed multi-agent contracts and safety preflight. R17 adds the next missing control plane: cost-aware and time-window-aware routing before any future model runtime call can happen.

This stage still performs no real DeepSeek call. It has no network access, no API keys, no secrets, and no model SDK dependency.

## DeepSeek-First, Provider-Agnostic

R17 supports DeepSeek as the intended first AI runtime provider while keeping the provider field explicit. The only providers modeled in this stage are:

- DEEPSEEK
- FAKE

No Qwen, Gemini, OpenAI, Claude, LangGraph, CrewAI, broker, or live-trading runtime is introduced.

## Flash / Pro Routing

Supported models are:

- `deepseek-v4-flash`
- `deepseek-v4-pro`

Deprecated names such as `deepseek-chat` and `deepseek-reasoner` are rejected.

Routing is deterministic:

- low-cost, news, data-quality, and stat-summary tasks use Flash
- factor and market-regime tasks use Pro outside peak hours and Flash during peak unless critical
- risk review uses Pro if critical or when a proposed trade exists
- supervisor decisions use Pro when critical, otherwise Flash during peak and Pro outside peak
- account and execution hard gates use no LLM

## Peak-Hour Policy

R17 uses deterministic BJT peak windows:

- 09:00-12:00
- 14:00-18:00

No external timezone library is used.

## Cost Budget Policy

Each request carries:

- maximum USD per run
- maximum USD per day
- maximum tokens per agent call
- defer policy

Model prices are configurable. Defaults use fields for cache-hit input, cache-miss input, output, and a peak multiplier so future pricing updates can be made without rewriting routing logic.

## No Runtime Side Effects

R17 includes a `FakeAIClient` only. It refuses invalid route decisions, refuses no-LLM decisions, and returns deterministic fake responses for valid LLM decisions.

There are no real API calls, no network calls, no keys, no live trading, no broker access, no Qlib/RQAlpha execution, and no real news crawling.

## Hard Gates Use No LLM

Account and execution hard gates are deterministic safety gates. They do not use an LLM because they must remain reproducible, auditable, and cost-free.

## Multi-Agent Cost Control

Cost-aware routing protects against cost explosion in multi-agent loops by:

- preferring Flash for low-cost and peak-hour non-critical work
- enforcing per-call token limits
- enforcing per-run and per-day cost limits
- deferring over-budget calls when policy allows

## Next Stage

Recommended next stage: PIT Data & Feature Store Preflight.
