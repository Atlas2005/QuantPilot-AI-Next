# QMT Simulation Order Loop V1 Runbook

## Purpose and scope

PR #127 provides one deliberate broker-simulation order loop:

```text
canonical QuantPilot order intent
  -> authenticated atomic intent file
  -> dedicated QMT built-in Python executor
  -> one passorder attempt
  -> QMT order/deal readback
  -> atomic acknowledgement/result
```

This is a manual, single-order acceptance path. It is not a trading daemon. It does not generate candidates, consume `continuous_paper`, call DeepSeek, poll continuously, cancel orders, or repeat execution. Those continuous behaviors are outside PR #127 and belong to PR #128 or later.

Only a broker simulation/test `STOCK` account is allowed. Never select a real-money account. The protocol cannot prove from QMT data alone that an account is non-real, so the operator must verify the selected account in the QMT UI before every acceptance run. Do not put an account number or credentials in a command, strategy, JSON file, log, screenshot, or report.

The real broker-simulation run exposed an execution-lifecycle compatibility limitation: QMT logged `start trading mode`, but no state or acknowledgement appeared, the authenticated intent remained `received` with `passorder_attempted=false`, and the intent expired. Separate read-only daily-period and one-minute-period checks also produced no fresh bridge file. Therefore, seeing `start trading mode` proves only that QMT started the model in that mode; it does **not** prove that QMT invoked `handlebar(ContextInfo)` or that `handlebar` had a usable broker context.

The expired intent from that run is historical evidence. It must never be resubmitted, recreated under another ID for the same economic order, or made executable by deleting its state or result.

## The QMT mode distinction is mandatory

QMT's **simulation signal mode does not send an order**. It is suitable for the separate PR #126 read-only exporter but cannot establish PR #127 broker-counter acceptance.

A real PR #127 acceptance run requires QMT **live trading mode** as the model execution mode while the model is bound to the broker's **simulation/test account**. Here, "live trading mode" is the QMT UI name for the model execution mode; it does not authorize a real-money account. Any QMT order-sending execution mode used by this runbook may only be bound to the broker simulation/test `STOCK` account and must never be bound to a real-money account. The required combination is:

| QMT model execution mode | Selected account | PR #127 outcome |
| --- | --- | --- |
| simulation signal mode | simulation/test account | No broker order is sent; not an acceptance run |
| live trading mode | simulation/test `STOCK` account | Required for the manual broker-simulation acceptance run |
| any order-sending mode | real-money account | Forbidden |

Stop if the selected account cannot be positively identified as the intended broker simulation/test account. PR #127 makes no claim that QMT can automatically detect a live account.

For this broker-specific acceptance run, treat **10:00-17:00** as the simulation-counter availability window supplied by the user. This is an operational constraint for this broker/test counter, not a universal QMT schedule or guarantee. Confirm the current broker notice and counter availability before the run; QMT may invoke the strategy outside that window without the counter matching the order.

## Protocol identity and filesystem layout

The protocol uses schema version `1` and protocol identifier `qmt_simulation_order_loop_v1`. Use the same configured bridge root as the PR #126 snapshot bridge, but keep all execution artifacts below a separate `execution` directory. The bridge root must be outside the Git repository.

```text
<bridge-root>\
  probe\
    lifecycle_probe_v1.json
  execution\
    diagnostics\
      executor_lifecycle_v1.json
    intents\
      <intent-id>.json
    acknowledgements\
      <intent-id>.json
    state\
      <intent-id>.json
  state\
    account_binding_key_v1.hex
```

Each `intent_id` owns one immutable intent path and one result identity. A different order never overwrites an existing intent. Writers create a temporary file in the destination directory, flush it, and atomically replace the completed path. Readers ignore temporary files. Runtime intent, acknowledgement, state, lock, and temporary files must remain outside Git.

`execution\intents` is an immutable history, not a single-use inbox that operators empty between runs. Completed `.json` intent files remain in place. Readers ignore temporary files and enumerate completed intent files deterministically. The executor uses associated state and acknowledgement/result evidence, when available, to classify history. Terminal intents and expired unattempted intents are not executable candidates; an expired unattempted intent receives an `expired` state/result when that update is safe and deterministic. An intent that was attempted or whose outcome is uncertain can never become executable again.

Execution proceeds only when exactly one completed intent is valid, authenticated, explicit-submit, unexpired, non-terminal, and otherwise executable. More than one executable candidate fails closed without calling `passorder`; zero executable candidates also performs no broker mutation. Operators do not delete historical intents to make a later acceptance run possible.

The existing `<bridge-root>\state\account_binding_key_v1.hex` is a local secret used both to derive the pseudonymous `qmtacct-v1-...` account binding and to authenticate intents. Never copy its bytes into an intent, result, command argument, report, or repository.

## Version 1 schemas

All JSON is bounded, canonical, UTF-8 JSON with finite numeric values, sorted deterministic keys, and no provider object representations or tracebacks. Timestamps are UTC. Unknown and missing fields are rejected.

### Intent

`execution\intents\<intent-id>.json` contains exactly one authenticated, executable limit-share order with these version 1 fields:

- `schema_version`: `1`;
- `protocol_version`: `qmt_simulation_order_loop_v1`;
- `intent_id`: the bounded client idempotency key;
- `created_at` and `expires_at`: UTC timestamps;
- `environment`: `broker_simulation`;
- `expected_redacted_account_id`: the expected `qmtacct-v1-...` binding, never a raw account ID;
- `account_type`: `STOCK`;
- `symbol`: canonical six-digit exchange-qualified symbol, for example `000001.SZ`;
- `side`: `buy` or `sell`;
- `quantity`: executable share quantity;
- `order_kind`: `shares_limit`;
- `limit_price`: finite, positive explicit limit price;
- `source_order_digest`: bounded digest of the upstream order identity;
- optional `run_label`: bounded source label;
- `explicit_submit`: exactly `true`;
- `intent_hmac`: HMAC-SHA256 over the deterministic canonical intent representation excluding the HMAC field itself.

The narrow adapter from `quantpilot_core.order_intent.OrderIntent` reuses `symbol`, `side`, `target_shares`, `run_label`, and a valid metadata order identity. `target_shares` becomes `quantity`. Advisory-only intents with only a target weight, missing share quantity, `hold`, or no explicit limit price cannot cross this broker boundary. Paper-trading or paper-ledger fill records are never broker acknowledgements.

Validation rejects unsupported versions, malformed symbols, unsupported sides, wrong account types, expired or future-skewed timestamps, account-binding mismatches, invalid HMACs, non-finite or non-positive prices, non-positive quantities, buys not divisible by 100, oversized files or text, `explicit_submit` values other than exactly `true`, and a bridge root inside the repository. This validation covers transport, identity, duplicate, and broker-shape safety; it is not a profitability or recommendation gate.

### Local execution state

`execution\state\<intent-id>.json` records only bounded lifecycle state for the matching intent. Its exact keys are `schema_version`, `protocol_version`, `intent_id`, `updated_at`, `status`, `expected_redacted_account_id`, `passorder_attempted`, and nullable bounded `failure_code`. The version 1 state vocabulary is:

```text
received
claimed
submission_attempted
broker_acknowledged
partially_filled
filled
rejected
expired
uncertain
```

The executor persists `claimed` and then `submission_attempted` atomically before invoking `passorder`. State contains no raw account identifier, binding key, credential, unrestricted broker message, or traceback.

### Acknowledgement/result

`execution\acknowledgements\<intent-id>.json` is the one bounded result identity for the intent. Its exact version 1 keys are:

- `schema_version`, `protocol_version`, `intent_id`, and UTC `generated_at`;
- lifecycle `status` and `expected_redacted_account_id`;
- `symbol`, `side`, `requested_quantity`, and `limit_price`;
- fixed `strategy_name`, `user_order_id`, and `passorder_attempted`;
- bounded nullable `broker_order_reference`, `system_order_id`, `order_status`, and `submission_status`;
- `filled_quantity`, nullable `average_fill_price`, and `deal_count`;
- bounded nullable `failure_code` and `failure_type`;
- nullable `latest_snapshot_sequence` when PR #126 snapshot evidence is available;
- `acceptance_limitation`, fixed to `qmt_live_trading_mode_with_broker_simulation_account_only`.

The result never contains a raw account ID, shareholder ID, password, key material, unrestricted broker error text, provider `repr`, or traceback. `broker_acknowledged` requires a matching QMT order record. `filled` requires matching QMT deal evidence or equivalent reconciled filled quantity; a `passorder` call alone is not evidence of broker acceptance. Filled quantity cannot exceed requested quantity.

### Read-only lifecycle probe record

`probe\lifecycle_probe_v1.json` is an atomically replaced, canonical JSON observation record written by `scripts/qmt_builtin_lifecycle_probe_v1.py`. It contains `schema_version`, `protocol_version`, `started_at`, and `updated_at`. Its `lifecycle` object has the exact callback keys `init`, `after_init`, `timer_callback`, `handlebar`, and `stop`; each callback entry records `count` and nullable `latest_at`. `timer_registration` contains `attempted`, `succeeded`, and nullable bounded `exception_type`. `handlebar_state` contains `is_last_bar_call_attempted`, `is_last_bar_callable`, and nullable bounded `is_last_bar_exception_type`.

The `queries` object has one entry for each lifecycle callback with a callback-level `attempted` flag and nested `account`, `position`, `order`, and `deal` outcomes. Each outcome contains `attempted`, nullable `succeeded`, and nullable bounded `exception_type`. Each callback type is queried at most once. The record stores no returned account/order/deal objects, provider representations, raw account or shareholder identifiers, binding key, credential, traceback, or complete local user path. Its `safety` object fixes `order_submission_enabled=false`, `cancel_enabled=false`, `passorder_invoked=false`, and `cancel_invoked=false`.

### Executor lifecycle diagnostics

`execution\diagnostics\executor_lifecycle_v1.json` is bounded, non-sensitive, canonical JSON diagnostic evidence. It contains `schema_version`, `protocol_version`, `started_at`, and `updated_at`. Its `lifecycle` object uses the same exact `init`, `after_init`, `timer_callback`, `handlebar`, and `stop` keys with `count` and nullable `latest_at`. `timer_registration` contains `attempted`, `succeeded`, and nullable bounded `error_type`. `handlebar_state` contains `entered`, nullable `is_last_bar_evaluation_succeeded`, and nullable `is_last_bar`.

The `intent_scan` object records the latest deterministic `outcome`, `executable_candidate_count`, and stable `reason_code` when processing does not continue. Reason codes include `no_intent_files`, `no_executable_intent`, `multiple_executable_intents`, `expired_intent_observed`, `terminal_intent_ignored`, `malformed_intent_observed`, `corrupt_intent_history_barrier`, `bound_intent_unavailable`, `waiting_for_handlebar`, `handlebar_not_last_bar`, and `executor_stopped`. The file never stores raw account identity or binding-key bytes. A diagnostic write failure does not authorize another submission attempt, erase execution state, or weaken the submission-attempted-before-`passorder` barrier.

## Run the one-time real-QMT lifecycle compatibility prerequisite

The lifecycle probe is a one-time real-QMT lifecycle compatibility prerequisite for PR #127 acceptance before creating any new broker-simulation intent. It is not a generic production approval layer and does not establish production readiness. This prerequisite exists because the real broker-simulation client started its model but did not demonstrate that QMT invoked `handlebar(ContextInfo)`. The probe is read-only and contains no order, cancellation, or other broker-mutation call.

1. Preserve the expired real-QMT intent and all of its state/result evidence. Do not create a replacement intent.
2. In the QMT strategy editor, create a separate strategy from the complete tracked `scripts/qmt_builtin_lifecycle_probe_v1.py`. Keep its first line exactly `#coding:gbk`, and set its bridge-root constant to the same external bridge root used by QuantPilot.
3. Bind the strategy only to the intended broker simulation/test `STOCK` account. If the QMT model must use an order-sending execution mode to expose broker context, select QMT live trading mode only after rechecking that the bound account is the simulation/test account. An order-sending mode bound to any real-money account is forbidden even though this probe is read-only.
4. Start the probe without an intent present for a new order. Exercise the intended period/mode long enough to observe the applicable callbacks and timer, then stop it cleanly so the `stop` observation can be recorded. Do not infer callback execution from the QMT start log.
5. Inspect the fresh `<bridge-root>\probe\lifecycle_probe_v1.json`. Confirm that its timestamps belong to this run, all `safety` flags are false, and `lifecycle`, `timer_registration`, `handlebar_state`, and per-callback `queries` evidence are present. Do not paste account identity or other local sensitive data into a report.
6. Treat a callback as having usable broker context only when the fresh record shows that callback was entered and its required read-only broker queries succeeded while bound to the intended simulation/test `STOCK` account. Preserve the record as the compatibility evidence.

No new broker-simulation intent may be created until this probe identifies a callback with usable broker context. The tracked executor still keeps broker readback and its sole direct `passorder(...)` call in `handlebar`; the probe does not authorize an operator to move or duplicate that call. If the probe finds usable context only in another callback, stop and obtain a reviewed executor revision before creating an intent. If no callback has usable context, stop without an intent or broker mutation.

## Prepare the dedicated QMT strategy

PR #126 remains a separate, strictly read-only bridge. Do not add `passorder` to `scripts/qmt_builtin_readonly_exporter_v1.py`, and do not weaken any of its mutation prohibitions.

After the lifecycle compatibility prerequisite above has been satisfied for `handlebar`, use only `scripts/qmt_builtin_simulation_executor_v1.py`:

1. In the QMT strategy editor, create a new Python strategy and copy the entire tracked executor source. Keep the first line exactly `#coding:gbk`.
2. Keep or set its bridge-root constant to the same external bridge root used by QuantPilot. The executor is ASCII-only, Python 3.6 compatible, and standard-library only.
3. In the QMT UI, select the intended broker simulation/test stock account. Confirm QMT will inject `account` and `accountType=STOCK`. Do not paste the account number into source.
4. Select QMT **live trading mode** for this model. Re-check that the bound account is still the simulation/test account and not a real-money account.
5. Do not start the strategy yet. After preserving the lifecycle-probe evidence, create and inspect exactly one new executable authenticated intent as described below, then manually start this dedicated executor. Existing terminal and expired intent files remain as immutable history.

The strategy performs broker queries and its only mutation call from `handlebar(ContextInfo)`. Historical bars return immediately. The one permitted call shape is:

```python
passorder(
    operation_code,       # 23 buy; 24 sell
    1101,                 # quantity is shares
    account_id,
    symbol,
    11,                   # explicit limit price
    limit_price,
    quantity,
    strategy_name,        # fixed value: quantpilot_sim_v1
    1,                    # quickTrade=1
    intent_id,            # QMT userOrderId
    ContextInfo,
)
```

There is exactly one direct `passorder` call site. There is no market-order routing, `quickTrade=2`, cancellation, algorithm order, credit-account operation, network access, `xtquant`, MiniQMT, subprocess, thread, or model call.

The fixed QMT strategy name recorded in version 1 results is `quantpilot_sim_v1`.

## Create exactly one executable intent

Creating an intent writes only the local filesystem protocol; it does not connect to QMT or submit an order. Nevertheless, it is the first half of the deliberate execution boundary, so verify the symbol, side, share quantity, limit price, external bridge root, redacted account binding, expiry, and intended test account before proceeding.

Do not run an intent-creation command until the fresh lifecycle probe has proved that `handlebar` has usable broker context for this QMT environment. Never reuse the expired real-QMT acceptance intent. Retained terminal or expired `.json` files do not count against the single new executable candidate and must not be deleted.

Use the PowerShell wrapper from the repository root. Replace every placeholder and retain the explicit confirmation switch:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\create_qmt_simulation_order_intent_v1.ps1 `
  -Symbol '<six-digit-symbol.exchange>' `
  -Side '<buy-or-sell>' `
  -Quantity <shares> `
  -LimitPrice <positive-limit-price> `
  -ExpectedRedactedAccountId 'qmtacct-v1-<24-lowercase-hex>' `
  -BridgeRoot '<external-bridge-root>' `
  -ConfirmBrokerSimulationOrder
```

The Python CLI exposes the equivalent required flags:

```text
--symbol
--side
--quantity
--limit-price
--expected-redacted-account-id
--bridge-root
--confirm-broker-simulation-order
```

Optional `--intent-id`, `--run-label`, and `--expires-in-seconds` arguments (PowerShell `-IntentId`, `-RunLabel`, and `-ExpiresInSeconds`) provide bounded identity, provenance, and expiry control. If omitted, the creator supplies a new intent ID, no run label, and the wrapper's bounded default expiry.

Without the exact `--confirm-broker-simulation-order` flag (or its PowerShell switch), the command creates no intent and modifies no state. A repeated creation for the same `intent_id` is accepted only when byte-identical or is rejected as a conflict; it never silently changes the order.

PR #127 supports explicit limit-share orders only. Buys must use a positive quantity divisible by the A-share 100-share buy lot. Sells must use a positive explicit share quantity and remain subject to the broker/account's available-position rules. There is no target-weight conversion, unspecified quantity, market order, automatic price selection, or automatic cancellation.

## Submit and inspect the result

1. Confirm that the intended `<intent-id>.json` is the only executable candidate and has not expired. Historical terminal and expired intent files may and should remain in `execution\intents`.
2. In QMT, perform the final visual check: **live trading mode**, the intended **simulation/test `STOCK` account**, and no real-money account selected.
3. Manually start `qmt_builtin_simulation_executor_v1.py`. The executor waits for QMT to invoke `handlebar(ContextInfo)`; neither the model start log nor timer registration proves that this occurred. The executor does not create a polling thread or continuously generate work.
4. Inspect the local result without contacting QMT:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\inspect_qmt_simulation_order_v1.ps1 `
  -BridgeRoot '<external-bridge-root>' `
  -IntentId '<intent-id>'
```

Use the wrapper's JSON option when machine-readable bounded output is required. The underlying Python inspector accepts the bridge root, intent ID, and text/JSON output format. Inspection reads only completed local state/result files; it never submits, cancels, or connects to QMT, and it does not print full account data.

5. Stop the dedicated executor after this one intent reaches a supported terminal outcome or after collecting the required `uncertain` evidence. Do not create a second intent as an automatic retry.

If no state or acknowledgement appears, inspect `<bridge-root>\execution\diagnostics\executor_lifecycle_v1.json` before taking any other action. Use its `lifecycle`, `timer_registration`, `handlebar_state`, and `intent_scan` evidence to distinguish a missing `handlebar` callback from a rejected or non-executable intent. Diagnostics alone never authorize resubmission.

`passorder` has no broker-acknowledgement return value. `passorder_attempted=true` means only that the direct call was attempted. Acceptance must be proved by QMT order/deal readback under the matching `intent_id`.

## Idempotency and crash recovery

`intent_id` is both the client idempotency key and the QMT `userOrderId`. QMT exposes it as `m_strRemark` on order/deal records. Before any submission attempt, the executor queries QMT orders and deals from `handlebar`:

- A matching order or deal causes reconciliation without another `passorder` call.
- Unrelated order/deal records never match merely by symbol, side, quantity, or price.
- `claimed` and `submission_attempted` are persisted before the mutation call.
- A matching order later upgrades the result to `broker_acknowledged`.
- Matching partial deal evidence upgrades it to `partially_filled`.
- Matching deal evidence for the requested quantity upgrades it to `filled`.
- An explicit bounded broker rejection becomes `rejected`.

If the process stops after `submission_attempted` but before readback proves an order or deal, the result becomes or remains `uncertain`. On restart, the executor queries by `m_strRemark` but does **not** automatically call `passorder` again. An acknowledgement write failure likewise does not authorize resubmission. Later readback may safely upgrade `uncertain`; until then it means neither accepted nor rejected. This protocol deliberately prefers one uncertain order over a possible duplicate order.

If a completed intent later becomes malformed while a state or acknowledgement/result path with the same valid filename-derived `intent_id` exists, the executor treats that pair as corrupt execution history. It inspects only whether the associated paths exist and have bounded regular-file shape; it does not parse, trust, rewrite, delete, normalize, or overwrite them without the authenticated intent. This `corrupt_intent_history_barrier` blocks all broker queries and submissions, and the attempt status remains unknown. A malformed intent with no associated state or result is instead an orphan: it remains untouched and non-executable, but does not block exactly one otherwise valid executable candidate.

Never work around `uncertain` by deleting local state or creating a replacement intent for the same economic order. First inspect the broker simulation/test account's order/deal records and preserve the protocol files for reconciliation.

## Reporting boundary

A completed result maps deterministically to the non-paper tuple keys `qmt_orders`, `qmt_fills`, and `qmt_reconciliation`. Their bounded mappings reuse the established reporting vocabulary: `order_id`/`fill_id`, `symbol`, `side`, `status`, `requested_quantity`, `filled_quantity`, `average_fill_price`, `order_status`, `submission_status`, and reconciliation status/checks. These facts remain explicitly identified as QMT broker-simulation facts.

They are not `paper_fills`, do not prove a paper simulated fill, and are not written to PostgreSQL by the QMT built-in strategy. PR #127 does not change continuous-paper tables, scheduling, candidate generation, or execution. Any later persistence integration must preserve this broker-simulation provenance instead of relabeling it as paper trading.

## Stop conditions and limitations

Stop the acceptance run without submission if any of the following is true:

- the QMT model is in simulation signal mode;
- the selected account is not positively verified as the intended broker simulation/test `STOCK` account;
- any real-money account is selected or account identity is ambiguous;
- the intent is missing, expired, unauthenticated, malformed, conflicting, or bound to another redacted account;
- the bridge root is in Git or differs between the intent creator and QMT strategy;
- the quantity or explicit limit price is wrong;
- the broker-specific simulation counter is unavailable;
- another manual order is already in progress;
- the lifecycle probe has not produced fresh evidence of usable `handlebar` broker context.

PR #127 offers no automatic cancellation. A limit order may remain pending according to broker simulation-counter behavior. Resolve it manually in the broker simulation/test environment only after preserving and inspecting the protocol evidence; do not represent a manual broker action as an automatic protocol result.

This runbook authorizes no real account action, real-money order, credential access/change, QMT installation modification, external MiniQMT connection, live DeepSeek call, continuous execution, or PR #128 behavior.
