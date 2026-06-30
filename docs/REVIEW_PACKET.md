# Review Packet

## Task Name

R19: News / Event Agent Preflight.

## Changed Files

- `docs/NEWS_EVENT_AGENT_PREFLIGHT.md`
- `docs/REVIEW_PACKET.md`
- `src/quantpilot_core/news_event_agent_preflight/__init__.py`
- `src/quantpilot_core/news_event_agent_preflight/contracts.py`
- `src/quantpilot_core/news_event_agent_preflight/pit_bridge.py`
- `src/quantpilot_core/news_event_agent_preflight/preflight.py`
- `tests/news_event_agent_preflight/test_news_event_agent_preflight.py`

## Safety Checks

- `src/` changed: Yes. Added standard-library-only R19 news/event contracts, validation, and PIT bridge.
- Tests changed: Yes. Added R19 offline news/event preflight tests.
- Local fixture changed: No.
- Integration matrix changed: No.
- Open-source decision table changed: No.
- Manual probe scripts changed: No.
- Dependencies changed: No.
- Packages installed: No.
- Packages uninstalled: No.
- `pyproject.toml` changed: No.
- Market data/API used during implementation: No.
- Provider API called during implementation: No.
- Production data assets written: No.
- Manual probes run: No.
- Real data fetched: No.
- Raw data committed: No.
- Any data source approved: No.
- Full data provider implementation added: No.
- Real news crawling added: No.
- DeepSeek/API call added: No.
- Real alpha evidence produced: No.
- Statistical significance claimed: No.
- External analytics installed/imported: No.
- Broker/live/order submission path created: No.
- Real backtest/model/agent implementation added: No.
- Full backtest/risk/factor/calendar/accounting engine added: No.
- External frameworks installed/imported in `src/`: No.
- Final technical selections made: No.
- Profitability claim made: No.

## Language / Runtime Decision

R19 keeps new `src/` code on Python standard library only. It adds typed contracts, deterministic validation, and an in-memory bridge from structured event findings to R18 PIT feature records.

R19 does not crawl news, call DeepSeek, call provider APIs, implement a live agent runtime, implement feature-store materialization, add broker integration, add live trading, add order generation, run Qlib, or run RQAlpha.

R19 reuses R18 PIT validation as the event-derived feature boundary, so future news/event agents cannot bypass point-in-time visibility checks.

## Validation Commands and Results

`python -m compileall src`

Result: not run because bare `python` is not available in this shell.

```text
zsh:1: command not found: python
```

`python -m pytest tests/news_event_agent_preflight`

Result: not run because bare `python` is not available in this shell.

```text
zsh:1: command not found: python
```

`.venv/bin/python -m compileall src`

Result: passed.

`.venv/bin/python -m pytest tests/news_event_agent_preflight`

Result: passed.

```text
platform darwin -- Python 3.12.10, pytest-9.1.1
collected 15 items
15 passed in 0.01s
```

`.venv/bin/python -m pytest`

Result: passed.

```text
platform darwin -- Python 3.12.10, pytest-9.1.1
collected 405 items
405 passed in 0.19s
```

## R19 News / Event Agent Preflight Summary

R19 adds an offline deterministic preflight for structured news/event findings.

The preflight validates event metadata, temporal availability, sentiment score bounds, confidence bounds, impact score bounds, affected-symbol requirements, rumor/critical risk flags, and structured-output requirements.

The PIT bridge emits deterministic feature keys for each affected symbol:

- `news.sentiment`
- `news.risk_level_numeric`
- `news.impact_score`
- `news.event_type_numeric`
- `news.confidence`

The emitted records are validated by R18 PIT preflight and blocked when they are not available as of the requested time.

## Risks

- R19 is a contract/preflight layer only; it does not prove real news source quality or model extraction quality.
- Future model output must still be forced through these structured contracts before sandbox use.
- Event-derived feature quality depends on truthful event, known, and trading-availability timestamps from future adapters.

## Recommended Next Step

Run closure review for R19. The next phase can harden Account Profile / Broker Config preflight or add a Stats Agent preflight, depending on project priority.
