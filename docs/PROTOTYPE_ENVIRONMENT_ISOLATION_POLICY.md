# Prototype Environment Isolation Policy

Manual external-framework prototypes must run in isolated prototype environments. The main project Python environment must not be used for framework experiments.

## Scope

This policy applies to future manual prototypes for tools such as vectorbt, Backtrader, RQAlpha, Qlib, LEAN, vn.py / VeighNa, NautilusTrader, Zipline-reloaded, backtesting.py, and bt.

## Rules

- Prototype dependencies must not enter `pyproject.toml` unless a later adapter phase is explicitly approved.
- Isolated prototype environments must live under `.venv-prototypes/<tool-name>/`.
- Prototype outputs must live under `local_artifacts/`.
- Raw outputs must remain gitignored.
- CI must not create or run prototype environments.
- No prototype may create broker, live trading, or real order submission paths.
- Live-trading-capable frameworks require extra isolation and explicit ChatGPT review before any run.

## Future Prototype Flow

1. ChatGPT kickoff review.
2. Create an isolated environment under `.venv-prototypes/<tool-name>/`.
3. Install only the approved package inside that environment.
4. Run the approved manual script.
5. Write summarized results to docs.
6. Keep raw outputs local.
7. ChatGPT closure review.

## Helper Scripts

Helper scripts in `tools/prototype_envs/` may create isolated environments. They do not install packages, modify `pyproject.toml`, run prototypes, fetch data, or call APIs.

## Phase 6C-1 Lesson

Phase 6C-1 showed that vectorbt can consume the fake Phase 3 fixture shape, but the manual install changed the main Python environment and downgraded an already-present pandas version. Future prototype installs must avoid this by using isolated environments.
