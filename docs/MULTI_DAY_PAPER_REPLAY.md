# Multi-day Paper Replay

R23 extends the R22 paper-ledger dry-run path into deterministic multi-day replay.

The replay accepts daily batches of R21 `PaperLedgerCandidateInstruction` objects, runs R22 dry-run logic day by day, carries simulated cash and positions forward, and maintains A-share T+1 sellability semantics. It remains offline and in memory.

## Purpose

Single-day dry-runs are useful, but readiness gates need to observe behavior across time. R23 adds the first replay layer for checking whether a sequence of candidate paper instructions remains coherent across multiple trading days before future performance attribution or small-capital readiness work.

## Inputs

Each `PaperReplayDayInput` includes:

- strict ISO trading date in `YYYY-MM-DD`
- a tuple of R21 candidate instructions

Day inputs must be strictly increasing by trading date. Duplicate trading dates and duplicate proposal IDs across the full replay are rejected. Empty instruction days are allowed and recorded as no-op simulated days.

## Daily State Carry-forward

Replay starts from `account_profile.cash.available_cash` and account positions.

For each day, R23 builds an in-memory account profile using carried:

- available cash
- total position quantity by symbol
- sellable quantity by symbol

The daily profile is passed to R22 `run_paper_ledger_dry_run()`. Successful simulated instruction deltas are carried forward. Blocked instructions do not change replay state.

## A-share T+1 Sellability

Existing account sellable quantity remains sellable on day 1.

Shares bought on day D increase total position immediately, but they are not sellable on day D. They become sellable from the next replay trading day.

Sells reduce both total position and sellable quantity.

## Decisions

Replay can return:

- `COMPLETED`: every day simulated without blocked instructions
- `PARTIAL`: at least one day/instruction was blocked, but at least one day/instruction simulated
- `BLOCKED`: input preflight failed, every day was blocked, or `fail_fast=True` stopped replay after the first blocked day

With `fail_fast=True`, the first blocked day stops replay and later days are marked `SKIPPED`.

## Safety Boundaries

R23 does not connect to brokers, place live orders, mutate real accounts, call DeepSeek, perform network calls, run Qlib/RQAlpha, or write real paper-ledger persistence.

It is a deterministic replay of already-accepted candidate instructions only.

## Future Use

R23 supports future Performance Attribution Flywheel and Small-Capital Readiness Gate work by producing a structured multi-day dry result with final cash, final positions, blocked days, and per-day risk flags.
