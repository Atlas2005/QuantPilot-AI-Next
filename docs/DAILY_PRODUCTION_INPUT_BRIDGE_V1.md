# Daily Production Input Bridge v1

`scripts/build_daily_production_input_v1.py` is the operational bridge from the
existing full-A Tushare snapshot capability to the existing Continuous Paper
input contract. It does not call DeepSeek, connect a broker, submit orders, or
use BaoStock/fixture candidates.

## Selection and allocation are separate

The authoritative upstream preselector is the existing
`run_factor_ranking_baseline_v1` implementation with
`defensive_composite_v1`. This is the deterministic non-ML ranking already
used by the real-candidate pipeline and evaluated as a PR121 Full-A fixed-rule
candidate.

The frozen production manifest remains `equal_weight_baseline`. In this bridge
that setting controls downstream equal-weight allocation and the tied
execution semantics over an already selected set. It is not used to select the
first symbols lexically from the full A-share market.

The bridge applies these existing inputs and boundaries:

- validated all-A Parquet snapshot and PIT listing dates;
- the snapshot's official SSE session calendar;
- persisted suspension and price-limit metadata through the existing
  tradability enrichment;
- valid decision-day OHLC and positive volume;
- the existing factor baseline with a 61-session window through decision day;
- `target_symbol_count` and `max_execution_symbols` from the strict production
  manifest (never more than six).

Only the six fields accepted by `production_input_v1` are written. The
authoritative calendar is serialized inside `quant_firm_context`, so the
existing Continuous Paper loader can recover it without adding another input
schema or falling back to a weekday fixture. Market bars are capped at the
decision session; the next session is calendar metadata only.

## Windows cached-snapshot command

The cached snapshot must validate successfully, include the 61 factor sessions
through the requested decision session, include the next official calendar
session, and expose `suspend` and `limits` capabilities as `available`.

```powershell
py -3 scripts\build_daily_production_input_v1.py `
  --mode cached `
  --production-manifest artifacts\production_candidate\latest_manifest.json `
  --snapshot-root D:\QuantPilotData\all_a_share_snapshot_v1 `
  --decision-session 2026-07-31 `
  --output .cache\quantpilot\production_input_2026-07-31.json
```

No provider call occurs in cached mode. A snapshot whose declared coverage
ends before the requested session is rejected; the builder does not substitute
fixtures or a historical default.

## Windows real-Tushare command

Load `TUSHARE_TOKEN` into the process environment before running this command.
The token is never accepted as a CLI argument and is never serialized or
printed. Keep `--snapshot-start-date` stable across daily resumptions so the
existing snapshot builder can reuse validated partitions.

```powershell
py -3 scripts\build_daily_production_input_v1.py `
  --mode tushare `
  --production-manifest artifacts\production_candidate\latest_manifest.json `
  --snapshot-root D:\QuantPilotData\all_a_share_snapshot_v1 `
  --snapshot-start-date 20250101 `
  --decision-session 2026-07-31 `
  --output .cache\quantpilot\production_input_2026-07-31.json
```

Real mode uses only the existing direct Tushare calendar and all-A snapshot
components. A missing environment token, incomplete snapshot, unavailable
tradability metadata, empty universe, or insufficient factor evidence is a
hard failure.

## Continuous Paper, experience plan, and QPTY

The generated file is passed directly to the existing cycle. This initial
qualification uses the in-memory reporting store and publishes the resulting
candidates to block code `QPTY`, displayed as `QP候选`.

```powershell
py -3 scripts\run_continuous_paper_cycle_v1.py `
  --production-manifest artifacts\production_candidate\latest_manifest.json `
  --decision-session 2026-07-31 `
  --state-path .cache\quantpilot\paper_state.json `
  --report-path .cache\quantpilot\paper_report.json `
  --input-json .cache\quantpilot\production_input_2026-07-31.json `
  --test-store `
  --experience-plan-path .cache\quantpilot\tdx_experience_plan.json `
  --publish-tq-visibility `
  --tdx-user-dir D:\tongdaxin\PYPlugins\user `
  --tq-block-code QPTY `
  --tq-block-name "QP候选"
```

`send_user_block` receives the selected symbols from the generated input; no
fixed demonstration-stock list is introduced by this bridge.

## Separate active-shadow command

After the deterministic path qualifies, load `DEEPSEEK_API_KEY` into the
process environment and add the existing advisory flags to the Continuous
Paper command. Input construction remains deterministic and makes no model
call.

```powershell
py -3 scripts\run_continuous_paper_cycle_v1.py `
  --production-manifest artifacts\production_candidate\latest_manifest.json `
  --decision-session 2026-07-31 `
  --state-path .cache\quantpilot\paper_state.json `
  --report-path .cache\quantpilot\paper_report.json `
  --input-json .cache\quantpilot\production_input_2026-07-31.json `
  --test-store `
  --enable-active-shadow `
  --enable-live-ai `
  --max-physical-model-calls 1 `
  --max-estimated-api-cost 1.0 `
  --estimated-cost-per-call 0.1
```

This second command activates only the existing Continuous Paper advisory
shadow. It does not change candidate selection, equal-weight allocation, or
broker state.
