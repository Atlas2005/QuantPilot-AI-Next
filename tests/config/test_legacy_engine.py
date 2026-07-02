import pytest

from quantpilot_core.config import (
    LEGACY_ENGINE_DISABLED_REASON,
    legacy_engine_enabled,
    require_legacy_engine,
)


def test_legacy_engine_disabled_by_default_raises(monkeypatch) -> None:
    monkeypatch.delenv("USE_LEGACY_ENGINE", raising=False)

    assert legacy_engine_enabled() is False
    with pytest.raises(RuntimeError, match=LEGACY_ENGINE_DISABLED_REASON):
        require_legacy_engine()


def test_legacy_engine_env_true_enables_require(monkeypatch) -> None:
    monkeypatch.setenv("USE_LEGACY_ENGINE", "true")

    assert legacy_engine_enabled() is True
    require_legacy_engine()


def test_explicit_legacy_engine_true_enables_without_env(monkeypatch) -> None:
    monkeypatch.delenv("USE_LEGACY_ENGINE", raising=False)

    assert legacy_engine_enabled(explicit=True) is True
    require_legacy_engine(explicit=True)


def test_explicit_legacy_engine_false_rejects_even_with_env(monkeypatch) -> None:
    monkeypatch.setenv("USE_LEGACY_ENGINE", "true")

    assert legacy_engine_enabled(explicit=False) is False
    with pytest.raises(RuntimeError, match=LEGACY_ENGINE_DISABLED_REASON):
        require_legacy_engine(explicit=False)
