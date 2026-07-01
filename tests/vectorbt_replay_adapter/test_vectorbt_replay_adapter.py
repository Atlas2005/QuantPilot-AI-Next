from __future__ import annotations

import importlib.util

from quantpilot_core.vectorbt_replay_adapter import (
    VectorbtReplayInput,
    VectorbtReplayStatus,
    build_vectorbt_replay_report,
    run_vectorbt_replay,
)


def valid_input() -> VectorbtReplayInput:
    return VectorbtReplayInput(
        prices={"600000": (10.0, 10.2, 10.4, 10.3)},
        entries={"600000": (True, False, False, False)},
        exits={"600000": (False, False, True, False)},
    )


def test_invalid_input_returns_invalid_input() -> None:
    result = run_vectorbt_replay(
        VectorbtReplayInput(
            prices={"600000": (10.0, 10.2)},
            entries={"600000": (True,)},
            exits={"600000": (False, False)},
        )
    )

    assert result.status == VectorbtReplayStatus.INVALID_INPUT.value
    assert result.reason == "length_mismatch:600000"


def test_missing_vectorbt_is_handled_gracefully() -> None:
    def missing_importer(name: str):
        raise ImportError(name)

    result = run_vectorbt_replay(valid_input(), importer=missing_importer)

    assert result.status == VectorbtReplayStatus.FRAMEWORK_MISSING.value
    assert result.reason == "vectorbt_not_installed"
    assert result.equity_curve == ()


def test_default_environment_passes_even_when_vectorbt_missing() -> None:
    result = run_vectorbt_replay(valid_input())

    assert result.status in {
        VectorbtReplayStatus.COMPLETED.value,
        VectorbtReplayStatus.FRAMEWORK_MISSING.value,
    }
    if result.status == VectorbtReplayStatus.FRAMEWORK_MISSING.value:
        assert result.reason == "vectorbt_not_installed"


def test_minimal_replay_completes_if_vectorbt_installed() -> None:
    if importlib.util.find_spec("vectorbt") is None:
        result = run_vectorbt_replay(valid_input())
        assert result.status == VectorbtReplayStatus.FRAMEWORK_MISSING.value
        return

    result = run_vectorbt_replay(valid_input())

    assert result.status == VectorbtReplayStatus.COMPLETED.value
    assert result.reason == "completed"
    assert result.equity_curve
    assert result.total_return is not None


def test_package_exports_are_correct() -> None:
    report = build_vectorbt_replay_report(valid_input())

    assert "mature-framework replay adapter" in report
    assert "not a new self-built engine" in report
