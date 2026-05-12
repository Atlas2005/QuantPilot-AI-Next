# Prototype Environment Helpers

This folder contains helper scripts for future isolated manual prototype environments.

These scripts are not run by CI. They do not install packages automatically unless a user manually runs a separate, approved install command inside the created environment.

Each prototype tool should have its own environment:

```text
.venv-prototypes/vectorbt/
.venv-prototypes/backtrader/
.venv-prototypes/rqalpha/
.venv-prototypes/qlib/
```

Prototype environments are for manual experiments only. They must not modify `pyproject.toml`, fetch provider data, run unapproved prototypes, or create broker/live/order paths.
