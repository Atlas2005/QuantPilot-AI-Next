"""Offline tests for the all-A-share optional PyArrow boundary."""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path
import tomllib
from types import ModuleType

import pytest

from quantpilot_core.all_a_share_snapshot.parquet_runtime import (
    ALL_A_SHARE_INSTALL_COMMAND,
    PyArrowUnavailableError,
    require_pyarrow,
)


def test_main_package_imports_without_pyarrow(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = importlib.import_module

    def missing_pyarrow(name: str, package: str | None = None) -> ModuleType:
        if name == "pyarrow":
            raise ModuleNotFoundError("No module named 'pyarrow'", name="pyarrow")
        return real_import(name, package)

    monkeypatch.setattr(importlib, "import_module", missing_pyarrow)
    assert importlib.import_module("quantpilot_core").__name__ == "quantpilot_core"


def test_parquet_runtime_missing_pyarrow_has_actionable_install_message() -> None:
    def missing_pyarrow(_: str) -> ModuleType:
        raise ModuleNotFoundError("No module named 'pyarrow'", name="pyarrow")

    with pytest.raises(PyArrowUnavailableError, match="PyArrow is required") as exc_info:
        require_pyarrow(importer=missing_pyarrow)

    assert ALL_A_SHARE_INSTALL_COMMAND in str(exc_info.value)


def test_fake_pyarrow_runtime_is_accepted_without_network_or_token_access() -> None:
    fake_pyarrow = ModuleType("pyarrow")
    fake_pyarrow.__version__ = "24.0.0"
    requested_modules: list[str] = []

    def importer(name: str) -> ModuleType:
        requested_modules.append(name)
        assert name == "pyarrow"
        return fake_pyarrow

    runtime = require_pyarrow(importer=importer)

    assert runtime.module is fake_pyarrow
    assert runtime.version == "24.0.0"
    assert requested_modules == ["pyarrow"]
    source = inspect.getsource(require_pyarrow)
    assert "TUSHARE_TOKEN" not in source
    assert "http" not in source


def test_runtime_import_failure_other_than_missing_pyarrow_is_not_hidden() -> None:
    def incompatible_runtime(_: str) -> ModuleType:
        raise RuntimeError("incompatible PyArrow binary")

    with pytest.raises(RuntimeError, match="incompatible PyArrow binary"):
        require_pyarrow(importer=incompatible_runtime)


def test_all_a_share_extra_includes_parquet_and_direct_provider_dependencies() -> None:
    payload = tomllib.loads(Path("pyproject.toml").read_text())
    extra = payload["project"]["optional-dependencies"]["all-a-share"]
    assert any(item.startswith("pyarrow") for item in extra)
    assert any(item.startswith("tushare>=1.4,<2") for item in extra)
