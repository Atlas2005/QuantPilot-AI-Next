# Review Packet

## Task Name

P33: Broker SDK Research in Isolated Branch.

## Changed Files

- `docs/BROKER_SDK_RESEARCH.md`
- `docs/REVIEW_PACKET.md`
- `src/quantpilot_core/broker_sdk_research/__init__.py`
- `src/quantpilot_core/broker_sdk_research/contracts.py`
- `src/quantpilot_core/broker_sdk_research/report.py`
- `src/quantpilot_core/broker_sdk_research/validation.py`
- `tests/broker_sdk_research/test_broker_sdk_research.py`

## Safety Checks

- `src/` changed: Yes. Added standard-library-only P33 broker SDK research contracts, metadata validation, and deterministic research report generation.
- Tests changed: Yes. Added P33 offline broker SDK research tests.
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
- Model training added: No.
- Live strategy weight update added: No.
- Real account API read: No.
- Broker connection added: No.
- Vendor broker SDK imported: No.
- Paper ledger persistence write added: No.
- Live order path added: No.
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

P33 keeps new `src/` code on Python standard library only. It adds metadata-only broker SDK research contracts, candidate safety validation, A-share constraint validation, deterministic priority ranking, and manual investigation checklist generation.

P33 does not install or import broker SDKs, connect to brokers, read real accounts, place orders, create credential handling, call DeepSeek, call OpenAI, perform network calls in tests, train models, update live strategy weights, run Qlib/qrun, or run RQAlpha.

P33 compares broker integration candidates as research metadata only: vn.py style, QMT / MiniQMT style, easytrader style, broker native SDK, and manual CSV / semi-manual boundary.

## Validation Commands and Results

`python -m compileall src`

Result: not run because bare `python` is not available in this shell.

```text
zsh:1: command not found: python
```

`python -m pytest tests/broker_sdk_research`

Result: not run because bare `python` is not available in this shell.

```text
zsh:1: command not found: python
```

`.venv/bin/python -m compileall src`

Result: passed.

`.venv/bin/python -m pytest tests/broker_sdk_research`

Result: passed.

```text
platform darwin -- Python 3.12.10, pytest-9.1.1
collected 16 items
16 passed in 0.01s
```

`.venv/bin/python -m pytest`

Result: passed.

```text
platform darwin -- Python 3.12.10, pytest-9.1.1
collected 647 items
647 passed in 0.32s
```

## P33 Broker SDK Research Summary

P33 adds an isolated, metadata-only research boundary for A-share broker SDK candidates.

The research validator checks license, source, maintenance status, supported market, account-read and order-submit boundaries, sandbox/paper declaration, credential handling, default network safety, vendor SDK import safety, live order-path safety, manual approval, A-share constraints, integration evidence, and forbidden-scope evidence.

The report emits deterministic research priorities, blockers, warnings, manual investigation checklist items, integration boundary evidence, and forbidden-scope evidence.

## Risks

- P33 is research-only; it does not approve or implement broker connectivity.
- Future broker work must remain in a separate isolated branch and behind manual approval.
- Credential handling, account reads, live order paths, and vendor SDK imports remain forbidden in default runtime.

## Recommended Next Step

Run closure review for P33. A future isolated branch may perform manual investigation for exactly one selected candidate while keeping credentials, account reads, and order submission outside the repository runtime.

## Code Evidence Snapshot

- `contracts.py`: defines metadata-only candidate contracts including `BrokerSdkCandidate`, `BrokerCapabilityProfile`, `BrokerPermissionBoundary`, `SandboxAvailabilityProfile`, `AccountReadBoundary`, `OrderSubmissionBoundary`, and `BrokerResearchReport`.
- `validation.py`: blocks missing license/source/maintenance, default account-read or order-submit permissions, missing sandbox/paper declaration, repository credential handling, default network dependency, vendor SDK import requirement, live order path, missing manual approval, and missing A-share constraints.
- `report.py`: builds candidate reports, deterministic priority ranking, blockers, warnings, manual investigation checklist, integration boundary evidence, and forbidden-scope evidence.
- `tests`: cover valid metadata, missing license/source/maintenance classification, live order path rejection, credential handling rejection, vendor SDK import rejection, missing sandbox declaration, missing A-share constraints, priority ranking, forbidden scope evidence, and offline deterministic report shape.
